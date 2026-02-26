"""Git worktree manager for coding agent workspaces.

Creates and manages git worktrees so coding tasks run in isolated workspaces.
"""

import asyncio
import os
import shutil
from pathlib import Path


def _get_repo_path() -> str:
    """Get the target repository path from environment variable."""
    repo_path = os.environ.get("WORKDECK_REPO_PATH", "")
    if not repo_path:
        raise ValueError(
            "WORKDECK_REPO_PATH environment variable is not set. "
            "Set it to the path of the git repository to use for worktrees."
        )
    return repo_path


def _short_id(task_id: str) -> str:
    """Get first 8 chars of a task ID for branch naming."""
    return task_id[:8]


async def create_worktree(task_id: str, repo_path: str | None = None) -> tuple[str, str]:
    """Create a git worktree for a task.

    Args:
        task_id: The task ID to create a worktree for.
        repo_path: Path to the git repository. If None, uses WORKDECK_REPO_PATH env var.

    Returns:
        Tuple of (worktree_path, branch_name).

    Raises:
        ValueError: If repo_path is not set or not a git repository.
        RuntimeError: If git worktree creation fails.
    """
    if repo_path is None:
        repo_path = _get_repo_path()

    repo = Path(repo_path)
    if not (repo / ".git").exists():
        raise ValueError(f"Not a git repository: {repo_path}")

    short_id = _short_id(task_id)
    branch_name = f"workdeck/task-{short_id}"
    worktree_dir = repo / ".workdeck" / "worktrees" / task_id
    worktree_path = str(worktree_dir)

    # Ensure parent directory exists
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    # Create worktree with new branch based on HEAD
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", "-b", branch_name, worktree_path,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode().strip()
        # If branch already exists, try adding worktree with existing branch
        if "already exists" in error_msg:
            proc2 = await asyncio.create_subprocess_exec(
                "git", "worktree", "add", worktree_path, branch_name,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, stderr2 = await proc2.communicate()
            if proc2.returncode != 0:
                raise RuntimeError(
                    f"Failed to create worktree: {stderr2.decode().strip()}"
                )
        else:
            raise RuntimeError(f"Failed to create worktree: {error_msg}")

    return worktree_path, branch_name


async def remove_worktree(worktree_path: str) -> None:
    """Remove a git worktree.

    Args:
        worktree_path: Path to the worktree to remove.

    Raises:
        RuntimeError: If git worktree removal fails.
    """
    worktree = Path(worktree_path)
    if not worktree.exists():
        return

    # Find the repo root by looking for .workdeck in parents
    repo_path = None
    for parent in worktree.parents:
        if (parent / ".git").exists():
            repo_path = str(parent)
            break

    if repo_path is None:
        # Fallback: just remove the directory
        shutil.rmtree(worktree_path, ignore_errors=True)
        return

    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "remove", "--force", worktree_path,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        # If git removal fails, try manual cleanup
        shutil.rmtree(worktree_path, ignore_errors=True)
        # Also prune stale worktree entries
        await asyncio.create_subprocess_exec(
            "git", "worktree", "prune",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


async def list_worktrees(repo_path: str | None = None) -> list[dict[str, str]]:
    """List all git worktrees for a repository.

    Args:
        repo_path: Path to the git repository. If None, uses WORKDECK_REPO_PATH env var.

    Returns:
        List of dicts with 'path', 'branch', and 'head' keys.
    """
    if repo_path is None:
        repo_path = _get_repo_path()

    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "list", "--porcelain",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        return []

    worktrees = []
    current: dict[str, str] = {}
    for line in stdout.decode().splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]

    if current:
        worktrees.append(current)

    return worktrees
