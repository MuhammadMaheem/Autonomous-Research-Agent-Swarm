"""Synthesizer: compose the draft report from findings + evidence, streaming tokens to the trace."""
from langchain_core.runnables import RunnableConfig

from app.events import get_emitter
from app.graph import prompts
from app.graph.state import SwarmState, normalize_citations
from app.services import llm as llm_service


def _build_user_prompt(state: SwarmState) -> str:
    plan = state["plan"]
    parts = [f"Main research question: {state['question']}\n"]
    parts.append("Sub-question findings:")
    findings = {f.sub_question_id: f for f in state.get("findings", [])}
    for sq in plan.sub_questions:
        f = findings.get(sq.id)
        if f is None:
            parts.append(f"- {sq.id} ({sq.question}): NOT ANSWERED (skipped)")
        elif f.status == "failed":
            parts.append(f"- {sq.id} ({sq.question}): FAILED — {f.error}")
        else:
            parts.append(f"- {sq.id} ({sq.question}):\n  {f.summary}")
    parts.append("\nEvidence catalog (cite by id):")
    for e in state.get("evidence", {}).values():
        src = e.url or e.title or e.source_type
        parts.append(f"[{e.id}] ({src}) {e.snippet[:280]}")
    return "\n".join(parts)


async def synthesizer(state: SwarmState, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    iteration = state.get("iteration", 0)
    await emitter.emit("synthesizer", "node_started", {"iteration": iteration})

    evidence_n = len(state.get("evidence", {}))
    if state.get("draft") and state.get("evidence_at_draft") == evidence_n:
        # Replan produced no new evidence (e.g. its agents failed) — regenerating would
        # spend tokens to audit the same information again.
        await emitter.emit("synthesizer", "node_finished",
                           {"skipped": "no new evidence since last draft — reusing it"})
        return {}

    async def on_chunk(text: str, reset: bool = False) -> None:
        await emitter.emit("synthesizer", "draft_token", {"text": text, "reset": reset})

    draft, tokens = await llm_service.stream_complete(
        "reasoner", prompts.SYNTHESIZER_SYSTEM, _build_user_prompt(state),
        on_chunk=on_chunk, temperature=0.3, max_tokens=1500)
    draft = normalize_citations(draft)
    await emitter.emit("synthesizer", "node_finished", {"chars": len(draft)})
    return {"draft": draft, "token_usage": tokens, "evidence_at_draft": evidence_n}
