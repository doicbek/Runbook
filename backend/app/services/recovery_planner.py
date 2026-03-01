import logging

from pydantic import BaseModel

from app.services.llm_client import get_default_model_for_agent, planner_completion

logger = logging.getLogger(__name__)

MAX_RECOVERY_ATTEMPTS = 2
MAX_FULL_REPLANS = 1  # full plan regeneration attempts after per-task recovery is exhausted


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

You MUST call the plan_recovery tool with your proposed replacement tasks."""

# JSON schema for the plan_recovery tool (matches RecoveryPlan)
_RECOVERY_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Explanation of why the task failed and the recovery strategy",
        },
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Specific instruction for this replacement task"},
                    "agent_type": {"type": "string", "description": "One of: data_retrieval, code_execution, spreadsheet, report, general, arxiv_search, sub_action"},
                    "model": {
                        "type": ["string", "null"],
                        "description": "Optional model override in provider/model_id format",
                    },
                },
                "required": ["prompt", "agent_type"],
            },
        },
    },
    "required": ["reasoning", "tasks"],
}


async def plan_recovery(
    root_prompt: str,
    failed_prompt: str,
    failed_agent_type: str,
    error_message: str,
    upstream_summaries: dict[str, str],
) -> list[RecoveryTask]:
    """Return replacement task specs for a failed task, or [] if unable to plan."""
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
        result = await planner_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            tool_name="plan_recovery",
            tool_schema=_RECOVERY_TOOL_SCHEMA,
        )
        if not result or not result.get("tasks"):
            logger.warning("Recovery planner returned empty plan")
            return []

        plan = RecoveryPlan(**result)
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
