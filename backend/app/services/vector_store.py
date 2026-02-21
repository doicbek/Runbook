from __future__ import annotations

import asyncio
import logging
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app.config import settings
from app.services.arxiv_service import ArxivPaper

logger = logging.getLogger(__name__)

_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection (lazy singleton)."""
    global _client, _collection
    if _collection is not None:
        return _collection

    _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=settings.OPENAI_API_KEY,
        model_name=settings.EMBEDDING_MODEL,
    )
    _collection = _client.get_or_create_collection(
        name="arxiv_papers",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(
        f"ChromaDB collection 'arxiv_papers' ready with {_collection.count()} documents"
    )
    return _collection


def add_papers(papers: list[ArxivPaper]) -> int:
    """Add papers to ChromaDB, deduplicating by arXiv ID. Returns count of newly added."""
    if not papers:
        return 0

    collection = get_collection()

    # Check which IDs already exist
    paper_ids = [p.arxiv_id for p in papers]
    existing = collection.get(ids=paper_ids)
    existing_ids = set(existing["ids"]) if existing["ids"] else set()

    new_papers = [p for p in papers if p.arxiv_id not in existing_ids]
    if not new_papers:
        logger.info("All papers already indexed, skipping")
        return 0

    documents = [f"{p.title}\n\n{p.abstract}" for p in new_papers]
    metadatas = [
        {
            "title": p.title,
            "authors": ", ".join(p.authors[:5]),
            "url": p.url,
            "published": p.published,
            "categories": ", ".join(p.categories[:5]),
            "abstract": p.abstract[:1000],
        }
        for p in new_papers
    ]
    ids = [p.arxiv_id for p in new_papers]

    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    logger.info(f"Indexed {len(new_papers)} new papers into ChromaDB")
    return len(new_papers)


def query_papers(query: str, top_k: int = 5) -> list[dict]:
    """Query ChromaDB for the most relevant papers."""
    collection = get_collection()

    if collection.count() == 0:
        return []

    results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))

    papers = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        distance = results["distances"][0][i] if results["distances"] else 0.0
        papers.append({
            "arxiv_id": results["ids"][0][i],
            "title": meta.get("title", ""),
            "authors": meta.get("authors", ""),
            "url": meta.get("url", ""),
            "published": meta.get("published", ""),
            "abstract": meta.get("abstract", ""),
            "distance": distance,
            "relevance_score": 1.0 - distance,
        })

    return papers
