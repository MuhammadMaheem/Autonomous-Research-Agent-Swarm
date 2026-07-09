"""B1 baseline: single-agent ReAct-style researcher — same reasoner model, same search
provider, same citation audit — but no planner DAG, no specialist swarm, no critic loop.
Isolates the contribution of the multi-agent structure.
"""
import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel

from app.events import NullEmitter
from app.graph.nodes.citation_checker import citation_checker
from app.graph.state import Evidence, normalize_citations
from app.services import llm as llm_service
from app.services.search import enrich_with_page_text, get_search_provider

_MAX_SEARCHES = 4

_QUERY_SYSTEM = """You are a research assistant. Given a research question and the searches already
performed, propose the single next web search query that would most improve evidence coverage,
or reply {"done": true} if the evidence is sufficient. Return ONLY JSON:
{"query": "...", "done": false}"""

_ANSWER_SYSTEM = """You are a research assistant writing a report in Markdown that answers the question
using ONLY the evidence provided. Every sentence containing a factual claim MUST end with 1-2
citations like [E1_2] using ONLY the given evidence ids. If no evidence supports a claim, omit the
claim. PROSE ONLY - no tables or bullet lists. 350-600 words. Output only the report."""


class _NextQuery(BaseModel):
    query: str = ""
    done: bool = False


async def run_baseline(question: str, *, mock: bool = False) -> dict:
    """Returns the same metric fields the swarm run produces."""
    provider = get_search_provider(mock=mock)
    evidence: dict[str, Evidence] = {}
    tokens = 0
    queries: list[str] = []

    for i in range(_MAX_SEARCHES):
        history = "\n".join(f"- {q}" for q in queries) or "(none yet)"
        ev_digest = "\n".join(f"[{e.id}] {e.title}" for e in evidence.values()) or "(none yet)"
        try:
            nq, t = await llm_service.structured(
                "reasoner", _QUERY_SYSTEM,
                f"Question: {question}\n\nSearches so far:\n{history}\n\nEvidence so far:\n{ev_digest}",
                _NextQuery, max_tokens=200)
            tokens += t
        except Exception:
            nq = _NextQuery(query=question, done=i > 0)
        if nq.done or not nq.query:
            break
        queries.append(nq.query)
        try:
            results = await provider.search(nq.query, k=4)
            if not mock:
                await enrich_with_page_text(results, n=2)
        except Exception:
            results = []
        base = len(evidence)
        for j, r in enumerate(results):
            eid = f"E{i + 1}_{j + 1}"
            evidence[eid] = Evidence(
                id=eid, sub_question_id=f"sq{i + 1}", source_type="web",
                url=r.url, title=r.title, snippet=r.best_text(),
                retrieved_at=datetime.now(timezone.utc))
        if len(evidence) == base:  # search yielded nothing new; stop early
            break

    ev_block = "\n\n".join(f"[{e.id}] ({e.url}) {e.snippet[:600]}" for e in evidence.values())
    draft, t = await llm_service.complete(
        "reasoner", _ANSWER_SYSTEM,
        f"Question: {question}\n\nEvidence:\n{ev_block or 'NONE - state that no evidence was found.'}",
        temperature=0.3, max_tokens=1500)
    tokens += t
    draft = normalize_citations(draft)

    # Same audit pipeline as the swarm.
    state = {"draft": draft, "evidence": evidence}
    audit = await citation_checker(state, {"configurable": {"emitter": NullEmitter()}})
    report = audit["citation_report"]
    tokens += audit.get("token_usage", 0)

    return {
        "coverage": report.coverage,
        "unsupported_rate": report.unsupported_rate,
        "iterations": 0,
        "token_usage": tokens,
        "n_evidence": len(evidence),
        "draft": draft,
        "verdicts": [v.model_dump(mode="json") for v in report.verdicts],
    }


if __name__ == "__main__":
    import sys

    out = asyncio.run(run_baseline(sys.argv[1] if len(sys.argv) > 1 else
                                   "How does RAG reduce hallucination in LLMs?"))
    print({k: v for k, v in out.items() if k not in ("draft", "verdicts")})
