from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine


class BaseAgent(ABC):
    mcp_config: dict | None = None
    supports_streaming: bool = False
    # Set by executor before execute() — agents call this to publish LLM chunks
    stream_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None

    @abstractmethod
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Execute the agent's task and return output.

        Args:
            task_id: The task ID being executed
            prompt: The task prompt
            dependency_outputs: Outputs from dependency tasks {task_id: output}
            log_callback: Async callable(level, message) for streaming logs
            model: LLM model to use (e.g. "openai/gpt-4o")

        Returns:
            dict with at least "summary" key
        """
        ...
