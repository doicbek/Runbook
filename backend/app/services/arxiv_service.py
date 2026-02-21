import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


@dataclass
class ArxivPaper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    url: str
    published: str
    categories: list[str]


async def search_arxiv(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
) -> list[ArxivPaper]:
    """Search arXiv API and return parsed papers."""
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    papers = []

    for entry in root.findall(f"{ATOM_NS}entry"):
        # Extract arXiv ID from the <id> tag URL
        raw_id = entry.findtext(f"{ATOM_NS}id", "")
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

        title = entry.findtext(f"{ATOM_NS}title", "").strip().replace("\n", " ")
        abstract = entry.findtext(f"{ATOM_NS}summary", "").strip().replace("\n", " ")
        published = entry.findtext(f"{ATOM_NS}published", "")

        authors = [
            author.findtext(f"{ATOM_NS}name", "")
            for author in entry.findall(f"{ATOM_NS}author")
        ]

        # Get the abstract page URL (rel="alternate")
        url = raw_id
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("rel") == "alternate":
                url = link.get("href", raw_id)
                break

        categories = [
            cat.get("term", "")
            for cat in entry.findall(f"{ARXIV_NS}primary_category")
        ]
        categories += [
            cat.get("term", "")
            for cat in entry.findall(f"{ATOM_NS}category")
            if cat.get("term", "") not in categories
        ]

        papers.append(ArxivPaper(
            arxiv_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors,
            url=url,
            published=published[:10] if published else "",
            categories=categories,
        ))

    logger.info(f"arXiv search for '{query}' returned {len(papers)} papers")
    return papers
