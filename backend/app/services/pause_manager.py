"""In-memory pause signal manager for tasks.

Tracks which tasks are paused and stores optional guidance text
provided by the user on resume.
"""

import asyncio
from dataclasses import dataclass, field


@dataclass
class PauseState:
    """State for a paused task."""
    is_paused: bool = False
    guidance: str | None = None
    # Event that gets set when pause is cleared (resume)
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)


class PauseManager:
    """In-memory pause signal store."""

    def __init__(self):
        self._states: dict[str, PauseState] = {}

    def _get_or_create(self, task_id: str) -> PauseState:
        if task_id not in self._states:
            self._states[task_id] = PauseState()
            self._states[task_id].resume_event.set()  # not paused by default
        return self._states[task_id]

    def pause(self, task_id: str) -> None:
        """Set the pause signal for a task."""
        state = self._get_or_create(task_id)
        state.is_paused = True
        state.guidance = None
        state.resume_event.clear()

    def resume(self, task_id: str, guidance: str | None = None) -> None:
        """Clear the pause signal and optionally store guidance text."""
        state = self._get_or_create(task_id)
        state.is_paused = False
        state.guidance = guidance
        state.resume_event.set()

    def is_paused(self, task_id: str) -> bool:
        """Check if a task has a pause signal set."""
        state = self._states.get(task_id)
        return state.is_paused if state else False

    def take_guidance(self, task_id: str) -> str | None:
        """Consume and return any guidance text (returns None if none)."""
        state = self._states.get(task_id)
        if state and state.guidance is not None:
            guidance = state.guidance
            state.guidance = None
            return guidance
        return None

    async def wait_for_resume(self, task_id: str) -> None:
        """Block until the task is resumed."""
        state = self._get_or_create(task_id)
        await state.resume_event.wait()

    def cleanup(self, task_id: str) -> None:
        """Remove state for a task (call when task completes)."""
        self._states.pop(task_id, None)


# Global singleton
pause_manager = PauseManager()
