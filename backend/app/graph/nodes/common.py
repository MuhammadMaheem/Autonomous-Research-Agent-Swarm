"""Shared helpers for specialist agent nodes."""
from app.events import get_emitter
from app.graph import prompts
from app.graph.state import Evidence, Finding, SubQuestion, sq_number
from app.services import llm as llm_service


def cfg_flag(config: dict, key: str, default=False):
    return (config or {}).get("configurable", {}).get(key, default)


def parse_task(payload: dict) -> tuple[SubQuestion, list[Finding], str]:
    sq = SubQuestion.model_validate(payload["task_sq"])
    context = [Finding.model_validate(f) for f in payload.get("context", [])]
    return sq, context, payload.get("question", "")


def evidence_id(sq: SubQuestion, n: int) -> str:
    return f"E{sq_number(sq.id)}_{n}"


def context_block(context: list[Finding]) -> str:
    if not context:
        return ""
    lines = [f"- [{f.sub_question_id}] {f.summary}" for f in context if f.status == "ok"]
    if not lines:
        return ""
    return "Answers from prerequisite sub-questions (context):\n" + "\n".join(lines) + "\n\n"


async def summarize_with_citations(sq: SubQuestion, context: list[Finding],
                                   evidences: list[Evidence]) -> tuple[str, int]:
    ev_block = "\n\n".join(
        f"[{e.id}] {e.title or e.source_type}\n{e.snippet[:900]}" for e in evidences
    )
    user = (
        f"Sub-question: {sq.question}\n\n"
        f"{context_block(context)}"
        f"Evidence:\n{ev_block}"
    )
    system = prompts.SUMMARIZE_SYSTEM.format(example_id=evidences[0].id if evidences else "E1_1")
    return await llm_service.complete("worker", system, user, temperature=0.2, max_tokens=400)


def failed_finding(sq: SubQuestion, error: str) -> Finding:
    return Finding(sub_question_id=sq.id, agent=sq.agent, summary="", status="failed", error=error[:500])


async def emit_start_finish(config, node: str, event: str, payload: dict):
    await get_emitter(config).emit(node, event, payload)
