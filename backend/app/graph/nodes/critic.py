"""Critic/Reflection: gate on citation coverage; below threshold, generate replan feedback
and loop back to the Planner — hard-capped at settings.max_iterations loop-backs.
"""
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.events import get_emitter
from app.graph import prompts
from app.graph.nodes.common import cfg_flag
from app.graph.state import CriticFeedback, SwarmState
from app.services import llm as llm_service


class _FeedbackSchema(CriticFeedback):
    passed: bool = False


async def critic(state: SwarmState, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    report = state["citation_report"]
    iteration = state.get("iteration", 0)
    no_critic = cfg_flag(config, "no_critic", False)
    await emitter.emit("critic", "node_started",
                       {"coverage": report.coverage, "iteration": iteration})

    # Track the best draft across reflection iterations; the finalizer publishes the best,
    # not necessarily the last (reflection can regress).
    best = state.get("best_report")
    best_updates: dict = {}
    if best is None or report.coverage >= best.coverage:
        best_updates = {"best_draft": state.get("draft"), "best_report": report}

    threshold = settings.coverage_threshold
    if no_critic or report.coverage >= threshold or iteration >= settings.max_iterations:
        reason = ("critic disabled (ablation)" if no_critic
                  else f"coverage {report.coverage:.2f} >= {threshold}" if report.coverage >= threshold
                  else f"max iterations reached ({iteration}/{settings.max_iterations}), finalizing anyway")
        fb = CriticFeedback(passed=True, notes=reason)
        await emitter.emit("critic", "route_decision",
                           {"route": "finalizer", "reason": reason, "coverage": report.coverage})
        await emitter.emit("critic", "node_finished", {"passed": True})
        return {"feedback": fb, **best_updates}

    failing = [v for v in report.verdicts if v.label in ("unsupported", "partially_supported")][:8]
    failing_block = "\n".join(f"- ({v.label}) {v.sentence} | reason: {v.reason}" for v in failing)
    plan = state["plan"]
    next_id = len(plan.sub_questions) + 1
    rag_opt = ", rag (local corpus)" if cfg_flag(config, "use_rag", True) else ""
    system = prompts.CRITIC_SYSTEM.format(next=next_id, rag_opt=rag_opt)
    user = (
        f"Research question: {state['question']}\n\n"
        f"Current plan:\n" +
        "\n".join(f"- {sq.id} ({sq.agent}): {sq.question}" for sq in plan.sub_questions) +
        f"\n\nCitation coverage: {report.coverage:.2f} (threshold {threshold})\n"
        f"Failing sentences:\n{failing_block}"
    )
    tokens = 0
    try:
        fb_raw, tokens = await llm_service.structured(
            "reasoner", system, user, _FeedbackSchema, max_tokens=800)
        fb = CriticFeedback(passed=False, weak_sub_questions=fb_raw.weak_sub_questions,
                            suggested_sub_questions=fb_raw.suggested_sub_questions,
                            notes=fb_raw.notes or "coverage below threshold")
    except Exception as exc:
        fb = CriticFeedback(passed=False, notes=f"coverage {report.coverage:.2f} below threshold; "
                                                f"gather stronger sources for unsupported claims "
                                                f"(critic LLM failed: {str(exc)[:150]})")
    await emitter.emit("critic", "route_decision", {
        "route": "planner", "reason": f"coverage {report.coverage:.2f} < {threshold}",
        "iteration": iteration + 1, "notes": fb.notes})
    await emitter.emit("critic", "node_finished", {"passed": False, "iteration": iteration + 1})
    return {"feedback": fb, "iteration": iteration + 1, "token_usage": tokens, **best_updates}


def route_after_critic(state: SwarmState) -> str:
    fb = state.get("feedback")
    return "finalizer" if (fb is None or fb.passed) else "planner"
