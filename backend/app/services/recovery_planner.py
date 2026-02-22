import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings
from app.services.llm_client import get_default_model_for_agent

logger = logging.getLogger(__name__)

MAX_RECOVERY_ATTEMPTS = 2


class RecoveryTask(BaseModel):
    prompt: str
    agent_type: str
    model: str | None = None


class RecoveryPlan(BaseModel):
    reasoning: str
    tasks: list[RecoveryTask]


_SYSTEM_PROMPT = """\
You are a recovery planner for a failed agentic workflow step.

A task has just failed. Your job is to propose a replacement approach that is more \
likely to succeed. You may replace the failed task with 1–3 tasks using any combination \
of agent types.

Available agent types:
- "data_retrieval"  : fetch data from web APIs, scrape pages, parse HTML/CSV/JSON
- "code_execution"  : run Python in a sandbox (numpy, scipy, pandas, matplotlib, urllib); \
can fetch from public APIs directly
- "spreadsheet"     : generate .xlsx files using openpyxl
- "report"          : synthesise upstream outputs into a markdown document
- "general"         : chain-of-thought reasoning, analysis, Q&A
- "arxiv_search"    : search academic papers on arXiv
- "sub_action"      : spawn a full child workflow with its own multi-step plan — use \
when the replacement itself requires several coordinated steps

Strategy:
1. If the same agent type failed due to a recoverable error (file not found, API format, \
missing data), try a DIFFERENT agent type that can accomplish the same goal. For example:
   - data_retrieval failed to get weather → use code_execution to fetch directly from \
Open-Meteo API
   - code_execution failed to read a file → adjust the prompt to fetch the data from \
its source URL instead
2. If the task is complex and may need multiple steps itself, use "sub_action".
3. Keep replacement tasks focused on the same goal as the failed task.
4. Output only the minimum tasks needed (prefer 1).
"""


async def plan_recovery(
    root_prompt: str,
    failed_prompt: str,
    failed_agent_type: str,
    error_message: str,
    upstream_summaries: dict[str, str],
) -> list[RecoveryTask]:
    """Return replacement task specs for a failed task, or [] if unable to plan."""
    if not settings.OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY — cannot plan recovery")
        return []

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    upstream_block = ""
    if upstream_summaries:
        parts = [f"- {s[:300]}" for s in upstream_summaries.values() if s]
        if parts:
            upstream_block = "\n\nCompleted upstream task outputs (context):\n" + "\n".join(parts)

    user_msg = (
        f"Overall workflow goal: {root_prompt}\n\n"
        f"Failed task\n"
        f"  Prompt:     {failed_prompt}\n"
        f"  Agent type: {failed_agent_type}\n"
        f"  Error:      {error_message[:600]}"
        f"{upstream_block}\n\n"
        "Propose replacement tasks."
    )

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format=RecoveryPlan,
        )
        plan = completion.choices[0].message.parsed
        if not plan or not plan.tasks:
            logger.warning("Recovery planner returned empty plan")
            return []

        logger.info(
            f"[RecoveryPlanner] {len(plan.tasks)} replacement task(s). "
            f"Reasoning: {plan.reasoning[:120]}"
        )
        # Fill default models
        for t in plan.tasks:
            if not t.model:
                t.model = get_default_model_for_agent(t.agent_type)
        return plan.tasks

    except Exception:
        logger.exception("Recovery planner LLM call failed")
        return []
