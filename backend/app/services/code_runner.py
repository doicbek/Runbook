import asyncio
import logging
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Base directory for storing artifacts
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"


def extract_code_blocks(markdown: str) -> list[dict]:
    """Extract fenced code blocks from markdown output.

    Returns list of {language, code} dicts.
    Matches ```python and ```py blocks.
    """
    pattern = r"```(?:python|py)\s*\n(.*?)```"
    matches = re.findall(pattern, markdown, re.DOTALL)
    return [{"language": "python", "code": match.strip()} for match in matches]


def _prepare_code(code: str, work_dir: str) -> str:
    """Prepare Python code for safe execution.

    - Sets matplotlib to non-interactive Agg backend
    - Replaces plt.show() with plt.savefig()
    """
    lines = []
    # Inject matplotlib backend switch at the very top
    lines.append("import matplotlib; matplotlib.use('Agg')")
    lines.append("")

    plot_counter = 0
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped == "plt.show()" or stripped == "plt.show( )":
            # Replace with savefig
            indent = line[: len(line) - len(line.lstrip())]
            save_path = os.path.join(work_dir, f"output_plot_{plot_counter}.png")
            lines.append(
                f"{indent}plt.savefig(r'{save_path}', dpi=150, bbox_inches='tight')"
            )
            lines.append(f"{indent}plt.close()")
            plot_counter += 1
        elif "plt.show()" in stripped:
            # Handle inline plt.show() in more complex lines
            indent = line[: len(line) - len(line.lstrip())]
            save_path = os.path.join(work_dir, f"output_plot_{plot_counter}.png")
            lines.append(
                f"{indent}plt.savefig(r'{save_path}', dpi=150, bbox_inches='tight')"
            )
            lines.append(f"{indent}plt.close()")
            plot_counter += 1
        else:
            lines.append(line)

    return "\n".join(lines)


ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".svg", ".gif",
    ".csv", ".json", ".html", ".txt",
    ".pdf", ".xlsx", ".md",
}


def _detect_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _detect_artifact_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type in ("text/markdown", "text/x-markdown"):
        return "markdown"
    return "file"


async def run_code(
    task_id: str,
    action_id: str,
    code: str,
    log_callback: Callable[[str, str], Awaitable[None]] | None = None,
    timeout: int = 60,
) -> dict:
    """Execute Python code in a subprocess and capture outputs.

    Args:
        task_id: The task this execution belongs to
        action_id: The action this execution belongs to
        code: Python source code to execute
        log_callback: Optional async callback for streaming log lines
        timeout: Execution timeout in seconds

    Returns:
        {stdout, stderr, exit_code, files: [{path, filename, mime_type, size, type}]}
    """
    # Create work directory for this execution
    work_dir = ARTIFACTS_DIR / action_id / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Clean up old generated files from previous runs
    for f in work_dir.iterdir():
        if f.suffix in ALLOWED_EXTENSIONS:
            f.unlink()

    # Prepare and write the script
    prepared_code = _prepare_code(code, str(work_dir))
    script_path = work_dir / "script.py"
    script_path.write_text(prepared_code, encoding="utf-8")

    if log_callback:
        await log_callback("info", "Starting code execution...")

    try:
        process = await asyncio.create_subprocess_exec(
            "python3",
            str(script_path),
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            if log_callback:
                await log_callback("error", f"Code execution timed out after {timeout}s")
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "exit_code": -1,
                "files": [],
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = process.returncode or 0

        # Log output
        if log_callback:
            if stdout.strip():
                for line in stdout.strip().split("\n")[:50]:  # Cap at 50 lines
                    await log_callback("info", line)
            if stderr.strip():
                for line in stderr.strip().split("\n")[:20]:
                    await log_callback("error", line)
            if exit_code == 0:
                await log_callback("info", "Code execution completed successfully")
            else:
                await log_callback("error", f"Code exited with code {exit_code}")

    except Exception as e:
        logger.exception(f"Failed to execute code for task {task_id}")
        if log_callback:
            await log_callback("error", f"Execution error: {e}")
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "files": [],
        }

    # Scan for generated files
    files = []
    for f in work_dir.iterdir():
        if f.name == "script.py":
            continue
        if f.suffix in ALLOWED_EXTENSIONS and f.is_file():
            mime_type = _detect_mime_type(str(f))
            files.append({
                "path": str(f),
                "filename": f.name,
                "mime_type": mime_type,
                "size": f.stat().st_size,
                "type": _detect_artifact_type(mime_type),
            })

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "files": files,
    }
