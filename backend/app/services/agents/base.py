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
    ) -> dict[str, Any]:
        """Execute the agent's task and return output.

        Args:
            task_id: The task ID being executed
            prompt: The task prompt
            dependency_outputs: Outputs from dependency tasks {task_id: output}
            log_callback: Async callable(level, message) for streaming logs

        Returns:
            dict with at least "summary" key
        """
        ...
