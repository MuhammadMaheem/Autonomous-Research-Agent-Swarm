"""Specialist agents: web search, sandboxed code execution, local-corpus RAG.

Each receives an AgentTask payload from a scheduler Send(), produces a Finding plus
Evidence entries, and never raises — failures become Finding(status="failed") so the
pipeline degrades gracefully instead of crashing a wave.
"""
import re

from langchain_core.runnables import RunnableConfig

from app.events import get_emitter
from app.graph import prompts
from app.graph.nodes.common import (
    cfg_flag,
    context_block,
    evidence_id,
    failed_finding,
    parse_task,
    summarize_with_citations,
)
from app.graph.state import Evidence, Finding
from app.services import llm as llm_service
from app.services.rag import get_retriever
from app.services.sandbox import ALLOWED_IMPORTS, run_python
from app.services.search import enrich_with_page_text, get_search_provider, sanitize_query

_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


async def web_agent(payload: dict, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    sq, context, _question = parse_task(payload)
    await emitter.emit("web_agent", "node_started", {"sub_question_id": sq.id, "question": sq.question})
    tokens = 0
    try:
        mock = cfg_flag(config, "mock", False)
        provider = get_search_provider(mock=mock)
        results = await provider.search(sq.question, k=4)
        if not results:  # retry with a compact keyword query — long questions trip engines
            short = " ".join(sanitize_query(sq.question).split()[:9])
            results = await provider.search(short, k=4)
        if not results:
            raise RuntimeError(f"no search results from provider '{provider.name}'")
        if not mock:
            await enrich_with_page_text(results, n=2)
        await emitter.emit("web_agent", "search_results", {
            "sub_question_id": sq.id,
            "provider": provider.name,
            "query": sq.question,
            "results": [{"title": r.title, "url": r.url} for r in results],
        })
        evidences = [
            Evidence(id=evidence_id(sq, j + 1), sub_question_id=sq.id, source_type="web",
                     url=r.url, title=r.title, snippet=r.best_text())
            for j, r in enumerate(results)
        ]
        summary, tokens = await summarize_with_citations(sq, context, evidences)
        finding = Finding(sub_question_id=sq.id, agent="web", summary=summary,
                          evidence_ids=[e.id for e in evidences])
        await emitter.emit("web_agent", "finding_ready", {
            "sub_question_id": sq.id, "summary": summary, "evidence_ids": finding.evidence_ids})
        await emitter.emit("web_agent", "node_finished", {"sub_question_id": sq.id})
        return {"findings": [finding], "evidence": {e.id: e for e in evidences}, "token_usage": tokens}
    except Exception as exc:
        await emitter.emit("web_agent", "node_finished",
                           {"sub_question_id": sq.id, "error": str(exc)[:300]})
        return {"findings": [failed_finding(sq, str(exc))], "token_usage": tokens}


async def code_agent(payload: dict, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    sq, context, _question = parse_task(payload)
    await emitter.emit("code_agent", "node_started", {"sub_question_id": sq.id, "question": sq.question})
    tokens = 0
    try:
        system = prompts.CODEGEN_SYSTEM.format(allowed=", ".join(sorted(ALLOWED_IMPORTS)))
        user = f"Sub-question: {sq.question}\n\n{context_block(context)}"
        raw, toks = await llm_service.complete("reasoner", system, user, temperature=0.0, max_tokens=900)
        tokens += toks
        match = _CODE_BLOCK.search(raw)
        code = (match.group(1) if match else raw).strip()

        result = await run_python(code)
        if not result.ok:  # one repair attempt with the error
            raw, toks = await llm_service.complete(
                "reasoner", system,
                f"{user}\nYour previous script failed:\n```python\n{code}\n```\nError:\n{result.stderr}\nFix it.",
                temperature=0.0, max_tokens=900)
            tokens += toks
            match = _CODE_BLOCK.search(raw)
            code = (match.group(1) if match else raw).strip()
            result = await run_python(code)
        if not result.ok:
            raise RuntimeError(f"sandbox execution failed: {result.stderr[:300]}")

        await emitter.emit("code_agent", "code_executed", {
            "sub_question_id": sq.id, "code": code[:1500], "stdout": result.stdout[:1000]})
        ev = Evidence(id=evidence_id(sq, 1), sub_question_id=sq.id, source_type="code",
                      title="Sandboxed Python computation",
                      snippet=f"```python\n{code[:1200]}\n```\nOutput:\n{result.stdout[:800]}")
        summary, toks = await summarize_with_citations(sq, context, [ev])
        tokens += toks
        finding = Finding(sub_question_id=sq.id, agent="code", summary=summary, evidence_ids=[ev.id])
        await emitter.emit("code_agent", "finding_ready", {
            "sub_question_id": sq.id, "summary": summary, "evidence_ids": [ev.id]})
        await emitter.emit("code_agent", "node_finished", {"sub_question_id": sq.id})
        return {"findings": [finding], "evidence": {ev.id: ev}, "token_usage": tokens}
    except Exception as exc:
        await emitter.emit("code_agent", "node_finished",
                           {"sub_question_id": sq.id, "error": str(exc)[:300]})
        return {"findings": [failed_finding(sq, str(exc))], "token_usage": tokens}


async def rag_agent(payload: dict, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    sq, context, _question = parse_task(payload)
    await emitter.emit("rag_agent", "node_started", {"sub_question_id": sq.id, "question": sq.question})
    tokens = 0
    try:
        retriever = get_retriever(mock=cfg_flag(config, "mock", False))
        chunks = retriever.search(sq.question, k=4)
        if not chunks:
            raise RuntimeError("no relevant chunks in local corpus")
        await emitter.emit("rag_agent", "search_results", {
            "sub_question_id": sq.id, "provider": retriever.name, "query": sq.question,
            "results": [{"title": c.source, "url": None} for c in chunks]})
        evidences = [
            Evidence(id=evidence_id(sq, j + 1), sub_question_id=sq.id, source_type="rag",
                     title=f"corpus: {c.source}", snippet=c.text[:1200])
            for j, c in enumerate(chunks)
        ]
        summary, tokens = await summarize_with_citations(sq, context, evidences)
        finding = Finding(sub_question_id=sq.id, agent="rag", summary=summary,
                          evidence_ids=[e.id for e in evidences])
        await emitter.emit("rag_agent", "finding_ready", {
            "sub_question_id": sq.id, "summary": summary, "evidence_ids": finding.evidence_ids})
        await emitter.emit("rag_agent", "node_finished", {"sub_question_id": sq.id})
        return {"findings": [finding], "evidence": {e.id: e for e in evidences}, "token_usage": tokens}
    except Exception as exc:
        await emitter.emit("rag_agent", "node_finished",
                           {"sub_question_id": sq.id, "error": str(exc)[:300]})
        return {"findings": [failed_finding(sq, str(exc))], "token_usage": tokens}
