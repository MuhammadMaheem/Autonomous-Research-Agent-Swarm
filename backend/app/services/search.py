"""Web search providers behind one protocol: Tavily (if key), DuckDuckGo (keyless fallback), Mock (tests/demo)."""
import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import settings

_WS = re.compile(r"\s+")


def sanitize_query(query: str, max_len: int = 130) -> str:
    """LLM sub-questions make poor search queries: normalize exotic unicode (non-breaking
    hyphens etc.), drop the question mark, collapse whitespace, cap length at a word boundary."""
    q = unicodedata.normalize("NFKC", query)
    q = q.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    q = _WS.sub(" ", q).strip().rstrip("?").strip()
    if len(q) > max_len:
        q = q[:max_len].rsplit(" ", 1)[0]
    return q


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str | None = None  # extracted page text, when available

    def best_text(self, limit: int = 1400) -> str:
        return (self.content or self.snippet or "")[:limit]


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, k: int = 4) -> list[SearchResult]: ...


class TavilyProvider:
    name = "tavily"

    async def search(self, query: str, k: int = 4) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": k,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(
                title=r.get("title") or r.get("url", ""),
                url=r.get("url", ""),
                snippet=(r.get("content") or "")[:400],
                content=r.get("content") or None,
            )
            for r in data.get("results", [])[:k]
        ]


class DDGSProvider:
    """ddgs rotates across engines; some (mojeek, brave) frequently time out. Pin reliable
    backends and fail over between them instead of surfacing one flaky engine's timeout."""

    name = "ddgs"
    _ATTEMPTS: tuple[str | None, ...] = ("duckduckgo", "bing", None)  # None -> ddgs auto

    async def search(self, query: str, k: int = 4) -> list[SearchResult]:
        q = sanitize_query(query)

        def _sync(backend: str | None) -> list[dict]:
            from ddgs import DDGS

            with DDGS(timeout=8) as d:
                if backend is None:
                    return list(d.text(q, max_results=k * 2))
                return list(d.text(q, max_results=k * 2, backend=backend))

        loop = asyncio.get_event_loop()
        for backend in self._ATTEMPTS:
            try:
                rows = await loop.run_in_executor(None, _sync, backend)
            except Exception:
                continue  # timeout / engine error -> next backend
            results, seen = [], set()
            for r in rows:
                url = r.get("href") or r.get("url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(
                    SearchResult(
                        title=r.get("title") or url,
                        url=url,
                        snippet=(r.get("body") or r.get("description") or "")[:400],
                    )
                )
                if len(results) >= k:
                    break
            if results:
                return results
        return []


def reconstruct_abstract(inverted: dict | None) -> str | None:
    """Rebuild word sequence from OpenAlex inverted index {word: [position, ...]}."""
    if not inverted:
        return None
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def _format_scholar_snippet(work: dict) -> str:
    """Build a readable snippet from OpenAlex work metadata."""
    parts: list[str] = []
    # Authors (up to 5)
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships[:5]:
        name = a.get("author", {}).get("display_name", "")
        if name:
            authors.append(name)
    if authors:
        parts.append(", ".join(authors) + (" et al." if len(authorships) > 5 else ""))
    # Year
    year = work.get("publication_year")
    if year:
        parts.append(f"({year})")
    # Venue
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    venue = source.get("display_name")
    if venue:
        parts.append(f"*{venue}*")
    snippet = " ".join(parts)
    # Append first part of abstract
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if abstract:
        snippet += "\n" + abstract[:400]
    return snippet[:600]


def _scholar_content(work: dict) -> str | None:
    """Build searchable text from OpenAlex work: abstract + keywords."""
    parts: list[str] = []
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if abstract:
        parts.append(f"Abstract: {abstract}")
    keywords = work.get("keywords") or []
    if keywords:
        kw_strs = [k if isinstance(k, str) else k.get("keyword", str(k)) for k in keywords]
        parts.append("Keywords: " + ", ".join(kw_strs))
    return "\n\n".join(parts)[:2000] if parts else None


class ScholarSearchProvider:
    """Academic paper search via OpenAlex API (free, no key, 250M+ works)."""

    name = "openalex"

    async def search(self, query: str, k: int = 4) -> list[SearchResult]:
        q = sanitize_query(query)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={"search": q, "per_page": min(k, 25), "sort": "cited_by_count:desc"},
                headers={"User-Agent": "mailto:research-swarm@example.org"},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for work in (data.get("results") or [])[:k]:
            doi = work.get("doi")  # full URL like https://doi.org/10.xxxx/xxxxx
            url = doi or work.get("id") or ""
            title = work.get("title") or "Untitled"
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=_format_scholar_snippet(work),
                content=_scholar_content(work),
            ))
        return results


class MockSearchProvider:
    """Deterministic canned results — Phase 1 pipeline verification without network/quota."""

    name = "mock"

    async def search(self, query: str, k: int = 4) -> list[SearchResult]:
        base = query.strip().rstrip("?")
        rows = [
            (
                f"Overview: {base}",
                "https://example.org/overview",
                f"An overview article covering {base}. It reports that the topic has seen steady growth "
                f"since 2020, with adoption rising roughly 15% year over year according to industry surveys.",
            ),
            (
                f"Research summary on {base}",
                "https://example.org/research",
                f"A 2024 study on {base} found measurable improvements in efficiency (around 20-30%) in "
                f"controlled evaluations, while noting open challenges around reliability and cost.",
            ),
            (
                f"Recent developments in {base}",
                "https://example.org/news",
                f"Recent reports describe new tooling and standards emerging around {base} in 2025, "
                f"including open-source frameworks and early regulatory guidance.",
            ),
        ]
        return [SearchResult(title=t, url=u, snippet=s, content=s) for t, u, s in rows[:k]]


async def enrich_with_page_text(results: list[SearchResult], n: int = 2, char_limit: int = 1400) -> None:
    """Fetch + extract full text for the top-n results (best effort, failures ignored)."""
    import trafilatura

    async def fetch(r: SearchResult) -> None:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0 (research-swarm)"}) as client:
                resp = await client.get(r.url)
                resp.raise_for_status()
            text = await asyncio.get_event_loop().run_in_executor(
                None, lambda: trafilatura.extract(resp.text)
            )
            if text and len(text) > len(r.snippet):
                r.content = text[:char_limit]
        except Exception:
            pass

    await asyncio.gather(*(fetch(r) for r in results[:n]))


def get_search_provider(mock: bool = False, scholarly: bool = False) -> SearchProvider:
    if mock:
        return MockSearchProvider()
    if scholarly:
        return ScholarSearchProvider()
    if settings.tavily_api_key:
        return TavilyProvider()
    return DDGSProvider()
