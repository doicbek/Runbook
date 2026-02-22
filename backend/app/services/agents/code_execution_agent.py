import logging
import re
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

        # If the model returned empty code, retry with an explicit data-fetching fallback
        if not code.strip():
            if log_callback:
                await log_callback("warn", "Empty code returned — retrying with explicit fetch instruction")
            code = await self._generate_code(
                resolved_model, prompt, dependency_outputs, force_fetch=True
            )

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
        force_fetch: bool = False,
    ) -> str:
        """Use LLM to generate Python code for the task."""
        dep_context = ""
        if dependency_outputs:
            for dep_id, output in dependency_outputs.items():
                out_str = str(output) if output else ""
                # Skip dependency outputs that are clearly failures/empty
                if out_str and "No Results" not in out_str and "No content retrieved" not in out_str:
                    dep_context += f"\n\nUpstream task output:\n{out_str[:1500]}"

        # Extract downloadable artifact URLs from dependency context and inject
        # explicit urllib.request.urlretrieve snippets so the LLM doesn't try to
        # open them as local files.
        artifact_download_snippet = self._build_artifact_download_snippet(dep_context)
        if artifact_download_snippet:
            dep_context += artifact_download_snippet

        force_fetch_instruction = ""
        if force_fetch or not dep_context:
            force_fetch_instruction = (
                "\n\nCRITICAL: No upstream data was provided. You MUST write code that fetches "
                "the required data from a public API using urllib.request. Do NOT return empty code. "
                "For temperature/weather tasks, use the Open-Meteo archive API:\n"
                "  import urllib.request, json, urllib.parse\n"
                "  params = urllib.parse.urlencode({'latitude': 37.3382, 'longitude': -121.8863,\n"
                "    'start_date': '2023-01-01', 'end_date': '2023-12-31',\n"
                "    'daily': 'temperature_2m_max,temperature_2m_min,temperature_2m_mean', 'timezone': 'auto'})\n"
                "  url = f'https://archive-api.open-meteo.com/v1/archive?{params}'\n"
                "  data = json.loads(urllib.request.urlopen(url).read())\n"
            )

        code = await chat_completion(
            model,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Python code generator. Write clean, executable Python code "
                        "for the given task.\n\n"
                        "Available libraries: numpy, scipy, matplotlib, pandas, math, statistics, "
                        "urllib.request, urllib.parse, json, datetime, csv, io.\n\n"
                        "IMPORTANT — Data fetching:\n"
                        "- You CAN and SHOULD fetch data from public APIs using urllib.request when the task needs real data.\n"
                        "- If upstream task output is empty, missing, or says 'No Results', fetch the data yourself.\n"
                        "- Free weather API (no key needed): https://archive-api.open-meteo.com/v1/archive\n"
                        "  Params: latitude, longitude, start_date (YYYY-MM-DD), end_date, daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean, timezone=auto\n"
                        "  San Jose CA: latitude=37.3382, longitude=-121.8863\n"
                        "  Example: import urllib.request, json; url='https://archive-api.open-meteo.com/v1/archive?latitude=37.3382&longitude=-121.8863&start_date=2023-01-01&end_date=2023-12-31&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean&timezone=auto'; data=json.loads(urllib.request.urlopen(url).read())\n\n"
                        "IMPORTANT — Artifact files from upstream tasks:\n"
                        "- Upstream task artifacts (xlsx, csv, png, etc.) are served via HTTP URLs, NOT available as local files.\n"
                        "- If the user context lists 'ARTIFACT FILES TO DOWNLOAD', you MUST download each file first:\n"
                        "    import urllib.request\n"
                        "    urllib.request.urlretrieve('http://...', 'local_name.ext')\n"
                        "  Then read the local file normally (e.g. pd.read_excel('local_name.ext')).\n"
                        "- NEVER use a bare filename like 'output.xlsx' without first downloading it from its URL.\n\n"
                        "Rules:\n"
                        "- Output ONLY the Python code — no markdown fences, no explanations, no comments about what you're doing\n"
                        "- Always use plt.show() to display plots (it will be intercepted and saved as a file)\n"
                        "- Print key results to stdout\n"
                        "- Use descriptive plot titles, axis labels, and legends\n"
                        "- If structured data is provided in upstream output, parse it from there first\n"
                        "- If upstream data is empty/missing, fetch from a public API — do NOT generate fake data for real-world tasks\n"
                        "- Use LaTeX in matplotlib labels where appropriate (e.g., r'$\\alpha$')\n"
                        "- Handle errors gracefully with try/except"
                    ),
                },
                {"role": "user", "content": f"Task: {prompt}{dep_context}{force_fetch_instruction}"},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        # Strip markdown fences robustly
        code = code.strip()
        code = re.sub(r"^```(?:python|py)?\s*\n?", "", code)
        code = re.sub(r"\n?```\s*$", "", code)
        return code.strip()

    def _build_artifact_download_snippet(self, dep_context: str) -> str:
        """Parse artifact URLs from dependency context and return an explicit download block.

        Looks for markdown links of the form:
          [Download filename.ext](http://localhost:PORT/artifacts/ID/content)
          [filename.ext](http://localhost:PORT/artifacts/ID/content)
          - [file: mime/type](http://localhost:PORT/artifacts/ID/content)
        """
        # Match: text inside brackets + URL inside parentheses pointing to /artifacts/
        pattern = re.compile(
            r'\[([^\]]*?)\]\((https?://[^)]+/artifacts/[^)]+/content)\)'
        )
        downloads = []
        seen_urls = set()
        for match in pattern.finditer(dep_context):
            label = match.group(1).strip()
            url = match.group(2).strip()
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Derive a sensible local filename from the label
            # Labels look like "Download output.xlsx", "file: application/vnd...", "output.png"
            label_clean = re.sub(r"^Download\s+", "", label, flags=re.IGNORECASE).strip()
            # If label doesn't look like a filename, try to guess extension from mime
            if "." not in label_clean or "/" in label_clean:
                # Mime-type label like "file: application/vnd.openxmlformats..."
                if "spreadsheet" in label_clean or "excel" in label_clean:
                    label_clean = "upstream_data.xlsx"
                elif "csv" in label_clean:
                    label_clean = "upstream_data.csv"
                elif "json" in label_clean:
                    label_clean = "upstream_data.json"
                elif "image" in label_clean or "png" in label_clean:
                    label_clean = "upstream_image.png"
                else:
                    label_clean = "upstream_file.bin"

            downloads.append((url, label_clean))

        if not downloads:
            return ""

        lines = ["\n\nARTIFACT FILES TO DOWNLOAD (download these before reading them):"]
        lines.append("import urllib.request")
        for url, filename in downloads:
            lines.append(f'urllib.request.urlretrieve("{url}", "{filename}")')
        lines.append(
            "# After the downloads above, read the files by their local names "
            "(e.g. pd.read_excel('upstream_data.xlsx'))"
        )
        return "\n".join(lines)

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
