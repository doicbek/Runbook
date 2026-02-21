import logging
import re

from app.schemas.agent_definition import ScaffoldResponse
from app.services.agents.tool_catalog import TOOL_CATALOG_BY_ID
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

PLATFORM_BLOCK = """# Platform Context
You are generating code for an agent running inside WSL2 on Windows 11.
- win32com is NOT available — do not use it.
- Use python-docx for Word files, openpyxl for Excel, python-pptx for PowerPoint.
- Windows file paths (C:\\Users\\...) are accessible at /mnt/c/Users/... in WSL2.
- The agent runs in an async Python environment with asyncio.
"""

BASE_AGENT_INTERFACE = '''# BaseAgent Interface (you MUST subclass this)
from abc import ABC, abstractmethod
from typing import Any

class BaseAgent(ABC):
    @abstractmethod
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Execute the agent\'s task and return output.

        Args:
            task_id: The task ID being executed
            prompt: The task prompt
            dependency_outputs: Outputs from dependency tasks {task_id: output}
            log_callback: Async callable(level, message) for streaming logs
            model: LLM model to use (e.g. "openai/gpt-4o")

        Returns:
            dict with at least "summary" key (markdown string)
        """
        ...
'''

REFERENCE_EXAMPLE = '''# Reference Example Agent
import logging
from typing import Any
from app.services.agents.base import BaseAgent
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

class ExampleAgent(BaseAgent):
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
        if log_callback:
            await log_callback("info", f"Starting task: {prompt[:80]}")

        # Build context from upstream task outputs
        context = ""
        for dep_id, dep_output in dependency_outputs.items():
            context += f"\\n\\nUpstream output ({dep_id}):\\n{dep_output}"

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{prompt}{context}"},
        ]
        result = await chat_completion(resolved_model, messages)

        if log_callback:
            await log_callback("info", "Task completed.")

        return {"summary": result}
'''

RULES = """# Rules for the generated agent
1. Output ONLY a Python class definition — no markdown fences, no explanations, no extra text.
2. The class MUST subclass BaseAgent (imported from app.services.agents.base).
3. The execute() method MUST have this exact signature:
   async def execute(self, task_id: str, prompt: str, dependency_outputs: dict[str, Any], log_callback: Any = None, *, model: str | None = None) -> dict[str, Any]
4. Return a dict with at least {"summary": "<markdown string>"}.
5. Use log_callback("info"|"warn"|"error", message) for progress updates (always await it).
6. Do NOT use win32com — it does not work in WSL2.
7. Import everything needed at the top of the class file.
8. Use get_default_model_for_agent("general") as fallback if model is None.
"""


def _strip_code_fences(code: str) -> str:
    """Remove markdown code fences if present."""
    code = code.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        # Remove first line (```python or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        code = "\n".join(lines)
    return code.strip()


class AgentScaffoldingService:
    async def scaffold(
        self,
        name: str,
        description: str,
        tools: list[str],
        model: str | None = None,
    ) -> ScaffoldResponse:
        resolved_model = model or get_default_model_for_agent("general")

        # Build tool context
        tool_snippets = []
        pip_packages = []
        for tool_id in tools:
            entry = TOOL_CATALOG_BY_ID.get(tool_id)
            if entry:
                tool_snippets.append(
                    f"## Tool: {entry['name']}\n"
                    f"Import: {entry['import_snippet']}\n"
                    f"Usage:\n{entry['usage_snippet']}"
                )
                if entry.get("pip_package"):
                    pip_packages.append(entry["pip_package"])

        tool_context = "\n\n".join(tool_snippets) if tool_snippets else "# No specific tools selected — use standard library or LLM calls."

        system_prompt = "\n\n".join([
            PLATFORM_BLOCK,
            BASE_AGENT_INTERFACE,
            REFERENCE_EXAMPLE,
            f"# Available Tool Snippets\n{tool_context}",
            RULES,
        ])

        user_message = (
            f"Generate a Python agent class named {_to_class_name(name)} for the following task:\n\n"
            f"Name: {name}\n"
            f"Description: {description}\n"
            f"Selected tools: {', '.join(tools) if tools else 'none'}\n\n"
            f"Output ONLY the Python class. No markdown, no explanation."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for attempt in range(2):
            try:
                raw = await chat_completion(resolved_model, messages, max_tokens=4096)
                code = _strip_code_fences(raw)
                # Validate syntax
                compile(code, f"<agent:{name}>", "exec")
                logger.info(f"Scaffold generated for '{name}' on attempt {attempt + 1}")

                requirements = f"pip install {' '.join(pip_packages)}" if pip_packages else "# No additional packages required"
                setup_notes = _build_setup_notes(tools)

                return ScaffoldResponse(
                    code=code,
                    requirements=requirements,
                    setup_notes=setup_notes,
                )
            except SyntaxError as e:
                logger.warning(f"Syntax error in generated code (attempt {attempt + 1}): {e}")
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": f"The generated code has a syntax error: {e}. Please fix it and output only the corrected Python class.",
                    })
            except Exception as e:
                logger.exception(f"Scaffold failed (attempt {attempt + 1}): {e}")
                if attempt == 1:
                    raise

        raise RuntimeError("Failed to generate valid agent code after 2 attempts")


    async def modify(
        self,
        name: str,
        description: str,
        current_code: str | None,
        modification_prompt: str,
        model: str | None = None,
    ) -> str:
        """Apply a natural-language modification to existing agent code."""
        resolved_model = model or get_default_model_for_agent("general")

        if current_code:
            user_message = (
                f"Here is the current agent class for '{name}':\n\n"
                f"```python\n{current_code}\n```\n\n"
                f"Modify it as follows: {modification_prompt}\n\n"
                f"Output ONLY the complete modified Python class. No markdown fences, no explanation."
            )
        else:
            # No existing code (builtin) — generate from scratch with the modification as intent
            user_message = (
                f"Generate a Python agent class named {_to_class_name(name)} for the following agent:\n\n"
                f"Name: {name}\n"
                f"Description: {description}\n"
                f"Additional requirements: {modification_prompt}\n\n"
                f"Output ONLY the Python class. No markdown fences, no explanation."
            )

        system_prompt = "\n\n".join([PLATFORM_BLOCK, BASE_AGENT_INTERFACE, REFERENCE_EXAMPLE, RULES])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for attempt in range(2):
            try:
                raw = await chat_completion(resolved_model, messages, max_tokens=4096)
                code = _strip_code_fences(raw)
                compile(code, f"<agent:{name}>", "exec")
                logger.info(f"Modify generated for '{name}' on attempt {attempt + 1}")
                return code
            except SyntaxError as e:
                logger.warning(f"Syntax error in modified code (attempt {attempt + 1}): {e}")
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": f"The code has a syntax error: {e}. Fix it and output only the corrected class.",
                    })
            except Exception as e:
                logger.exception(f"Modify failed (attempt {attempt + 1}): {e}")
                if attempt == 1:
                    raise

        raise RuntimeError("Failed to generate valid modified code after 2 attempts")


def _to_class_name(name: str) -> str:
    """Convert a human name to a CamelCase class name."""
    words = re.split(r"[\s_\-]+", name)
    return "".join(w.capitalize() for w in words if w) + "Agent"


def _build_setup_notes(tools: list[str]) -> str:
    notes = []
    if "win32com" in tools:
        notes.append("⚠️  win32com is NOT available in WSL2. Use python-docx/openpyxl instead.")
    if "playwright" in tools:
        notes.append("After installing playwright, run: playwright install chromium")
    if not notes:
        notes.append("No special setup required.")
    return "\n".join(notes)
