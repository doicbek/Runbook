import asyncio
import io
import json
import logging
import re
import urllib.parse
from typing import Any

import httpx

from app.services.agents.base import BaseAgent
from app.services.llm_client import chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

MAX_CONTENT_PER_PAGE = 8_000
MAX_PAGES = 5
FETCH_TIMEOUT = 15

# ── Well-known free API shortcuts ─────────────────────────────────────────────

_CITY_COORDS = {
    "san jose": (37.3382, -121.8863),
    "san francisco": (37.7749, -122.4194),
    "los angeles": (34.0522, -118.2437),
    "new york": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "seattle": (47.6062, -122.3321),
    "austin": (30.2672, -97.7431),
    "boston": (42.3601, -71.0589),
    "denver": (39.7392, -104.9903),
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "tokyo": (35.6895, 139.6917),
}


def _build_open_meteo_url(prompt: str) -> str | None:
    """Build an Open-Meteo archive URL if the prompt looks like a weather data request."""
    low = prompt.lower()
    if not any(kw in low for kw in ["temperature", "weather", "climate", "temp", "rainfall", "precipitation"]):
        return None

    # Detect city
    coords = None
    city_name = None
    for city, (lat, lon) in _CITY_COORDS.items():
        if city in low:
            coords = (lat, lon)
            city_name = city
            break
    if not coords:
        return None

    # Detect year range
    years = re.findall(r"\b(20\d{2})\b", prompt)
    if years:
        start = f"{years[0]}-01-01"
        end = f"{years[-1]}-12-31"
    else:
        start, end = "2023-01-01", "2023-12-31"

    lat, lon = coords
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean",
        "timezone": "auto",
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{params}"
    logger.info(f"Auto-constructed Open-Meteo URL for {city_name}: {url}")
    return url


