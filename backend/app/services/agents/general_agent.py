import asyncio
import logging
import re
from typing import Any

from app.services.agents.base import BaseAgent
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

_MAX_DEP_CHARS = 4_000


class GeneralAgent(BaseAgent):
    """
    Sophisticated general-purpose agent using chain-of-thought reasoning:
      1. Classify the task and identify the best reasoning strategy.
      2. Generate a step-by-step plan (chain-of-thought).
      3. Execute each reasoning step (sequentially, building on prior steps).
      4. Synthesise a high-quality final answer in structured markdown.

    Best for: summarisation, transformation, Q&A, comparison, analysis, reasoning
    tasks that do not require code execution or live data retrieval.
    """

    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or get_default_model_for_agent("general")

        async def log(level: str, msg: str):
            if log_callback:
                await log_callback(level, msg)

        await log("info", f"General Agent | model={resolved_model}")
        await log("info", f"Task: {prompt[:140]}")

        # Build dependency context
        dep_context = self._build_dep_context(dependency_outputs)

        # ── 1. Classify task ───────────────────────────────────────────────────
        await log("info", "Classifying task type and reasoning strategy...")
        classification = await self._classify(resolved_model, prompt, dep_context)
        await log("info", f"Classification: {classification.get('task_type', 'unknown')} — "
                          f"strategy: {classification.get('strategy', 'direct')}")

        strategy = classification.get("strategy", "direct")

        if strategy == "direct":
            # Simple task — single LLM call is enough
            await log("info", "Direct answer strategy selected.")
            result = await self._direct_answer(resolved_model, prompt, dep_context)
        else:
            # Chain-of-thought: plan → execute steps → synthesise
            await log("info", "Chain-of-thought strategy selected.")

            # ── 2. Plan ────────────────────────────────────────────────────────
            await log("info", "Generating reasoning plan...")
            steps = await self._plan(resolved_model, prompt, dep_context, classification)
            await log("info", f"Plan: {len(steps)} step(s)")
            for i, s in enumerate(steps, 1):
                await log("info", f"  Step {i}: {s[:100]}")

            # ── 3. Execute each step ───────────────────────────────────────────
            step_results: list[str] = []
            for i, step in enumerate(steps, 1):
                await log("info", f"Executing step {i}/{len(steps)}: {step[:80]}...")
                prior = self._format_prior_steps(steps[:i-1], step_results)
                result_text = await self._execute_step(
                    resolved_model, prompt, dep_context, step, prior
                )
                step_results.append(result_text)
                await log("info", f"  ✓ Step {i} done ({len(result_text)} chars)")

            # ── 4. Synthesise ──────────────────────────────────────────────────
            await log("info", "Synthesising final answer...")
            result = await self._synthesise(
                resolved_model, prompt, dep_context, steps, step_results
            )

        await log("info", f"Done ({len(result)} chars).")
        return {"summary": result}

    # ── Classification ────────────────────────────────────────────────────────

    async def _classify(self, model: str, prompt: str, dep_context: str) -> dict:
        system = (
            "You are a task classifier. Analyse the task and output a JSON object with:\n"
            "- task_type: one of [summarisation, analysis, comparison, transformation, "
            "reasoning, planning, explanation, qa, creative, other]\n"
            "- strategy: 'direct' for simple/short tasks, 'chain_of_thought' for complex "
            "multi-step tasks requiring careful reasoning\n"
            "- complexity: 'low', 'medium', or 'high'\n"
            "Output ONLY valid JSON, no markdown fences."
        )
        user = f"Task: {prompt}"
        if dep_context:
            user += f"\n\nUpstream context (first 500 chars): {dep_context[:500]}"
        try:
            raw = await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=200,
                temperature=0.0,
            )
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            import json
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Classification failed: {e}")
            return {"task_type": "other", "strategy": "chain_of_thought", "complexity": "medium"}

    # ── Planning ──────────────────────────────────────────────────────────────

    async def _plan(
        self, model: str, prompt: str, dep_context: str, classification: dict
    ) -> list[str]:
        task_type = classification.get("task_type", "other")
        complexity = classification.get("complexity", "medium")

        system = (
            f"You are a reasoning planner for a {task_type} task of {complexity} complexity. "
            "Decompose the task into 3–6 clear reasoning steps. Each step should build on the "
            "previous ones. Output ONLY a numbered list, one step per line — no explanations, "
            "no preamble. Steps should be actionable thinking actions, e.g. 'Identify the key "
            "variables', 'Compare X and Y on dimension Z', 'Draw conclusion from findings'."
        )
        user_parts = [f"Task: {prompt}"]
        if dep_context:
            user_parts.append(f"\nAvailable context:\n{dep_context[:2000]}")

        try:
            raw = await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "\n".join(user_parts)},
                ],
                max_tokens=400,
                temperature=0.3,
            )
            steps = []
            for line in raw.splitlines():
                cleaned = re.sub(r"^[\d]+[.)]\s*", "", line.strip()).strip()
                if cleaned:
                    steps.append(cleaned)
            return steps[:6] if steps else ["Analyse the task", "Formulate the answer"]
        except Exception as e:
            logger.warning(f"Planning failed: {e}")
            return ["Analyse the task and available context", "Formulate a comprehensive answer"]

    # ── Step execution ────────────────────────────────────────────────────────

    async def _execute_step(
        self,
        model: str,
        prompt: str,
        dep_context: str,
        step: str,
        prior_reasoning: str,
    ) -> str:
        system = (
            "You are a step-by-step reasoning engine. Execute only the specified reasoning step. "
            "Be thorough and analytical. Reference specific data from the context. "
            "Keep your response focused on just this step — do not write a conclusion or summary. "
            "Use markdown formatting if helpful (tables, lists). Max 400 words."
        )
        user = (
            f"Overall task: {prompt}\n\n"
            f"Current step to execute: **{step}**\n\n"
        )
        if prior_reasoning:
            user += f"Prior reasoning steps:\n{prior_reasoning}\n\n"
        if dep_context:
            user += f"Available context:\n{dep_context[:3000]}"

        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=600,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning(f"Step execution failed: {e}")
            return f"*(step failed: {e})*"

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def _synthesise(
        self,
        model: str,
        prompt: str,
        dep_context: str,
        steps: list[str],
        step_results: list[str],
    ) -> str:
        # Build reasoning chain summary
        chain = "\n\n".join(
            f"**Step {i+1} — {step}:**\n{result}"
            for i, (step, result) in enumerate(zip(steps, step_results))
        )

        system = (
            "You are a senior analyst synthesising a chain-of-thought reasoning process into "
            "a final, polished answer. Use the reasoning chain to inform your answer, but write "
            "the output as a clean, well-structured markdown document — NOT as a list of steps. "
            "Use appropriate headings (##), bullet points, tables, code blocks as needed. "
            "Support LaTeX math: $...$ for inline, $$...$$ for display. "
            "Be precise, cite specific facts and numbers from the reasoning. "
            "End with a clear conclusion or recommendation section."
        )
        user = (
            f"Task: {prompt}\n\n"
            f"Reasoning chain:\n{chain[:8000]}\n\n"
        )
        if dep_context:
            user += f"Source context:\n{dep_context[:2000]}"

        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=2500,
                temperature=0.4,
            )
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            # Fallback: return the raw chain
            return f"## {prompt}\n\n" + chain

    async def _direct_answer(self, model: str, prompt: str, dep_context: str) -> str:
        system = (
            "You are an expert assistant. Answer the task clearly and comprehensively. "
            "Use markdown formatting: headings, lists, tables, code blocks as appropriate. "
            "Support LaTeX math: $...$ inline, $$...$$ display. Be precise and well-structured."
        )
        user = f"Task: {prompt}"
        if dep_context:
            user += f"\n\nContext from upstream tasks:\n{dep_context[:4000]}"

        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=2000,
                temperature=0.5,
            )
        except Exception as e:
            logger.warning(f"Direct answer failed: {e}")
            return f"**Task:** {prompt}\n\n*(Answer generation failed: {e})*"

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _build_dep_context(self, dependency_outputs: dict) -> str:
        if not dependency_outputs:
            return ""
        parts = []
        for tid, out in dependency_outputs.items():
            if out:
                parts.append(f"[Task {tid[:8]}]:\n{str(out)[:_MAX_DEP_CHARS]}")
        return "\n\n---\n\n".join(parts)

    def _format_prior_steps(self, steps: list[str], results: list[str]) -> str:
        if not steps or not results:
            return ""
        parts = []
        for s, r in zip(steps, results):
            parts.append(f"**{s}**\n{r[:500]}")
        return "\n\n".join(parts)
