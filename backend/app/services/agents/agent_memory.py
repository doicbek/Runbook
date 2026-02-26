"""Per-agent persistent memory: lessons learned from failures.

Files are stored at backend/data/agent_memory/{agent_type}.md and injected
into the task prompt at runtime so agents can avoid repeating past mistakes.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).parent.parent.parent.parent / "data" / "agent_memory"


def load_memory(agent_type: str) -> str:
    """Return the agent's current memory/lessons. Empty string if none."""
    path = MEMORY_DIR / f"{agent_type}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def save_memory(agent_type: str, content: str) -> None:
    """Write (overwrite) the agent's memory file."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = MEMORY_DIR / f"{agent_type}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"[AgentMemory] Saved lesson for {agent_type}")


async def generate_and_save_lesson(
    agent_type: str,
    task_prompt: str,
    error: str,
) -> None:
    """Call a fast LLM to generate/revise a lesson from a failure and persist it."""
    from app.services.llm_client import chat_completion

    existing = load_memory(agent_type)
    existing_block = (
        f"\n\nExisting lessons to revise (update or expand as needed):\n{existing}"
        if existing
        else ""
    )

    try:
        lesson = await chat_completion(
            "gpt-4o-mini",
            [
                {
                    "role": "system",
                    "content": (
                        f"You are a memory assistant for a `{agent_type}` AI agent. "
                        "Your job is to write concise, actionable lessons that help the agent "
                        "avoid repeating failures. Write in markdown, 1–3 bullet points maximum. "
                        "Be specific about what to do differently, not just what went wrong."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"The agent failed on this task: {task_prompt[:300]}\n"
                        f"Error: {error[:500]}"
                        f"{existing_block}\n\n"
                        "Write (or revise) a concise lesson for this agent to remember."
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.3,
        )
        save_memory(agent_type, lesson.strip())
    except Exception:
        logger.exception(f"[AgentMemory] Failed to generate lesson for {agent_type}")
