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
            "Mock implementation — does not create real spreadsheet files. Uses an LLM to "
            "generate a markdown table that looks like spreadsheet data, including summary "
            "statistics. To produce real .xlsx files, build a custom agent using openpyxl."
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
            "Mock implementation — uses an LLM to synthesize inputs from upstream tasks into a "
            "multi-section markdown document with headings, findings, and conclusions. Preserves "
            "image markdown tags (plots/artifacts) from upstream tasks so they render inline. "
            "Supports LaTeX math notation. Typically placed as the final task in a workflow."
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
            "Mock implementation — catch-all agent for tasks that don't fit other categories. "
            "Passes the task prompt and any upstream outputs to an LLM and returns the response "
            "as markdown. No tool access. Use for summarization, transformation, or reasoning "
            "tasks that don't require code execution or external data."
        ),
        "tools": [],
        "status": "active",
        "is_builtin": True,
        "icon": "🤖",
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
