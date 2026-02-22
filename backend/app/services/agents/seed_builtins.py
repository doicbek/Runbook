import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_definition import AgentDefinition

logger = logging.getLogger(__name__)

BUILTIN_AGENTS = [
    {
        "agent_type": "arxiv_search",
        "name": "ArXiv Search",
        "description": (
            "Real implementation — searches arXiv for academic papers using the arXiv API and a "
            "vector store (ChromaDB) for semantic retrieval. Produces a structured literature review "
            "with [Author et al., Year] citations and arXiv URLs. Best for research surveys, "
            "finding prior work, and synthesizing academic literature."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "📚",
    },
    {
        "agent_type": "code_execution",
        "name": "Code Execution",
        "description": (
            "Real implementation — uses an LLM to generate Python code from the task prompt, "
            "then executes it in a sandboxed subprocess. Has access to numpy, scipy, matplotlib, "
            "pandas, and other installed packages. Produces code blocks, computed values, and "
            "plots as artifacts. Best for data analysis, curve fitting, and computation."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "⚙️",
    },
    {
        "agent_type": "data_retrieval",
        "name": "Data Retrieval",
        "description": (
            "Real implementation — uses an LLM to understand what data is needed and generate "
            "targeted search queries, then searches the web via DuckDuckGo (no API key needed). "
            "Fetches pages and extracts HTML tables (converted to markdown), CSV files, JSON APIs, "
            "and Excel files. Also reads file URLs from upstream task outputs. Finally synthesises "
            "all retrieved data into a structured markdown report with source citations."
        ),
        "tools": ["httpx"],
        "status": "active",
        "is_builtin": True,
        "icon": "🌐",
    },
    {
        "agent_type": "spreadsheet",
        "name": "Spreadsheet",
        "description": (
            "Real implementation — uses an LLM to generate openpyxl Python code from the task "
            "prompt, then executes it in a sandboxed subprocess. Creates a real .xlsx file with "
            "formatted headers (bold + blue fill), auto-sized columns, frozen top row, a Summary "
            "sheet with statistics, and a markdown table preview in stdout. Parses upstream "
            "markdown tables as input data; generates synthetic data if none is provided. "
            "Downloads the .xlsx as an artifact. Best for structured data, financial models, "
            "and datasets that need to be opened in Excel."
        ),
        "tools": ["openpyxl"],
        "status": "active",
        "is_builtin": True,
        "icon": "📊",
    },
    {
        "agent_type": "report",
        "name": "Report",
        "description": (
            "Real implementation — multi-step synthesis pipeline: (1) extracts key findings from "
            "each upstream task output in parallel, (2) builds a structured outline (Executive "
            "Summary → thematic sections → Conclusions), (3) writes each section in parallel "
            "using the upstream findings as context, (4) assembles the final document and weaves "
            "in any inline images (plots/artifacts) from upstream tasks at contextually "
            "appropriate locations. Supports LaTeX math ($...$ inline, $$...$$ display). "
            "Typically placed as the final task in a workflow."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "📝",
    },
    {
        "agent_type": "general",
        "name": "General",
        "description": (
            "Real implementation — chain-of-thought reasoning agent. First classifies the task "
            "type and selects a reasoning strategy (direct answer vs. multi-step). For complex "
            "tasks: generates a step-by-step reasoning plan, executes each step sequentially "
            "(each step builds on prior results), then synthesises a polished markdown answer "
            "from the reasoning chain. Supports LaTeX math, tables, code blocks. Use for "
            "summarisation, analysis, comparison, transformation, explanation, or Q&A tasks "
            "that do not require code execution or live data retrieval."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "🤖",
    },
    {
        "agent_type": "sub_action",
        "name": "Sub-Action",
        "description": (
            "Spawns a child action with its own planner-generated DAG for complex sub-problems. "
            "Use when a sub-problem is itself complex enough to require multi-step planning "
            "(e.g., a full research-then-analysis sub-workflow). The task prompt must specify "
            "exactly what output the sub-action should produce. Max depth: 3 levels."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "↗",
    },
]


async def seed_builtin_agents(db: AsyncSession) -> None:
    """Idempotent upsert of builtin agents."""
    for data in BUILTIN_AGENTS:
        result = await db.execute(
            select(AgentDefinition).where(AgentDefinition.agent_type == data["agent_type"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            agent = AgentDefinition(**data)
            db.add(agent)
            logger.info(f"Seeded builtin agent: {data['agent_type']}")
        else:
            # Update fields that might have changed (name, description, icon) but don't overwrite code
            existing.name = data["name"]
            existing.description = data["description"]
            existing.icon = data["icon"]
            existing.is_builtin = True
            existing.status = data["status"]

    await db.commit()
    logger.info("Builtin agents seeded.")
