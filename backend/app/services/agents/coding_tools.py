"""Standalone tool functions for the coding agent.

All file operations are sandboxed to a workspace directory.
"""

import asyncio
import difflib
import fnmatch
import os
import re
from pathlib import Path


def _resolve_and_validate(path: str, workspace: str) -> Path:
    """Resolve a path and validate it is within the workspace.

    Args:
        path: Relative or absolute path to resolve.
        workspace: The workspace root directory.

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: If the resolved path is outside the workspace.
    """
    workspace_path = Path(workspace).resolve()
    # If path is relative, resolve against workspace
    if not os.path.isabs(path):
        resolved = (workspace_path / path).resolve()
    else:
        resolved = Path(path).resolve()

    # Check that the resolved path is within the workspace
    try:
        resolved.relative_to(workspace_path)
    except ValueError:
        raise ValueError(
            f"Path escape detected: '{path}' resolves to '{resolved}' "
            f"which is outside workspace '{workspace_path}'"
        )

    return resolved


async def read_file(path: str, workspace: str) -> str:
    """Read a file from the workspace.

    Args:
        path: File path (relative to workspace or absolute).
        workspace: The workspace root directory.

    Returns:
        File contents as a string.

    Raises:
        ValueError: If path is outside workspace.
        FileNotFoundError: If file does not exist.
    """
    resolved = _resolve_and_validate(path, workspace)
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return resolved.read_text(encoding="utf-8", errors="replace")


async def write_file(path: str, content: str, workspace: str) -> str:
    """Write content to a file in the workspace.

    Creates parent directories if they don't exist.

    Args:
        path: File path (relative to workspace or absolute).
        content: Content to write.
        workspace: The workspace root directory.

    Returns:
        Confirmation message with the file path.

    Raises:
        ValueError: If path is outside workspace.
    """
    resolved = _resolve_and_validate(path, workspace)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {resolved.relative_to(Path(workspace).resolve())}"


async def edit_file(path: str, old_str: str, new_str: str, workspace: str) -> str:
    """Edit a file by replacing old_str with new_str.

    Args:
        path: File path (relative to workspace or absolute).
        old_str: The exact string to find and replace.
        new_str: The replacement string.
        workspace: The workspace root directory.

    Returns:
        Unified diff of the change.

    Raises:
        ValueError: If path is outside workspace or old_str not found.
        FileNotFoundError: If file does not exist.
    """
    resolved = _resolve_and_validate(path, workspace)
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    original = resolved.read_text(encoding="utf-8", errors="replace")

    if old_str not in original:
        raise ValueError(
            f"old_str not found in {path}. "
            f"Make sure the string matches exactly (including whitespace)."
        )

    # Count occurrences
    count = original.count(old_str)
    updated = original.replace(old_str, new_str, 1)
    resolved.write_text(updated, encoding="utf-8")

    # Compute unified diff
    rel_path = str(resolved.relative_to(Path(workspace).resolve()))
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
    )
    diff_text = "".join(diff)

    note = ""
    if count > 1:
        note = f" (Note: {count} occurrences found, replaced first only)"

    return diff_text + note if diff_text else f"No diff generated{note}"


async def glob_search(pattern: str, workspace: str) -> list[str]:
    """Search for files matching a glob pattern in the workspace.

    Args:
        pattern: Glob pattern (e.g., '**/*.py', 'src/**/*.ts').
        workspace: The workspace root directory.

    Returns:
        List of matching file paths relative to workspace.
    """
    workspace_path = Path(workspace).resolve()
    matches = sorted(workspace_path.glob(pattern))
    results = []
    for m in matches:
        if m.is_file():
            results.append(str(m.relative_to(workspace_path)))
    return results


async def grep_search(
    pattern: str,
    workspace: str,
    glob_filter: str | None = None,
) -> list[dict]:
    """Search file contents for a regex pattern.

    Args:
        pattern: Regex pattern to search for.
        workspace: The workspace root directory.
        glob_filter: Optional glob pattern to filter files (e.g., '*.py').

    Returns:
        List of dicts with 'file', 'line', 'text' keys.
    """
    workspace_path = Path(workspace).resolve()
    results: list[dict] = []
    regex = re.compile(pattern)

    # Collect files to search
    if glob_filter:
        files = sorted(workspace_path.rglob(glob_filter))
    else:
        files = sorted(workspace_path.rglob("*"))

    for fpath in files:
        if not fpath.is_file():
            continue
        # Skip binary files and hidden/git directories
        rel = str(fpath.relative_to(workspace_path))
        if rel.startswith(".git/") or "/.git/" in rel:
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, PermissionError):
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                results.append({
                    "file": rel,
                    "line": i,
                    "text": line.rstrip(),
                })
        # Cap results to prevent massive output
        if len(results) >= 500:
            break

    return results


_BLOCKED_COMMANDS = {"rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){ :|:& };:", "fork bomb"}
_BLOCKED_PATTERNS = [
    r"\bcurl\b.*\|.*\bsh\b",  # curl | sh
    r"\bwget\b.*\|.*\bsh\b",  # wget | sh
    r"\bnc\b.*-[el]",         # netcat listeners
    r"\bchmod\b.*777\s*/",    # chmod 777 on root
    r"\benv\b\s*$",           # bare env (leaks secrets)
    r"cat\s+/etc/(passwd|shadow)",
    r"\$[({].*API_KEY",       # accessing API keys
    r"os\.environ",           # accessing env vars
]

# Sensitive environment variables to strip from subprocess environments
_BASH_SENSITIVE_ENV_VARS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "DATABASE_URL"}


async def bash_run(
    command: str,
    workspace: str,
    timeout: int = 120,
) -> dict:
    """Execute a shell command in the workspace directory.

    Args:
        command: Shell command to execute.
        workspace: The workspace root directory (used as cwd).
        timeout: Timeout in seconds (default 120).

    Returns:
        Dict with 'stdout', 'stderr', 'exit_code' keys.
    """
    import re as _re

    # Check against blocked commands
    for blocked in _BLOCKED_COMMANDS:
        if blocked in command:
            return {"stdout": "", "stderr": f"Command blocked by security policy: matches restricted command", "exit_code": -1}

    # Check against blocked patterns
    for pattern in _BLOCKED_PATTERNS:
        if _re.search(pattern, command, _re.IGNORECASE):
            return {"stdout": "", "stderr": f"Command blocked by security policy: matches restricted pattern", "exit_code": -1}

    workspace_path = Path(workspace).resolve()
    if not workspace_path.is_dir():
        raise ValueError(f"Workspace directory does not exist: {workspace}")

    # Build a clean env that strips secrets
    clean_env = {k: v for k, v in os.environ.items() if k not in _BASH_SENSITIVE_ENV_VARS}

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "exit_code": -1,
        }
