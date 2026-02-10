import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.task import Task
from app.schemas.planner import PlannerOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a task planner for an agentic workflow system. Given a user's prompt, decompose it into 2-8 concrete, actionable tasks that can be executed by specialized agents.

Each task must have:
- prompt: A specific, concrete instruction (not vague like "analyze data" but specific like "fetch weather data for San Francisco from the Open-Meteo API for all of 2025")
- agent_type: One of "data_retrieval", "spreadsheet", "code_execution", "report", "general"
- dependencies: Array of 0-based indices of tasks this task depends on (must only reference earlier tasks)

Maximize parallelism by minimizing dependencies. Only add a dependency when a task genuinely needs the output of another task.

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


async def plan_tasks(root_prompt: str, action_id: str, db: AsyncSession) -> list[Task]:
    """Use OpenAI to decompose a prompt into tasks."""
    if not settings.OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY set, using fallback single task")
        return _fallback_tasks(root_prompt, action_id)

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    for attempt in range(2):
        try:
            logger.info(f"[Planner LLM Input] system: {SYSTEM_PROMPT[:200]}...")
            logger.info(f"[Planner LLM Input] user: {root_prompt}")
            completion = await client.beta.chat.completions.parse(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
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
        tasks.append(
            Task(
                id=task_ids[i],
                action_id=action_id,
                prompt=pt.prompt,
                agent_type=pt.agent_type,
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
            dependencies=[],
            status="pending",
        )
    ]
