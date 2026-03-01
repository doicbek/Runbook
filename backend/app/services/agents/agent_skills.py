"""Self-improving agent skills system.

Inspired by github.com/peterskoett/self-improving-agent — captures learnings,
error patterns, corrections, and best practices to enable continuous improvement.

Skills are stored in the `agent_skills` table with four categories:
- learning: reusable workflow knowledge from successes
- error_pattern: recurring failure patterns with avoidance strategies
- correction: fixes discovered after failures (what to do instead)
- best_practice: promoted learnings that apply broadly

Key behaviors:
- Recurrence tracking: same pattern_key bumps recurrence_count + last_seen
- Auto-promotion: skills with recurrence >= 3 across 2+ tasks get promoted
- Error reflection: failures produce corrective skills, not just memory files
- Skill refinement: repeated successes refine existing skills instead of duplication
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.agent_skill import AgentSkill
from app.models.skill_relation import SkillConcept, SkillRelation

logger = logging.getLogger(__name__)

# Auto-promotion threshold
_PROMOTION_RECURRENCE = 3


async def generate_skill_from_success(
    agent_type: str,
    task_prompt: str,
    output_summary: str,
    task_id: str,
    action_id: str,
) -> None:
    """Auto-generate or refine a skill from a successful task execution.

    Uses a fast LLM to produce a pattern_key, title, and description.
    If a skill with the same pattern_key exists, bumps recurrence and refines.
    Otherwise creates a new skill.
    """
    from app.services.llm_client import utility_completion

    try:
        raw = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You extract reusable workflow knowledge from a successful task execution.\n"
                        "Output exactly THREE lines:\n"
                        "LINE 1: A stable pattern key — a short snake_case identifier that captures "
                        "the *type* of workflow (not the specific data). Two tasks doing the same "
                        "kind of work should produce the same key. Examples: 'scipy_curve_fit', "
                        "'web_scrape_and_parse', 'pandas_data_cleaning', 'arxiv_literature_review'.\n"
                        "LINE 2: A short title (10-15 words) phrased as an action.\n"
                        "LINE 3: A detailed description (100-300 words) of the approach, tools, "
                        "and steps that worked. Write it as instructions for an agent to follow "
                        "in the future. Be specific about libraries, APIs, data formats, and "
                        "techniques used."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Agent type: {agent_type}\n"
                        f"Task prompt: {task_prompt[:500]}\n"
                        f"Output summary: {output_summary[:800]}"
                    ),
                },
            ],
            max_tokens=600,
            temperature=0.3,
        )

        lines = raw.strip().split("\n", 2)
        if len(lines) < 3:
            logger.warning("[AgentSkills] LLM returned fewer than 3 lines, skipping")
            return

        pattern_key = lines[0].strip().strip('"').strip("'").lower().replace(" ", "_")[:255]
        title = lines[1].strip().strip('"').strip("'")
        description = lines[2].strip()

        if not pattern_key or not title or not description:
            return

        async with async_session() as db:
            # Check for existing skill with same pattern_key
            result = await db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_type == agent_type,
                    AgentSkill.pattern_key == pattern_key,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Refine: bump recurrence, update last_seen, merge description
                existing.recurrence_count += 1
                existing.last_seen = datetime.now(timezone.utc)
                existing.usage_count += 1

                # Refine description if recurrence is low (still learning)
                if existing.recurrence_count <= 5:
                    existing.description = await _refine_description(
                        existing.description, description
                    )

                # Auto-promote if threshold met
                if (
                    existing.recurrence_count >= _PROMOTION_RECURRENCE
                    and existing.status != "promoted"
                ):
                    existing.status = "promoted"
                    existing.category = "best_practice"
                    existing.priority = "high"
                    logger.info(
                        f"[AgentSkills] Promoted skill '{pattern_key}' for {agent_type} "
                        f"(recurrence={existing.recurrence_count})"
                    )

                await db.commit()
                logger.info(
                    f"[AgentSkills] Refined existing skill '{pattern_key}' for {agent_type} "
                    f"(recurrence={existing.recurrence_count})"
                )
            else:
                skill = AgentSkill(
                    agent_type=agent_type,
                    title=title,
                    description=description,
                    source="auto",
                    source_task_id=task_id,
                    source_action_id=action_id,
                    category="learning",
                    priority="medium",
                    pattern_key=pattern_key,
                )
                db.add(skill)
                await db.commit()
                await db.refresh(skill)
                logger.info(f"[AgentSkills] New skill '{pattern_key}' for {agent_type}: {title[:60]}")
                # Fire-and-forget concept extraction
                import asyncio
                asyncio.create_task(extract_concepts_from_skill(skill.id, title, description))

    except Exception:
        logger.exception(f"[AgentSkills] Failed to generate skill for {agent_type}")


async def generate_skill_from_failure(
    agent_type: str,
    task_prompt: str,
    error: str,
    task_id: str,
    action_id: str,
) -> None:
    """Generate an error_pattern or correction skill from a task failure.

    Captures what went wrong and how to avoid it, producing actionable
    corrective knowledge rather than just logging the error.
    """
    from app.services.llm_client import utility_completion

    try:
        raw = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a failure analysis assistant. A task has failed and you must "
                        "capture a reusable lesson.\n"
                        "Output exactly FOUR lines:\n"
                        "LINE 1: A stable pattern key (snake_case) capturing the *type* of error. "
                        "Two similar failures should produce the same key. Examples: "
                        "'missing_api_key', 'import_not_installed', 'timeout_large_dataset', "
                        "'wrong_data_format'.\n"
                        "LINE 2: Priority — one of: low, medium, high, critical. Use 'critical' "
                        "for data loss/security, 'high' for recurring blockers, 'medium' for "
                        "common issues with workarounds, 'low' for edge cases.\n"
                        "LINE 3: A short title (10-15 words) describing the avoidance strategy.\n"
                        "LINE 4: A corrective description (100-200 words) — what went wrong, "
                        "why, and exactly what the agent should do differently next time. "
                        "Be specific: name libraries, API patterns, common pitfalls."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Agent type: {agent_type}\n"
                        f"Task prompt: {task_prompt[:400]}\n"
                        f"Error: {error[:600]}"
                    ),
                },
            ],
            max_tokens=400,
            temperature=0.3,
        )

        lines = raw.strip().split("\n", 3)
        if len(lines) < 4:
            logger.warning("[AgentSkills] Failure LLM returned fewer than 4 lines, skipping")
            return

        pattern_key = lines[0].strip().strip('"').strip("'").lower().replace(" ", "_")[:255]
        priority = lines[1].strip().lower()
        if priority not in ("low", "medium", "high", "critical"):
            priority = "medium"
        title = lines[2].strip().strip('"').strip("'")
        description = lines[3].strip()

        if not pattern_key or not title or not description:
            return

        async with async_session() as db:
            # Check for existing error pattern with same key
            result = await db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_type == agent_type,
                    AgentSkill.pattern_key == pattern_key,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.recurrence_count += 1
                existing.last_seen = datetime.now(timezone.utc)
                # Escalate priority if recurring
                if existing.recurrence_count >= 3 and existing.priority == "medium":
                    existing.priority = "high"
                if existing.recurrence_count >= 5 and existing.priority == "high":
                    existing.priority = "critical"
                # Auto-promote recurring error patterns
                if (
                    existing.recurrence_count >= _PROMOTION_RECURRENCE
                    and existing.status != "promoted"
                ):
                    existing.status = "promoted"
                    logger.info(
                        f"[AgentSkills] Promoted error pattern '{pattern_key}' for {agent_type} "
                        f"(recurrence={existing.recurrence_count})"
                    )
                await db.commit()
                logger.info(
                    f"[AgentSkills] Bumped error pattern '{pattern_key}' for {agent_type} "
                    f"(recurrence={existing.recurrence_count})"
                )
            else:
                skill = AgentSkill(
                    agent_type=agent_type,
                    title=title,
                    description=description,
                    source="error",
                    source_task_id=task_id,
                    source_action_id=action_id,
                    category="error_pattern",
                    priority=priority,
                    pattern_key=pattern_key,
                )
                db.add(skill)
                await db.commit()
                logger.info(f"[AgentSkills] New error pattern '{pattern_key}' for {agent_type}: {title[:60]}")

    except Exception:
        logger.exception(f"[AgentSkills] Failed to generate error skill for {agent_type}")


async def generate_correction_skill(
    agent_type: str,
    task_prompt: str,
    error: str,
    successful_output: str,
    task_id: str,
    action_id: str,
) -> None:
    """Generate a correction skill when a task succeeds after prior failures.

    This captures the *fix* — what worked after earlier attempts failed.
    """
    from app.services.llm_client import utility_completion

    try:
        raw = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "A task initially failed but then succeeded on retry. "
                        "Extract the correction — what fixed the problem.\n"
                        "Output exactly THREE lines:\n"
                        "LINE 1: A stable pattern key (snake_case) for this type of correction.\n"
                        "LINE 2: A short title (10-15 words) describing the fix.\n"
                        "LINE 3: A description (80-200 words) of what went wrong and what fixed it. "
                        "Write as instructions: 'When you encounter X, do Y instead of Z.'"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Agent type: {agent_type}\n"
                        f"Task prompt: {task_prompt[:300]}\n"
                        f"Original error: {error[:400]}\n"
                        f"Successful output: {successful_output[:400]}"
                    ),
                },
            ],
            max_tokens=350,
            temperature=0.3,
        )

        lines = raw.strip().split("\n", 2)
        if len(lines) < 3:
            return

        pattern_key = lines[0].strip().strip('"').strip("'").lower().replace(" ", "_")[:255]
        title = lines[1].strip().strip('"').strip("'")
        description = lines[2].strip()

        if not pattern_key or not title or not description:
            return

        async with async_session() as db:
            result = await db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_type == agent_type,
                    AgentSkill.pattern_key == pattern_key,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.recurrence_count += 1
                existing.last_seen = datetime.now(timezone.utc)
                # If it was an error_pattern, upgrade to correction
                if existing.category == "error_pattern":
                    existing.category = "correction"
                    existing.source = "correction"
                    existing.description = description
                    existing.title = title
                await db.commit()
            else:
                skill = AgentSkill(
                    agent_type=agent_type,
                    title=title,
                    description=description,
                    source="correction",
                    source_task_id=task_id,
                    source_action_id=action_id,
                    category="correction",
                    priority="high",
                    pattern_key=pattern_key,
                )
                db.add(skill)
                await db.commit()
                logger.info(f"[AgentSkills] New correction '{pattern_key}' for {agent_type}: {title[:60]}")

    except Exception:
        logger.exception(f"[AgentSkills] Failed to generate correction skill for {agent_type}")


async def load_skills_for_agent(agent_type: str, db: AsyncSession) -> list[AgentSkill]:
    """Return active skills for an agent type, prioritized for injection.

    Returns promoted skills first, then high-priority, then by recurrence.
    """
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.agent_type == agent_type,
            AgentSkill.is_active == True,  # noqa: E712
        ).order_by(
            # promoted first
            AgentSkill.status.desc(),
            # high/critical before medium/low
            AgentSkill.priority.desc(),
            # most recurrent first
            AgentSkill.recurrence_count.desc(),
        )
    )
    return list(result.scalars().all())


def format_skills_for_prompt(skills: list[AgentSkill]) -> str:
    """Format skills for injection into the agent's task prompt.

    Groups by category for clarity: corrections and error patterns first
    (avoidance), then best practices and learnings (guidance).
    """
    if not skills:
        return ""

    sections: dict[str, list[str]] = {}
    category_order = ["correction", "error_pattern", "best_practice", "learning"]

    for skill in skills:
        cat = skill.category if skill.category in category_order else "learning"
        sections.setdefault(cat, [])
        recurrence_note = f" (seen {skill.recurrence_count}x)" if skill.recurrence_count > 1 else ""
        promoted_note = " [PROMOTED]" if skill.status == "promoted" else ""
        sections[cat].append(
            f"- [{skill.priority.upper()}]{promoted_note}{recurrence_note} {skill.title}: "
            f"{skill.description[:300]}"
        )

    lines = ["[Agent Skills — self-improvement knowledge base]"]

    category_labels = {
        "correction": "Corrections (fixes for known failure patterns — apply these first)",
        "error_pattern": "Error patterns to avoid",
        "best_practice": "Best practices (promoted from repeated successes)",
        "learning": "Learned workflows",
    }

    for cat in category_order:
        if cat in sections:
            lines.append(f"\n### {category_labels.get(cat, cat)}")
            lines.extend(sections[cat][:5])

    return "\n".join(lines)


async def get_skills_summary_for_planner(db: AsyncSession) -> str:
    """Return formatted skill summaries grouped by agent_type for planner injection.

    Promoted/high-priority skills are highlighted.
    """
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.is_active == True,  # noqa: E712
        ).order_by(AgentSkill.agent_type, AgentSkill.recurrence_count.desc())
    )
    skills = result.scalars().all()

    if not skills:
        return ""

    grouped: dict[str, list[AgentSkill]] = {}
    for skill in skills:
        grouped.setdefault(skill.agent_type, []).append(skill)

    lines = ["\nSkills available per agent type (proven workflows and known pitfalls):"]
    for agent_type, agent_skills in grouped.items():
        # Separate promoted/high-priority for emphasis
        highlights = [s for s in agent_skills if s.status == "promoted" or s.priority in ("high", "critical")]
        regular = [s for s in agent_skills if s not in highlights]

        parts = []
        for s in highlights[:3]:
            label = "AVOID" if s.category in ("error_pattern", "correction") else "PROVEN"
            parts.append(f'[{label}] "{s.title}"')
        for s in regular[:3]:
            parts.append(f'"{s.title}"')

        if parts:
            lines.append(f'- "{agent_type}": {" | ".join(parts)}')

    return "\n".join(lines)


async def _refine_description(existing: str, new: str) -> str:
    """Merge an existing skill description with a new observation."""
    from app.services.llm_client import utility_completion

    try:
        refined = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Merge two descriptions of the same workflow into a single, "
                        "improved description. Keep the best details from both. "
                        "Output only the merged description (100-300 words), no preamble."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Existing description:\n{existing[:500]}\n\n"
                        f"New observation:\n{new[:500]}"
                    ),
                },
            ],
            max_tokens=400,
            temperature=0.2,
        )
        return refined.strip() or existing
    except Exception:
        logger.warning("[AgentSkills] Refinement LLM failed, keeping existing description")
        return existing


async def extract_concepts_from_skill(skill_id: str, skill_title: str, skill_description: str) -> None:
    """Auto-extract domain concepts (tools, libraries, APIs, techniques) from a skill.

    Uses a fast LLM to identify concepts mentioned in the skill description,
    creates SkillConcept nodes for each, and links them to the skill via
    SkillRelation edges (uses_tool, produces, avoids).
    """
    from app.services.llm_client import utility_completion

    try:
        raw = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract domain concepts from a skill description. For each concept, "
                        "output one line with the format:\n"
                        "CONCEPT_NAME | CONCEPT_TYPE | RELATION_TYPE\n\n"
                        "CONCEPT_TYPE must be one of: tool, library, api, data_format, anti_pattern, technique\n"
                        "RELATION_TYPE must be one of: uses_tool, produces, avoids\n\n"
                        "Examples:\n"
                        "scipy | library | uses_tool\n"
                        "csv | data_format | produces\n"
                        "rate_limiting | anti_pattern | avoids\n"
                        "curve_fitting | technique | uses_tool\n\n"
                        "Output 2-6 concepts, one per line. No other text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Skill: {skill_title}\nDescription: {skill_description[:600]}",
                },
            ],
            max_tokens=200,
            temperature=0.2,
        )

        lines = [line.strip() for line in raw.strip().split("\n") if "|" in line]
        if not lines:
            return

        valid_concept_types = {"tool", "library", "api", "data_format", "anti_pattern", "technique"}
        valid_relation_types = {"uses_tool", "produces", "avoids"}

        async with async_session() as db:
            for line in lines[:6]:
                parts = [p.strip().lower() for p in line.split("|")]
                if len(parts) != 3:
                    continue
                concept_name, concept_type, relation_type = parts

                if concept_type not in valid_concept_types or relation_type not in valid_relation_types:
                    continue
                if not concept_name or len(concept_name) > 255:
                    continue

                # Upsert concept
                result = await db.execute(
                    select(SkillConcept).where(SkillConcept.name == concept_name)
                )
                concept = result.scalar_one_or_none()
                if not concept:
                    concept = SkillConcept(
                        name=concept_name,
                        concept_type=concept_type,
                    )
                    db.add(concept)
                    await db.flush()

                # Create relation if not exists
                result = await db.execute(
                    select(SkillRelation).where(
                        SkillRelation.from_id == skill_id,
                        SkillRelation.relation_type == relation_type,
                        SkillRelation.to_id == concept.id,
                    )
                )
                if not result.scalar_one_or_none():
                    db.add(SkillRelation(
                        from_id=skill_id,
                        relation_type=relation_type,
                        to_id=concept.id,
                    ))

            await db.commit()
            logger.info(f"[AgentSkills] Extracted concepts for skill '{skill_title[:40]}'")

    except Exception:
        logger.exception("[AgentSkills] Failed to extract concepts from skill")
