import asyncio
import logging
import random
from typing import Any

from app.services.agents.base import BaseAgent
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

MOCK_LOG_MESSAGES = {
    "data_retrieval": [
        "Initializing data retrieval agent...",
        "Connecting to data source...",
        "Fetching records...",
        "Processing response data...",
        "Validating data integrity...",
        "Data retrieval complete.",
    ],
    "spreadsheet": [
        "Initializing spreadsheet agent...",
        "Reading input data from dependencies...",
        "Creating spreadsheet structure...",
        "Formatting headers and columns...",
        "Populating rows...",
        "Calculating summary statistics...",
        "Spreadsheet generation complete.",
    ],
    "code_execution": [
        "Initializing code execution agent...",
        "Setting up sandbox environment...",
        "Installing dependencies...",
        "Executing code...",
        "Processing results...",
        "Code execution complete.",
    ],
    "report": [
        "Initializing report agent...",
        "Gathering inputs from dependencies...",
        "Analyzing data...",
        "Generating document sections...",
        "Formatting final report...",
        "Report generation complete.",
    ],
    "general": [
        "Initializing agent...",
        "Processing task...",
        "Generating output...",
        "Task complete.",
    ],
}


async def _generate_output_with_llm(
    prompt: str,
    agent_type: str,
    dependency_outputs: dict[str, Any],
    model: str | None = None,
) -> str:
    """Use LLM to generate a contextual mock output for this task."""
    resolved_model = model or get_default_model_for_agent(agent_type)

    try:
        dep_context = ""
        if dependency_outputs:
            dep_summaries = []
            for dep_id, output in dependency_outputs.items():
                if output:
                    # Truncate long outputs
                    text = str(output)[:500]
                    dep_summaries.append(f"- Dependency output: {text}")
            if dep_summaries:
                dep_context = "\n\nInputs from upstream tasks:\n" + "\n".join(dep_summaries)

        type_instructions = {
            "data_retrieval": "You retrieved data. Show a sample of the data in a markdown table (5-10 rows). Include a summary of total records found.",
            "spreadsheet": "You created a spreadsheet. Show the spreadsheet as a markdown table with row numbers. Include summary statistics at the bottom.",
            "code_execution": "You executed code. Show the code in a fenced code block, then show the results including any computed values. Use tables for structured results. Use LaTeX notation ($...$ or $$...$$) for mathematical equations and formulas.",
            "report": "You wrote a report. Write a proper multi-section markdown document with headings, findings, and conclusions. Make it 200-400 words. IMPORTANT: If the dependency inputs contain image markdown (![...](...)) for plots or artifacts, you MUST include those exact image markdown tags in your report so the images render. Do NOT omit or rewrite the image URLs. Use LaTeX math notation ($...$ for inline, $$...$$ for display) when presenting equations or formulas.",
            "general": "Produce a clear, structured markdown output for this task with relevant content.",
        }

        system_msg = f"""You are a mock agent producing realistic output for a workflow task.
Agent type: {agent_type}

{type_instructions.get(agent_type, type_instructions['general'])}

Rules:
- Output ONLY the markdown content, no preamble
- Make the output realistic and relevant to the specific task prompt
- Use markdown formatting: tables, code blocks, headings, lists, blockquotes
- Keep output concise but substantive (100-300 words)
- If you have dependency inputs, reference and build on them"""

        user_msg = f"Task: {prompt}{dep_context}"

        return await chat_completion(
            resolved_model,
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1000,
            temperature=0.7,
        )

    except Exception as e:
        logger.warning(f"LLM output generation failed: {e}")
        return f"**Task completed:** {prompt}\n\n> Output generation encountered an error. Fallback result."


class MockAgent(BaseAgent):
    def __init__(self, agent_type: str = "general"):
        self.agent_type = agent_type

    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        logs = MOCK_LOG_MESSAGES.get(self.agent_type, MOCK_LOG_MESSAGES["general"])

        for msg in logs:
            if log_callback:
                await log_callback("info", msg)
            await asyncio.sleep(random.uniform(0.3, 0.8))

        resolved_model = model or get_default_model_for_agent(self.agent_type)

        # Log LLM input
        if log_callback:
            await log_callback("info", f"Using model: {resolved_model}")
            await log_callback("info", f"[LLM Input] Prompt: {prompt}")
            if dependency_outputs:
                for dep_id, dep_out in dependency_outputs.items():
                    preview = str(dep_out)[:200]
                    await log_callback("info", f"[LLM Input] Dependency {dep_id[:8]}...: {preview}")
            await log_callback("info", "Generating output...")

        summary = await _generate_output_with_llm(
            prompt, self.agent_type, dependency_outputs, model=resolved_model
        )

        # Log LLM output
        if log_callback:
            preview = summary[:300] if summary else "(empty)"
            await log_callback("info", f"[LLM Output] {preview}")

        return {"summary": summary}
