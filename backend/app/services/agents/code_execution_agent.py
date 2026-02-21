import logging
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models import Artifact, TaskOutput
from app.services.agents.base import BaseAgent
from app.services.code_runner import run_code
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)


class CodeExecutionAgent(BaseAgent):
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or get_default_model_for_agent("code_execution")

        if log_callback:
            await log_callback("info", f"Using model: {resolved_model}")

        # Step 1: Generate Python code from the prompt
        if log_callback:
            await log_callback("info", "Generating Python code from task prompt...")

        code = await self._generate_code(resolved_model, prompt, dependency_outputs)

        if log_callback:
            await log_callback("info", f"Generated code ({len(code.splitlines())} lines)")
            # Log first few lines
            for line in code.splitlines()[:10]:
                await log_callback("info", f"  {line}")
            if len(code.splitlines()) > 10:
                await log_callback("info", f"  ... ({len(code.splitlines()) - 10} more lines)")

        # Step 2: Look up the action_id for this task
        async with async_session() as db:
            from app.models import Task
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one()
            action_id = task.action_id

        # Step 3: Execute the code
        if log_callback:
            await log_callback("info", "Executing Python code...")

        exec_result = await run_code(
            task_id=task_id,
            action_id=action_id,
            code=code,
            log_callback=log_callback,
            timeout=120,
        )

        stdout = exec_result["stdout"]
        stderr = exec_result["stderr"]
        exit_code = exec_result["exit_code"]
        files = exec_result["files"]

        if log_callback:
            if exit_code == 0:
                await log_callback("info", f"Code executed successfully. {len(files)} file(s) generated.")
            else:
                await log_callback("error", f"Code failed with exit code {exit_code}")
                if stderr:
                    await log_callback("error", stderr[:500])

        # Step 4: Save artifacts to DB
        artifact_urls = []
        async with async_session() as db:
            # Clean old artifacts for this task
            old_result = await db.execute(
                select(Artifact).where(Artifact.task_id == task_id)
            )
            for old in old_result.scalars().all():
                await db.delete(old)
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

                if log_callback:
                    await log_callback("info", f"Saved artifact: {f['filename']} ({f['mime_type']})")

            # Update TaskOutput artifact_ids if it exists
            to_result = await db.execute(
                select(TaskOutput).where(TaskOutput.task_id == task_id)
            )
            task_output = to_result.scalar_one_or_none()
            if task_output:
                task_output.artifact_ids = [a["id"] for a in artifact_urls]

            await db.commit()

        # Step 5: Build summary directly from code + results
        summary = self._build_summary(code, stdout, stderr, exit_code, artifact_urls)

        return {"summary": summary}

    async def _generate_code(
        self,
        model: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
    ) -> str:
        """Use LLM to generate Python code for the task."""
        dep_context = ""
        if dependency_outputs:
            for dep_id, output in dependency_outputs.items():
                if output:
                    dep_context += f"\n\nUpstream task output:\n{str(output)[:1500]}"

        code = await chat_completion(
            model,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Python code generator. Write clean, executable Python code "
                        "for the given task.\n\n"
                        "Available libraries: numpy, scipy, matplotlib, pandas, math, statistics.\n\n"
                        "Rules:\n"
                        "- Output ONLY the Python code, no markdown fences, no explanations\n"
                        "- Always use plt.show() to display plots (it will be intercepted and saved)\n"
                        "- Print key results to stdout\n"
                        "- Use descriptive plot titles, axis labels, and legends\n"
                        "- If data is provided in the upstream output, parse it from there\n"
                        "- If the task needs external data, generate realistic synthetic data\n"
                        "- Use LaTeX in matplotlib labels where appropriate (e.g., r'$\\alpha$')\n"
                        "- Handle errors gracefully"
                    ),
                },
                {"role": "user", "content": f"Task: {prompt}{dep_context}"},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        # Strip markdown fences if the LLM wraps them anyway
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first and last lines if they're fences
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
        return code

    def _build_summary(
        self,
        code: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        artifact_urls: list[dict],
    ) -> str:
        """Build a markdown summary directly from code + results (no LLM call)."""
        if exit_code != 0:
            return (
                f"## Code Execution Failed\n\n"
                f"```python\n{code}\n```\n\n"
                f"**Error (exit code {exit_code}):**\n```\n{stderr[:1000]}\n```"
            )

        parts = [f"```python\n{code}\n```"]

        if stdout.strip():
            parts.append(f"**Output:**\n```\n{stdout[:2000]}\n```")

        for art in artifact_urls:
            if art["mime_type"].startswith("image/"):
                parts.append(f"![{art['filename']}]({art['url']})")

        return "\n\n".join(parts)