class DataRetrievalAgent(BaseAgent):
    """
    Sophisticated data retrieval agent that:
      1. Uses an LLM to understand what data is needed and generate targeted search queries.
      2. Searches the web via DuckDuckGo (no API key required).
      3. Fetches pages and extracts tables (HTML→markdown), CSV, and JSON payloads.
      4. Reads any file URLs referenced in dependency outputs.
      5. Synthesises everything into a structured markdown report with source citations.
    """

    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or get_default_model_for_agent("data_retrieval")

        async def log(level: str, msg: str):
            if log_callback:
                await log_callback(level, msg)

        await log("info", f"Data Retrieval Agent | model={resolved_model}")
        await log("info", f"Task: {prompt[:140]}")

        # ── 1. Auto-detect well-known APIs before any LLM planning ────────────
        auto_url = _build_open_meteo_url(prompt)

        # ── 2. Plan (skip if auto-URL gives us enough) ────────────────────────
        await log("info", "Analysing data requirements...")
        plan = await self._plan(resolved_model, prompt, dependency_outputs)
        await log("info", f"Goal: {plan.get('goal', prompt)}")
        for q in plan.get("queries", []):
            await log("info", f"  Query: {q}")

        # Merge auto_url into direct_urls if not already present
        direct_urls = plan.get("direct_urls", [])
        if auto_url and auto_url not in direct_urls:
            direct_urls = [auto_url] + direct_urls
            await log("info", f"Auto-detected API URL: {auto_url[:90]}")

        # ── 3. Direct URL fetches ─────────────────────────────────────────────
        fetched: list[dict] = []
        for url in direct_urls[:3]:
            await log("info", f"Direct fetch: {url[:90]}")
            content = await self._fetch(url)
            if content:
                content["title"] = "Direct API response"
                fetched.append(content)
                n_tables = len(content.get("tables", []))
                n_chars = len(content.get("text", ""))
                await log("info", f"  → {n_chars} chars, {n_tables} table(s)")

        # ── 3. Web search (only if direct fetches didn't provide enough) ─────
        if len(fetched) < 2:
            all_results: list[dict] = []
            for query in plan.get("queries", [])[:4]:
                await log("info", f"Searching: {query}")
                hits = await self._search(query)
                await log("info", f"  → {len(hits)} results")
                all_results.extend(hits)

            seen: set[str] = set()
            unique: list[dict] = []
            for r in all_results:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    unique.append(r)
            await log("info", f"Unique sources: {len(unique)}")

            for hit in unique[:MAX_PAGES]:
                await log("info", f"Fetching: {hit['url'][:90]}")
                content = await self._fetch(hit["url"])
                if content:
                    content["title"] = hit.get("title", "")
                    content["snippet"] = hit.get("snippet", "")
                    fetched.append(content)
                    n_tables = len(content.get("tables", []))
                    n_chars = len(content.get("text", ""))
                    await log("info", f"  → {n_chars} chars, {n_tables} table(s)")

        # ── 4. Read file URLs from upstream outputs ───────────────────────────
        for url in self._file_urls_from_deps(dependency_outputs):
            await log("info", f"Reading dependency file: {url[:90]}")
            content = await self._fetch(url)
            if content:
                fetched.append(content)

        if not fetched:
            await log("warn", "No content retrieved — returning empty result")
            return {
                "summary": (
                    f"**Data Retrieval: No Results**\n\n"
                    f"Could not retrieve data for: {prompt}\n\n"
                    f"Searched queries: {plan.get('queries', [])}"
                )
            }

        # ── 5. Synthesise ─────────────────────────────────────────────────────
        await log("info", f"Synthesising {len(fetched)} source(s)...")
        summary = await self._synthesise(resolved_model, prompt, plan, fetched)
        await log("info", "Done.")
        return {"summary": summary}

    # ── Planning ──────────────────────────────────────────────────────────────

    async def _plan(self, model: str, prompt: str, dep_outputs: dict) -> dict:
        dep_ctx = ""
        if dep_outputs:
            lines = [f"- {str(v)[:300]}" for v in dep_outputs.values() if v]
            if lines:
                dep_ctx = "\n\nContext from upstream tasks:\n" + "\n".join(lines)

        system = (
            "You are a data retrieval planner. Given a task prompt, output a JSON object with:\n"
            "- goal: one sentence — what data needs to be retrieved\n"
            "- queries: list of 2–4 SHORT web search queries a human would type into Google.\n"
            "  CRITICAL: Do NOT restate the task as a query. Write terse keyword-style queries.\n"
            "  Good examples: [\"San Jose temperature 2023 daily CSV\", \"open-meteo historical weather API\"]\n"
            "  Bad examples: [\"Fetch daily temperature data for San Jose from the Open-Meteo API for the year 2023\"]\n"
            "- direct_urls: list of direct API or data URLs to fetch (if the task names a specific API/dataset).\n"
            "  For weather data use Open-Meteo archive API (free, no key):\n"
            "  https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean&timezone=auto\n"
            "  San Jose CA: latitude=37.3382, longitude=-121.8863\n"
            "- data_types: expected formats e.g. [\"json\", \"csv\", \"table\"]\n"
            "- key_metrics: specific values or columns to extract\n"
            "Output ONLY valid JSON, no markdown fences."
        )
        user = f"Task: {prompt}{dep_ctx}"

        try:
            raw = await chat_completion(model, [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], max_tokens=600)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            plan = json.loads(raw)
            # Ensure direct_urls key exists
            plan.setdefault("direct_urls", [])
            return plan
        except Exception as e:
            logger.warning(f"Plan failed: {e} — using fallback queries")
            # Fallback: generate sensible short queries from the prompt keywords
            words = [w for w in prompt.split() if len(w) > 3][:6]
            return {
                "goal": prompt,
                "queries": [" ".join(words[:4]), " ".join(words[:4]) + " data CSV"],
                "direct_urls": [],
                "data_types": ["text"],
                "key_metrics": [],
            }

    # ── Search ────────────────────────────────────────────────────────────────

    async def _search(self, query: str) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=6)),
            )
            return [
                {"url": r.get("href", ""), "title": r.get("title", ""), "snippet": r.get("body", "")}
                for r in results
                if r.get("href")
            ]
        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")
            return []

    # ── Fetch & extract ───────────────────────────────────────────────────────

    async def _fetch(self, url: str) -> dict | None:
        try:
            async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WorkdeckBot/1.0)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")

                if "json" in ct or url.endswith(".json"):
                    return self._parse_json(url, resp.text)
                if "csv" in ct or url.endswith(".csv"):
                    return self._parse_csv(url, resp.text)
                if url.endswith((".xlsx", ".xls")):
                    return self._parse_excel(url, resp.content)
                # Default: HTML / plain text
                return self._parse_html(url, resp.text)
        except Exception as e:
            logger.warning(f"Fetch failed for {url}: {e}")
            return None

    def _parse_html(self, url: str, html: str) -> dict:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            tables = [
                md for t in soup.find_all("table")[:6]
                if (md := self._table_to_md(t))
            ]

            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r" {2,}", " ", text)[:MAX_CONTENT_PER_PAGE]
            return {"url": url, "text": text, "tables": tables}
        except Exception as e:
            logger.warning(f"HTML parse error {url}: {e}")
            return {"url": url, "text": html[:MAX_CONTENT_PER_PAGE], "tables": []}

    def _table_to_md(self, table) -> str | None:
        try:
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if len(rows) < 2:
                return None
            max_cols = max(len(r) for r in rows)
            # Pad rows to same width
            rows = [r + [""] * (max_cols - len(r)) for r in rows]
            lines = ["| " + " | ".join(rows[0]) + " |"]
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")
            for row in rows[1:25]:
                lines.append("| " + " | ".join(row) + " |")
            return "\n".join(lines)
        except Exception:
            return None

    def _parse_json(self, url: str, text: str) -> dict:
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                import pandas as pd
                df = pd.DataFrame(data[:50])
                table_md = df.to_markdown(index=False)
                return {"url": url, "text": f"JSON array ({len(data)} records)", "tables": [table_md]}
            return {"url": url, "text": json.dumps(data, indent=2)[:MAX_CONTENT_PER_PAGE], "tables": []}
        except Exception:
            return {"url": url, "text": text[:MAX_CONTENT_PER_PAGE], "tables": []}

    def _parse_csv(self, url: str, text: str) -> dict:
        try:
            import pandas as pd
            df = pd.read_csv(io.StringIO(text))
            table_md = df.head(30).to_markdown(index=False)
            desc = f"CSV — {len(df)} rows × {len(df.columns)} columns. Columns: {', '.join(df.columns)}"
            return {"url": url, "text": desc, "tables": [table_md]}
        except Exception:
            return {"url": url, "text": text[:MAX_CONTENT_PER_PAGE], "tables": []}

    def _parse_excel(self, url: str, content: bytes) -> dict:
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content))
            table_md = df.head(30).to_markdown(index=False)
            desc = f"Excel — {len(df)} rows × {len(df.columns)} columns. Columns: {', '.join(df.columns)}"
            return {"url": url, "text": desc, "tables": [table_md]}
        except Exception:
            return {"url": url, "text": "(Excel parse failed)", "tables": []}

    # ── Dep file URL extraction ───────────────────────────────────────────────

    def _file_urls_from_deps(self, dep_outputs: dict) -> list[str]:
        pattern = re.compile(r"https?://\S+\.(?:csv|json|xlsx?|tsv)", re.IGNORECASE)
        urls = []
        for v in dep_outputs.values():
            if v:
                urls.extend(pattern.findall(str(v)))
        return urls

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def _synthesise(
        self, model: str, prompt: str, plan: dict, fetched: list[dict]
    ) -> str:
        parts = []
        for item in fetched:
            section = f"### Source: {item.get('title') or item.get('url', 'unknown')}\n"
            section += f"URL: {item.get('url', '')}\n"
            if item.get("snippet"):
                section += f"*{item['snippet'][:200]}*\n"
            for tbl in item.get("tables", []):
                section += f"\n{tbl}\n"
            if item.get("text"):
                section += f"\n{item['text'][:3000]}\n"
            parts.append(section)

        full_context = "\n\n---\n\n".join(parts)
        key_metrics = ", ".join(plan.get("key_metrics", [])) or "all relevant data"

        system = (
            "You are a data analyst preparing a structured data report for an agentic workflow. "
            "Given retrieved web content, synthesise it into a precise markdown report that:\n"
            "1. States clearly what data was found vs. what is missing\n"
            "2. Presents all tables in clean markdown format (preserve them!)\n"
            "3. Lists key numeric values and metrics extracted\n"
            "4. Cites every source with its URL\n"
            "5. Notes data quality issues, gaps, or caveats\n"
            "The report will be consumed by downstream agents — be precise and structured."
        )
        user = (
            f"Task: {prompt}\n"
            f"Goal: {plan.get('goal', '')}\n"
            f"Key metrics to extract: {key_metrics}\n\n"
            f"Retrieved content:\n\n{full_context[:14_000]}"
        )

        try:
            return await chat_completion(model, [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], max_tokens=4096)
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"**Data Retrieval Results**\n\n{full_context[:5000]}"
