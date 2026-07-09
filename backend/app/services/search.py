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


def get_search_provider(mock: bool = False) -> SearchProvider:
    if mock:
        return MockSearchProvider()
    if settings.tavily_api_key:
        return TavilyProvider()
    return DDGSProvider()
