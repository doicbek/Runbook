import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agents.base import BaseAgent
from app.services.agents.mock_agent import MockAgent

logger = logging.getLogger(__name__)

_BUILTIN_TYPES = {"arxiv_search", "code_execution"}


def get_agent(agent_type: str) -> BaseAgent:
    """Sync shim — returns builtin or MockAgent. Use get_agent_async for DB-backed custom agents."""
    if agent_type == "arxiv_search":
        from app.services.agents.arxiv_search_agent import ArxivSearchAgent
        return ArxivSearchAgent()
    if agent_type == "code_execution":
        from app.services.agents.code_execution_agent import CodeExecutionAgent
        return CodeExecutionAgent()
    if agent_type == "data_retrieval":
        from app.services.agents.data_retrieval_agent import DataRetrievalAgent
        return DataRetrievalAgent()
    if agent_type == "spreadsheet":
        from app.services.agents.spreadsheet_agent import SpreadsheetAgent
        return SpreadsheetAgent()
    if agent_type == "report":
        from app.services.agents.report_agent import ReportAgent
        return ReportAgent()
    if agent_type == "general":
        from app.services.agents.general_agent import GeneralAgent
        return GeneralAgent()
    return MockAgent(agent_type=agent_type)


async def get_agent_async(agent_type: str, db: AsyncSession) -> BaseAgent:
    """Return the appropriate agent, including DB-backed custom agents.

    DB code always takes precedence — if a builtin has custom code stored, it runs instead.
    Falls back to the native implementation, then MockAgent.
    """
    # Check DB first — allows overriding any builtin with custom code
    try:
        from app.models.agent_definition import AgentDefinition
        result = await db.execute(
            select(AgentDefinition).where(
                AgentDefinition.agent_type == agent_type,
                AgentDefinition.status == "active",
            )
        )
        defn = result.scalar_one_or_none()
        if defn is not None and defn.code is not None:
            return _load_dynamic_agent(defn)
    except Exception:
        logger.exception(f"Failed to load agent '{agent_type}' from DB, falling back")

    # Fall back to native implementations
    if agent_type == "arxiv_search":
        from app.services.agents.arxiv_search_agent import ArxivSearchAgent
        return ArxivSearchAgent()
    if agent_type == "code_execution":
        from app.services.agents.code_execution_agent import CodeExecutionAgent
        return CodeExecutionAgent()
    if agent_type == "data_retrieval":
        from app.services.agents.data_retrieval_agent import DataRetrievalAgent
        return DataRetrievalAgent()
    if agent_type == "spreadsheet":
        from app.services.agents.spreadsheet_agent import SpreadsheetAgent
        return SpreadsheetAgent()
    if agent_type == "report":
        from app.services.agents.report_agent import ReportAgent
        return ReportAgent()
    if agent_type == "general":
        from app.services.agents.general_agent import GeneralAgent
        return GeneralAgent()

    return MockAgent(agent_type=agent_type)


def _load_dynamic_agent(defn: Any) -> BaseAgent:
    """exec() the agent code and return an instantiated agent."""
    from app.services.llm_client import chat_completion, get_default_model_for_agent
    import asyncio

    namespace: dict[str, Any] = {
        "BaseAgent": BaseAgent,
        "chat_completion": chat_completion,
        "get_default_model_for_agent": get_default_model_for_agent,
        "asyncio": asyncio,
        "logging": logging,
        "Any": Any,
        "__builtins__": __builtins__,
    }

    try:
        compiled = compile(defn.code, f"<agent:{defn.agent_type}>", "exec")
        exec(compiled, namespace)  # noqa: S102
    except Exception as e:
        logger.error(f"Failed to exec agent code for '{defn.agent_type}': {e}")
        raise RuntimeError(f"Agent code execution failed: {e}") from e

    # Find the first class that subclasses BaseAgent (excluding BaseAgent itself)
    agent_class = None
    for obj in namespace.values():
        try:
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseAgent)
                and obj is not BaseAgent
            ):
                agent_class = obj
                break
        except TypeError:
            continue

    if agent_class is None:
        raise RuntimeError(
            f"No BaseAgent subclass found in code for agent type '{defn.agent_type}'"
        )

    return agent_class()
