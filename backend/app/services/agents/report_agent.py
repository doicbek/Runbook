import asyncio
import logging
import re
from typing import Any

from app.services.agents.base import BaseAgent
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

# Max characters of each dependency output fed to the LLM
_MAX_DEP_CHARS = 6_000
# Max total context for the final writing step
_MAX_CONTEXT_CHARS = 20_000


class ReportAgent(BaseAgent):
    """
    Sophisticated multi-step report agent:
      1. Extract key findings from each upstream output in parallel.
      2. Build a structured outline based on the task prompt + findings.
      3. Write each section of the report (parallelised where independent).
      4. Assemble the final report, preserving inline images and LaTeX math.
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
        resolved_model = model or get_default_model_for_agent("report")

        async def log(level: str, msg: str):
            if log_callback:
                await log_callback(level, msg)

        await log("info", f"Report Agent | model={resolved_model}")
        await log("info", f"Task: {prompt[:140]}")

        # ── 1. Extract findings from each dep (parallel) ──────────────────────
        dep_items = [(tid, str(out)) for tid, out in dependency_outputs.items() if out]
        if dep_items:
            await log("info", f"Extracting findings from {len(dep_items)} upstream task(s)...")
            findings_list = await asyncio.gather(*[
                self._extract_findings(resolved_model, tid, output[:_MAX_DEP_CHARS])
                for tid, output in dep_items
            ])
            findings = {tid: f for (tid, _), f in zip(dep_items, findings_list)}
            for tid, f in findings.items():
                await log("info", f"  [{tid[:8]}] {f[:120]}...")
        else:
            await log("info", "No upstream dependencies — writing from prompt alone.")
            findings = {}

        # ── 2. Build outline ───────────────────────────────────────────────────
        await log("info", "Building report outline...")
        outline = await self._build_outline(resolved_model, prompt, findings)
        sections = self._parse_outline(outline)
        await log("info", f"Outline: {len(sections)} section(s)")
        for s in sections:
            await log("info", f"  • {s}")

        # ── 3. Write sections (parallel) ───────────────────────────────────────
        await log("info", "Writing report sections...")

        # Collect all image tags from dependencies so we can inject them
        image_tags = self._collect_image_tags(dep_items)
        if image_tags:
            await log("info", f"Preserving {len(image_tags)} inline image(s) from upstream tasks")

        full_context = self._build_context(findings, dep_items)
        section_texts = await asyncio.gather(*[
            self._write_section(resolved_model, prompt, section, full_context, image_tags, i)
            for i, section in enumerate(sections)
        ])

        for i, (section, text) in enumerate(zip(sections, section_texts)):
            await log("info", f"  ✓ '{section}' ({len(text)} chars)")

        # ── 4. Assemble final report ───────────────────────────────────────────
        await log("info", "Assembling final report...")
        report = await self._assemble(resolved_model, prompt, sections, section_texts, image_tags)
        await log("info", f"Report complete ({len(report)} chars).")

        return {"summary": report}

    # ── Step helpers ──────────────────────────────────────────────────────────

    async def _extract_findings(self, model: str, task_id: str, output: str) -> str:
        """Summarise key facts / data points from a single upstream output."""
        system = (
            "You are a research analyst. Extract the key findings, data points, numbers, "
            "and conclusions from the provided task output. Be concise and factual. "
            "Preserve any important numeric values exactly. Output plain prose (no headings). "
            "Max 300 words."
        )
        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Task output to analyse:\n\n{output}"},
                ],
                max_tokens=500,
            )
        except Exception as e:
            logger.warning(f"Finding extraction failed for {task_id}: {e}")
            return output[:300]

    async def _build_outline(self, model: str, prompt: str, findings: dict) -> str:
        """Generate a numbered section list for the report."""
        findings_text = "\n\n".join(
            f"[Source {i+1}]: {f}" for i, (_, f) in enumerate(findings.items())
        ) if findings else "(no upstream data)"

        system = (
            "You are a report planner. Given a report task and available findings, output a "
            "numbered list of section titles only — nothing else. Each title on its own line. "
            "Start with an Executive Summary. End with Conclusions. Include 4–7 sections total. "
            "Do NOT write any section content, just the titles."
        )
        user = f"Report task: {prompt}\n\nAvailable findings:\n{findings_text[:3000]}"
        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=300,
            )
        except Exception as e:
            logger.warning(f"Outline generation failed: {e}")
            return "1. Executive Summary\n2. Findings\n3. Analysis\n4. Conclusions"

    def _parse_outline(self, outline: str) -> list[str]:
        """Parse numbered list into clean section titles."""
        titles = []
        for line in outline.splitlines():
            line = line.strip()
            if not line:
                continue
            # Remove leading numbers/bullets: "1.", "1)", "-", "*"
            cleaned = re.sub(r"^[\d]+[.)]\s*", "", line)
            cleaned = re.sub(r"^[-*]\s*", "", cleaned).strip()
            if cleaned:
                titles.append(cleaned)
        return titles if titles else ["Executive Summary", "Findings", "Analysis", "Conclusions"]

    async def _write_section(
        self,
        model: str,
        prompt: str,
        section: str,
        full_context: str,
        image_tags: list[str],
        section_index: int,
    ) -> str:
        """Write a single section of the report."""
        image_instruction = ""
        if image_tags and section_index == len(image_tags) - 1:
            # Inject images into the last substantive section before conclusions
            img_block = "\n".join(image_tags)
            image_instruction = (
                f"\n\nIMPORTANT: This section must include the following image(s) inline "
                f"using the EXACT markdown image tags provided (do not alter URLs):\n{img_block}"
            )

        system = (
            "You are a technical report writer. Write the specified section of a report "
            "using the provided context. Use markdown formatting (subheadings with ##, "
            "bullet lists, bold key terms, markdown tables if presenting data). "
            "Support LaTeX math: inline with $...$, display with $$...$$. "
            "Be precise, cite numbers and sources from the context. "
            "Write 150–400 words for this section."
            f"{image_instruction}"
        )
        user = (
            f"Report goal: {prompt}\n\n"
            f"Section to write: **{section}**\n\n"
            f"Available context:\n{full_context[:_MAX_CONTEXT_CHARS]}"
        )
        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=800,
            )
        except Exception as e:
            logger.warning(f"Section '{section}' writing failed: {e}")
            return f"*Section unavailable due to error: {e}*"

    async def _assemble(
        self,
        model: str,
        prompt: str,
        sections: list[str],
        section_texts: list[str],
        image_tags: list[str],
    ) -> str:
        """Assemble all sections into a coherent final report."""
        # Build raw assembled text first
        raw_parts = [f"# {prompt}\n"]
        for title, text in zip(sections, section_texts):
            raw_parts.append(f"## {title}\n\n{text}")

        assembled = "\n\n---\n\n".join(raw_parts)

        # Ensure all image tags are present in the final output
        missing_images = [tag for tag in image_tags if tag not in assembled]

        if not missing_images:
            # No assembly needed — return directly
            return assembled

        # If images are missing, do a final LLM pass to weave them in
        system = (
            "You are a document editor. You are given a report and a list of image markdown tags "
            "that MUST appear in the final document. Insert each image tag at the most "
            "contextually appropriate location in the report. Do NOT change any text, "
            "just insert the image tags where they belong. Output the complete report."
        )
        user = (
            f"Report:\n\n{assembled[:12_000]}\n\n"
            f"Missing image tags to insert:\n" + "\n".join(missing_images)
        )
        try:
            return await chat_completion(
                model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=6000,
            )
        except Exception as e:
            logger.warning(f"Final assembly failed: {e} — returning raw assembled text")
            # Append missing images at the end
            return assembled + "\n\n" + "\n\n".join(missing_images)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _collect_image_tags(self, dep_items: list[tuple[str, str]]) -> list[str]:
        """Extract all ![...](...) markdown image tags from upstream outputs."""
        pattern = re.compile(r"!\[.*?\]\(.*?\)")
        tags = []
        seen: set[str] = set()
        for _, output in dep_items:
            for tag in pattern.findall(output):
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
        return tags

    def _build_context(self, findings: dict, dep_items: list[tuple[str, str]]) -> str:
        """Build consolidated context string from findings + raw outputs."""
        parts = []
        for i, ((tid, raw), finding) in enumerate(
            zip(dep_items, findings.values()) if findings else []
        ):
            parts.append(
                f"### Source {i+1} (task {tid[:8]})\n"
                f"**Key findings:** {finding}\n\n"
                f"**Raw output (truncated):**\n{raw[:1500]}"
            )
        if not parts and dep_items:
            for tid, raw in dep_items:
                parts.append(f"### Output from {tid[:8]}\n{raw[:2000]}")
        return "\n\n---\n\n".join(parts) if parts else "(no upstream context)"
