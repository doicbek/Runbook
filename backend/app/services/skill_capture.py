"""Fire-and-forget skill capture triggers extracted from executor.py.

Each function wraps the corresponding agent_skills generator and schedules
it as a background task so the executor doesn't block on skill generation.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def capture_success_skill(
    agent_type: str,
    task_prompt: str,
    output_summary: str,
    task_id: str,
    action_id: str,
) -> None:
    """Schedule a fire-and-forget task to generate a learning skill from success."""
    try:
        from app.services.agents.agent_skills import generate_skill_from_success

        asyncio.create_task(generate_skill_from_success(
            agent_type=agent_type,
            task_prompt=task_prompt,
            output_summary=output_summary,
            task_id=task_id,
            action_id=action_id,
        ))
    except Exception:
        logger.debug(f"[SkillCapture] Failed to schedule success skill for task {task_id}")


def capture_failure_skill(
    agent_type: str,
    task_prompt: str,
    error: str,
    task_id: str,
    action_id: str,
) -> None:
    """Schedule a fire-and-forget task to generate an error pattern skill from failure."""
    try:
        from app.services.agents.agent_skills import generate_skill_from_failure

        asyncio.create_task(generate_skill_from_failure(
            agent_type=agent_type,
            task_prompt=task_prompt,
            error=error,
            task_id=task_id,
            action_id=action_id,
        ))
    except Exception:
        logger.debug(f"[SkillCapture] Failed to schedule failure skill for task {task_id}")


def capture_correction_skill(
    agent_type: str,
    task_prompt: str,
    error: str,
    successful_output: str,
    task_id: str,
    action_id: str,
) -> None:
    """Schedule a fire-and-forget task to generate a correction skill from recovery."""
    try:
        from app.services.agents.agent_skills import generate_correction_skill

        asyncio.create_task(generate_correction_skill(
            agent_type=agent_type,
            task_prompt=task_prompt,
            error=error,
            successful_output=successful_output,
            task_id=task_id,
            action_id=action_id,
        ))
    except Exception:
        logger.debug(f"[SkillCapture] Failed to schedule correction skill for task {task_id}")
