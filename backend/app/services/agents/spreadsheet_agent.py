import logging
import re
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models import Artifact, TaskOutput, Task
from app.services.agents.base import BaseAgent
from app.services.code_runner import run_code
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)


class SpreadsheetAgent(BaseAgent):
    """
    Real spreadsheet agent: uses an LLM to generate openpyxl Python code,
    executes it in a sandboxed subprocess, and saves the resulting .xlsx file
    as a downloadable artifact. Also generates a markdown table preview.
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
        resolved_model = model or get_default_model_for_agent("spreadsheet")

        async def log(level: str, msg: str):
            if log_callback:
                await log_callback(level, msg)

        await log("info", f"Spreadsheet Agent | model={resolved_model}")
        await log("info", f"Task: {prompt[:140]}")

        # ── 1. Understand the data from deps ─────────────────────────────────
        await log("info", "Analysing dependency outputs for data...")
        data_summary = self._extract_dep_context(dependency_outputs)

        # ── 2. Generate openpyxl code ─────────────────────────────────────────
        await log("info", "Generating spreadsheet code...")
        code = await self._generate_code(resolved_model, prompt, data_summary)
        line_count = len(code.splitlines())
        await log("info", f"Generated {line_count}-line openpyxl script")
        for line in code.splitlines()[:8]:
            await log("info", f"  {line}")
        if line_count > 8:
            await log("info", f"  ... ({line_count - 8} more lines)")

        # ── 3. Get action_id ──────────────────────────────────────────────────
        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one()
            action_id = task.action_id

        # ── 4. Execute code ───────────────────────────────────────────────────
        await log("info", "Executing spreadsheet code...")
        exec_result = await run_code(
            task_id=task_id,
            action_id=action_id,
            code=code,
            log_callback=log_callback,
            timeout=60,
        )

        stdout = exec_result["stdout"]
        stderr = exec_result["stderr"]
        exit_code = exec_result["exit_code"]
        files = exec_result["files"]

        xlsx_files = [f for f in files if f["filename"].endswith(".xlsx")]
        if exit_code == 0:
            await log("info", f"Execution succeeded. {len(xlsx_files)} .xlsx file(s) produced.")
        else:
            await log("error", f"Execution failed (exit {exit_code}). Attempting recovery...")
            # Retry once with the error message
            code = await self._generate_code(
                resolved_model, prompt, data_summary,
                error_hint=stderr[:500] if stderr else "Unknown error"
            )
            exec_result = await run_code(
                task_id=task_id,
                action_id=action_id,
                code=code,
                log_callback=log_callback,
                timeout=60,
            )
            stdout = exec_result["stdout"]
            stderr = exec_result["stderr"]
            exit_code = exec_result["exit_code"]
            files = exec_result["files"]
            xlsx_files = [f for f in files if f["filename"].endswith(".xlsx")]

        # ── 5. Save artifacts ─────────────────────────────────────────────────
        artifact_urls: list[dict] = []
        async with async_session() as db:
            old = await db.execute(select(Artifact).where(Artifact.task_id == task_id))
            for a in old.scalars().all():
                await db.delete(a)
            await db.flush()

            for f in files:
                artifact = Artifact(
                    task_id=task_id,
                    action_id=action_id,
                    type=f["type"],
                    mime_type=f["mime_type"],
                    storage_path=f["path"],
                    size_bytes=f["size"],
                )
                db.add(artifact)
                await db.flush()
                await db.refresh(artifact)
                url = f"http://localhost:8001/artifacts/{artifact.id}/content"
                artifact_urls.append({
                    "id": artifact.id,
                    "url": url,
                    "type": f["type"],
                    "mime_type": f["mime_type"],
                    "filename": f["filename"],
                })
                await log("info", f"Saved artifact: {f['filename']} ({f['mime_type']})")

            to_result = await db.execute(select(TaskOutput).where(TaskOutput.task_id == task_id))
            task_output = to_result.scalar_one_or_none()
            if task_output:
                task_output.artifact_ids = [a["id"] for a in artifact_urls]

            await db.commit()

        await log("info", "Done.")
        summary = self._build_summary(code, stdout, stderr, exit_code, artifact_urls, xlsx_files)
        return {"summary": summary}

    # ── Code generation ───────────────────────────────────────────────────────

    def _extract_dep_context(self, dep_outputs: dict) -> str:
        if not dep_outputs:
            return ""
        parts = []
        for v in dep_outputs.values():
            if v:
                parts.append(str(v)[:2000])
        return "\n\n---\n\n".join(parts) if parts else ""

    async def _generate_code(
        self,
        model: str,
        prompt: str,
        data_context: str,
        error_hint: str | None = None,
    ) -> str:
        system = (
            "You are a Python code generator specialising in spreadsheet creation with openpyxl.\n\n"
            "Rules:\n"
            "- Output ONLY executable Python code — no markdown fences, no explanations\n"
            "- Use openpyxl to create a real .xlsx file named 'output.xlsx' in the current directory\n"
            "- Always use: from openpyxl import Workbook; from openpyxl.styles import Font, PatternFill, Alignment, Border, Side\n"
            "- Bold the header row; use a light blue fill (#C9DAF8) for headers\n"
            "- Auto-size columns using: ws.column_dimensions[col].width = max_width + 2\n"
            "- Add a second sheet named 'Summary' with key statistics (count, min, max, mean for numeric columns)\n"
            "- Freeze the top row: ws.freeze_panes = 'A2'\n"
            "- Print a markdown table preview to stdout (first 10 rows) so the user can see the data\n"
            "- If upstream data contains tables (markdown | ... | format), parse them as the input dataset\n"
            "- If no data is provided, generate realistic synthetic data relevant to the task (at least 20 rows)\n"
            "- Handle errors gracefully; never crash silently\n"
            "- Import only stdlib + openpyxl + pandas (all are available)\n"
        )

        user_parts = [f"Task: {prompt}"]
        if data_context:
            user_parts.append(f"\nUpstream task outputs:\n{data_context[:4000]}")
        if error_hint:
            user_parts.append(
                f"\nPrevious attempt failed with this error — fix it:\n{error_hint}"
            )

        raw = await chat_completion(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(user_parts)},
            ],
            max_tokens=2500,
            temperature=0.1,
        )
        return self._strip_fences(raw)

    @staticmethod
    def _strip_fences(code: str) -> str:
        code = code.strip()
        code = re.sub(r"^```(?:python|py)?\s*\n", "", code)
        code = re.sub(r"\n```\s*$", "", code)
        return code.strip()

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary(
        self,
        code: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        artifact_urls: list[dict],
        xlsx_files: list[dict],
    ) -> str:
        if exit_code != 0:
            return (
                "## Spreadsheet Generation Failed\n\n"
                f"```python\n{code}\n```\n\n"
                f"**Error:**\n```\n{stderr[:800]}\n```"
            )

        parts = []

        # Download links for .xlsx files
        for art in artifact_urls:
            if art["filename"].endswith(".xlsx"):
                parts.append(
                    f"**[Download {art['filename']}]({art['url']})**  \n"
                    f"*(right-click → Save As if it opens in browser)*"
                )

        # Stdout preview (markdown table printed by the script)
        if stdout.strip():
            parts.append(f"### Preview\n\n{stdout.strip()[:3000]}")

        # Code block (collapsed context)
        parts.append(f"<details><summary>View generated code</summary>\n\n```python\n{code}\n```\n\n</details>")

        return "\n\n".join(parts) if parts else f"Spreadsheet created.\n\n```python\n{code}\n```"
