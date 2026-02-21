import asyncio
import logging
from typing import Any

from app.config import settings
from app.services.agents.base import BaseAgent
from app.services.arxiv_service import search_arxiv
from app.services.llm_client import chat_completion, get_default_model_for_agent
from app.services.vector_store import add_papers, query_papers

logger = logging.getLogger(__name__)


class ArxivSearchAgent(BaseAgent):
    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or get_default_model_for_agent("arxiv_search")

        if log_callback:
            await log_callback("info", f"Using model: {resolved_model}")

        # Step 1: Extract focused search query from task prompt
        if log_callback:
            await log_callback("info", "Extracting arXiv search query from task prompt...")

        search_query = await self._extract_query(resolved_model, prompt, dependency_outputs)

        if log_callback:
            await log_callback("info", f"Search query: {search_query}")

        # Step 2: Fetch papers from arXiv API
        if log_callback:
            await log_callback("info", "Fetching papers from arXiv API...")

        papers = await search_arxiv(search_query, max_results=settings.ARXIV_MAX_RESULTS)

        if log_callback:
            await log_callback("info", f"Found {len(papers)} papers from arXiv")
            for p in papers[:3]:
                await log_callback("info", f"  - {p.title[:80]}")

        if not papers:
            return {"summary": f"No papers found on arXiv for query: {search_query}"}

        # Step 3: Index papers into ChromaDB
        if log_callback:
            await log_callback("info", "Indexing papers into vector store...")

        loop = asyncio.get_event_loop()
        new_count = await loop.run_in_executor(None, add_papers, papers)

        if log_callback:
            await log_callback("info", f"Indexed {new_count} new papers (deduped)")

        # Step 4: RAG retrieval — query the vector store
        if log_callback:
            await log_callback("info", "Retrieving most relevant papers via similarity search...")

        relevant = await loop.run_in_executor(
            None, query_papers, prompt, settings.ARXIV_RAG_TOP_K
        )

        if log_callback:
            await log_callback("info", f"Retrieved {len(relevant)} relevant papers for synthesis")
            for r in relevant:
                score = f"{r['relevance_score']:.3f}"
                await log_callback("info", f"  [{score}] {r['title'][:70]}")

        # Step 5: Generate literature review with LLM
        if log_callback:
            await log_callback("info", "Generating research summary with citations...")

        summary = await self._generate_summary(resolved_model, prompt, relevant)

        if log_callback:
            preview = summary[:200] if summary else "(empty)"
            await log_callback("info", f"[LLM Output] {preview}...")

        return {"summary": summary}

    async def _extract_query(
        self,
        model: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
    ) -> str:
        """Use LLM to distill the task prompt into focused arXiv search terms."""
        dep_context = ""
        if dependency_outputs:
            for dep_id, output in dependency_outputs.items():
                if output:
                    dep_context += f"\nUpstream output: {str(output)[:300]}"

        result = await chat_completion(
            model,
            [
                {
                    "role": "system",
                    "content": (
                        "Extract a concise arXiv search query from the user's task. "
                        "Output ONLY the search terms, nothing else. "
                        "Use technical terms suitable for academic paper search. "
                        "Maximum 8 words."
                    ),
                },
                {"role": "user", "content": f"Task: {prompt}{dep_context}"},
            ],
            max_tokens=50,
            temperature=0.0,
        )
        return result.strip().strip('"')

    async def _generate_summary(
        self,
        model: str,
        prompt: str,
        relevant_papers: list[dict],
    ) -> str:
        """Generate a markdown literature review from retrieved papers."""
        papers_context = ""
        for i, p in enumerate(relevant_papers, 1):
            # Extract first author surname and year
            authors = p.get("authors", "Unknown")
            first_author = authors.split(",")[0].strip().split()[-1] if authors else "Unknown"
            year = p.get("published", "")[:4] if p.get("published") else "n.d."

            papers_context += (
                f"\n--- Paper {i} ---\n"
                f"Title: {p['title']}\n"
                f"Authors: {authors}\n"
                f"Year: {year}\n"
                f"arXiv URL: {p['url']}\n"
                f"Abstract: {p['abstract']}\n"
            )

        system_prompt = (
            "You are an academic research assistant. Using ONLY the provided paper abstracts, "
            "write a structured markdown literature review.\n\n"
            "Requirements:\n"
            "- Use in-text citations in the format [Author et al., Year]\n"
            "- Organize findings by theme, not paper-by-paper\n"
            "- Include a '## Key Findings' section with thematic subsections\n"
            "- Include a '## Synthesis' section connecting the papers\n"
            "- End with a '## References' section listing each paper with its arXiv URL\n"
            "- Be specific about methods, results, and contributions\n"
            "- Do NOT fabricate information not present in the abstracts\n"
            "- Use LaTeX notation ($...$ for inline, $$...$$ for display) for any mathematical formulas\n"
            "- Output ONLY the markdown content"
        )

        return await chat_completion(
            model,
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Research question: {prompt}\n\nRetrieved papers:\n{papers_context}",
                },
            ],
            max_tokens=2000,
            temperature=0.3,
        )
