import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.task import Task
from app.schemas.planner import PlannerOutput
from app.services.llm_client import get_default_model_for_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a task planner for an agentic workflow system. Given a user's prompt, decompose it into 2-8 concrete, actionable tasks that can be executed by specialized agents.

Each task must have:
- prompt: A specific, concrete instruction (not vague like "analyze data" but specific like "fetch weather data for San Francisco from the Open-Meteo API for all of 2025")
- agent_type: One of "data_retrieval", "spreadsheet", "code_execution", "report", "general", "arxiv_search"
- dependencies: Array of 0-based indices of tasks this task depends on (must only reference earlier tasks)
- model: (optional) Override the LLM model for this task. Use "provider/model_id" format. Leave null to use the default for the agent type.

Agent type guidelines:
- "arxiv_search": Search academic papers on arXiv and produce a literature review with citations. Use for any research, survey, or academic paper search task. Produces a markdown summary with [Author et al., Year] citations and arXiv URLs.
- "code_execution": Execute real Python code in a sandbox. Has access to numpy, scipy, matplotlib, pandas. Use for data analysis, curve fitting, plotting, and computation. Produces code blocks that can be run.
- "data_retrieval": Fetch data from web APIs, databases, or scrape web pages.
- "spreadsheet": Create or manipulate structured tabular data.
- "report": Generate a formatted markdown report or document synthesizing inputs from other tasks.
- "general": Catch-all for tasks that don't fit other categories.

Available LLM models and their strengths:
- "openai/gpt-4o": Good all-rounder (default for general tasks)
- "openai/gpt-4o-mini": Fast and cheap, good for simple structured tasks (default for data_retrieval, spreadsheet)
- "anthropic/claude-sonnet-4-5-20250929": Excellent at research synthesis, writing, and long-form content (default for arxiv_search, report)
- "deepseek/deepseek-chat": Best at code generation (default for code_execution)
- "google/gemini-2.0-flash": Fast, good for general tasks

You can set the model field to override the default, or leave it null to use the recommended default per agent type.

Common workflow patterns:
- Research + analysis: arxiv_search → code_execution → report
- Data pipeline: data_retrieval → code_execution → report
- Literature review: arxiv_search → report

IMPORTANT RULES:
- The LAST task must ALWAYS be a "report" task that synthesizes and summarizes all outputs from upstream tasks. Never end with code_execution, data_retrieval, or any non-report task.
- The final report should reference and include key results: data tables, computed values, plots (by describing them), and conclusions.
- Maximize parallelism by minimizing dependencies. Only add a dependency when a task genuinely needs the output of another task.

Respond with a JSON object matching the schema exactly."""


def _validate_dag(output: PlannerOutput) -> bool:
    """Validate DAG: no cycles, no forward references, no empty prompts."""
    n = len(output.tasks)
    if n == 0:
        return False
    for i, task in enumerate(output.tasks):
        if not task.prompt.strip():
            return False
        for dep in task.dependencies:
            if dep < 0 or dep >= i:
                return False
    return True


async def _get_custom_agent_context(db: AsyncSession) -> str:
    """Return a block describing active custom agents to inject into the system prompt."""
    try:
        from sqlalchemy import select
        from app.models.agent_definition import AgentDefinition

        result = await db.execute(
            select(AgentDefinition).where(
                AgentDefinition.is_builtin == False,  # noqa: E712
                AgentDefinition.status == "active",
            )
        )
        custom_agents = result.scalars().all()
        if not custom_agents:
            return ""

        lines = ["\n\nCustom agent types available (user-defined):"]
        for agent in custom_agents:
            lines.append(f'- "{agent.agent_type}": {agent.description}')
        lines.append("\nYou may assign tasks to these custom agent types when appropriate.")
        return "\n".join(lines)
    except Exception:
        logger.exception("Failed to fetch custom agents for planner context")
        return ""


async def _load_planner_config(db: AsyncSession) -> tuple[str, str, int]:
    """Returns (system_prompt, model, max_retries) from DB config, falling back to defaults."""
    try:
        from sqlalchemy import select
        from app.models.planner_config import PlannerConfig
        result = await db.execute(select(PlannerConfig).where(PlannerConfig.id == "default"))
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg.system_prompt, cfg.model, cfg.max_retries
    except Exception:
        logger.exception("Failed to load planner config from DB, using defaults")
    return SYSTEM_PROMPT, settings.OPENAI_MODEL, 2


async def plan_tasks(root_prompt: str, action_id: str, db: AsyncSession) -> list[Task]:
    """Use OpenAI to decompose a prompt into tasks."""
    if not settings.OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY set, using fallback single task")
        return _fallback_tasks(root_prompt, action_id)

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    system_prompt_base, model, max_retries = await _load_planner_config(db)
    custom_agent_context = await _get_custom_agent_context(db)
    system_prompt = system_prompt_base + custom_agent_context

    for attempt in range(max(max_retries, 1)):
        try:
            logger.info(f"[Planner LLM Input] model={model} system: {system_prompt[:200]}...")
            logger.info(f"[Planner LLM Input] user: {root_prompt}")
            completion = await client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": root_prompt},
                ],
                response_format=PlannerOutput,
            )
            parsed = completion.choices[0].message.parsed
            if parsed:
                logger.info(f"[Planner LLM Output] {len(parsed.tasks)} tasks: {[t.prompt[:60] for t in parsed.tasks]}")
            if parsed and _validate_dag(parsed):
                return _convert_to_models(parsed, action_id)
            logger.warning(f"Invalid DAG on attempt {attempt + 1}, retrying")
        except Exception:
            logger.exception(f"Planner failed on attempt {attempt + 1}")

    logger.warning("Planner failed, using fallback")
    return _fallback_tasks(root_prompt, action_id)


def _convert_to_models(output: PlannerOutput, action_id: str) -> list[Task]:
    """Convert planner output to Task models, mapping indices to UUIDs."""
    task_ids = [str(uuid.uuid4()) for _ in output.tasks]
    tasks = []
    for i, pt in enumerate(output.tasks):
        dep_ids = [task_ids[d] for d in pt.dependencies]
        model = pt.model if pt.model else get_default_model_for_agent(pt.agent_type)
        tasks.append(
            Task(
                id=task_ids[i],
                action_id=action_id,
                prompt=pt.prompt,
                agent_type=pt.agent_type,
                model=model,
                dependencies=dep_ids,
                status="pending",
            )
        )
    return tasks


def _fallback_tasks(root_prompt: str, action_id: str) -> list[Task]:
    """Return a single task with the root prompt as fallback."""
    return [
        Task(
            action_id=action_id,
            prompt=root_prompt,
            agent_type="general",
            model=get_default_model_for_agent("general"),
            dependencies=[],
            status="pending",
        )
    ]
