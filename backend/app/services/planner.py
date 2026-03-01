import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.task import Task
from app.schemas.planner import PlannerOutput, PlannerTask
from app.services.llm_client import get_default_model_for_agent, planner_completion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a task planner for an agentic workflow system. Given a user's prompt, decompose it into 2-8 concrete, actionable tasks that can be executed by specialized agents.

Each task must have:
- prompt: A specific, concrete instruction (not vague like "analyze data" but specific like "fetch weather data for San Francisco from the Open-Meteo API for all of 2025")
- agent_type: One of "data_retrieval", "spreadsheet", "code_execution", "coding", "report", "general", "arxiv_search", "sub_action", "mcp"
- dependencies: Array of 0-based indices of tasks this task depends on (must only reference earlier tasks)
- model: (optional) Override the LLM model for this task. Use "provider/model_id" format. Leave null to use the default for the agent type.

Agent type guidelines:
- "arxiv_search": Search academic papers on arXiv and produce a literature review with citations. Use for any research, survey, or academic paper search task. Produces a markdown summary with [Author et al., Year] citations and arXiv URLs.
- "coding": LLM-driven agentic coding loop in an isolated git worktree. Has tools: read_file, write_file, edit_file, glob, grep, bash. Iteratively plans, writes code, runs tests, and debugs. Use for tasks involving file creation/editing, code writing, debugging, testing, refactoring, or any work that needs to modify files in a repository. Produces a git diff and change summary.
- "code_execution": Execute real Python code in a sandbox. Has access to numpy, scipy, matplotlib, pandas, urllib, and can install packages. Use for data analysis, curve fitting, plotting, computation, and downloading data from APIs. Can fetch data directly using urllib.request.
- "data_retrieval": Fetch data from web APIs, databases, or scrape web pages via web search. Best for general web data. For specialized scientific datasets, prefer code_execution which can install domain-specific packages.
- "spreadsheet": Create or manipulate structured tabular data.
- "report": Generate a formatted markdown report or document synthesizing inputs from other tasks.
- "general": Catch-all for tasks that don't fit other categories.
- "mcp": Agent powered by MCP tool servers. Use when the task requires tools from configured MCP servers (e.g. filesystem operations, database queries, external API calls via MCP).
- "sub_action": Spawn a child action with its own multi-step planner-generated DAG. Use ONLY when a sub-problem is itself so complex that it requires multiple coordinated steps (e.g., a full research-then-analysis sub-workflow, or a multi-stage data pipeline with its own report). The task prompt must clearly describe the goal and expected output. Do NOT use sub_action for simple single-step tasks — prefer a direct agent type instead. Max nesting depth: 3 levels.

Available LLM models and their strengths:
- "openai/gpt-5": Good all-rounder, strong reasoning (default for general tasks)
- "openai/gpt-5-mini": Fast and cheap, good for simple structured tasks
- "anthropic/claude-sonnet-4-5-20250929": Excellent at research synthesis, writing, and long-form content (default for arxiv_search, report)
- "deepseek/deepseek-chat": Best at code generation (default for code_execution)
- "google/gemini-2.0-flash": Fast, good for general tasks

You can set the model field to override the default, or leave it null to use the recommended default per agent type.

Common workflow patterns:
- Research + analysis: arxiv_search → code_execution → report
- Data pipeline: data_retrieval → code_execution → report
- Literature review: arxiv_search → report
- Scientific data: code_execution (download with domain packages) → code_execution (analysis) → report
- Complex sub-problem: sub_action (e.g., "Research and compare 5 ML frameworks, producing a comparison table and recommendation") → report
- Parallel independent investigations: multiple sub_action tasks in parallel → report that synthesizes all findings

IMPORTANT RULES:
- The LAST task must ALWAYS be a "report" task that synthesizes and summarizes all outputs from upstream tasks. Never end with code_execution, data_retrieval, or any non-report task.
- The final report should reference and include key results: data tables, computed values, plots (by describing them), and conclusions.
- Maximize parallelism by minimizing dependencies. Only add a dependency when a task genuinely needs the output of another task.

You MUST call the plan_tasks tool with the structured task list."""

# JSON schema for the plan_tasks tool (matches PlannerOutput)
_PLANNER_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Specific, concrete instruction for this task"},
                    "agent_type": {"type": "string", "description": "One of: data_retrieval, spreadsheet, code_execution, coding, report, general, arxiv_search, sub_action, mcp"},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "0-based indices of tasks this depends on (must reference earlier tasks only)",
                    },
                    "model": {
                        "type": ["string", "null"],
                        "description": "Optional model override in provider/model_id format",
                    },
                },
                "required": ["prompt", "agent_type", "dependencies"],
            },
        },
    },
    "required": ["tasks"],
}


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


async def _get_skills_context(db: AsyncSession) -> str:
    """Return a block of skill summaries to inject into the planner system prompt."""
    try:
        from app.services.agents.agent_skills import get_skills_summary_for_planner
        return await get_skills_summary_for_planner(db)
    except Exception:
        logger.exception("Failed to fetch skills for planner context")
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
    return SYSTEM_PROMPT, "anthropic/claude-opus-4-6", 2


async def plan_tasks(root_prompt: str, action_id: str, db: AsyncSession) -> list[Task]:
    """Use LLM (with tool_use for structured output) to decompose a prompt into tasks."""
    system_prompt_base, model_override, max_retries = await _load_planner_config(db)
    custom_agent_context = await _get_custom_agent_context(db)
    skills_context = await _get_skills_context(db)
    system_prompt = system_prompt_base + custom_agent_context + skills_context

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": root_prompt},
    ]

    for attempt in range(max(max_retries, 1)):
        try:
            logger.info(f"[Planner LLM Input] model_override={model_override} system: {system_prompt[:200]}...")
            logger.info(f"[Planner LLM Input] user: {root_prompt}")
            result = await planner_completion(
                messages,
                tool_name="plan_tasks",
                tool_schema=_PLANNER_TOOL_SCHEMA,
                model_override=model_override,
            )
            if result is None:
                logger.warning(f"Planner returned no tool call on attempt {attempt + 1}")
                continue

            # Parse tool call result into PlannerOutput
            tasks_data = result.get("tasks", [])
            parsed = PlannerOutput(
                tasks=[PlannerTask(**t) for t in tasks_data]
            )
            logger.info(f"[Planner LLM Output] {len(parsed.tasks)} tasks: {[t.prompt[:60] for t in parsed.tasks]}")
            if _validate_dag(parsed):
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
