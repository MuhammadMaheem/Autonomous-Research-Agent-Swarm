"""DAG wave scheduler. The node itself is a join point (no-op); routing happens in
`dispatch`, the conditional edge: it fans out ready sub-questions as parallel Send()s
(topological waves) and routes to the synthesizer when the DAG is complete or the
token budget is exhausted.
"""
from langgraph.types import Send

from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.events import get_emitter
from app.graph.state import SwarmState


async def scheduler(state: SwarmState, config: RunnableConfig) -> dict:  # noqa: ARG001
    return {}


def _dep_findings(state: SwarmState, dep_ids: list[str]) -> list[dict]:
    return [f.model_dump(mode="json") for f in state.get("findings", [])
            if f.sub_question_id in dep_ids and f.status == "ok"]


async def dispatch(state: SwarmState, config: RunnableConfig):
    emitter = get_emitter(config)
    plan = state.get("plan")
    if plan is None or not plan.sub_questions:
        await emitter.emit("scheduler", "route_decision", {"route": "synthesizer", "reason": "empty plan"})
        return "synthesizer"

    answered = {f.sub_question_id for f in state.get("findings", [])}
    pending = [sq for sq in plan.sub_questions if sq.id not in answered]

    if not pending:
        await emitter.emit("scheduler", "route_decision",
                           {"route": "synthesizer", "reason": "all sub-questions answered"})
        return "synthesizer"

    if state.get("token_usage", 0) > settings.token_budget:
        await emitter.emit("scheduler", "route_decision",
                           {"route": "synthesizer",
                            "reason": f"token budget exceeded ({state['token_usage']} > {settings.token_budget})",
                            "skipped": [sq.id for sq in pending]})
        return "synthesizer"

    ready = [sq for sq in pending if set(sq.depends_on) <= answered]
    if not ready:  # unreachable if plan validated, but never deadlock
        await emitter.emit("scheduler", "route_decision",
                           {"route": "synthesizer", "reason": "no dispatchable sub-questions",
                            "skipped": [sq.id for sq in pending]})
        return "synthesizer"

    await emitter.emit("scheduler", "route_decision", {
        "route": "wave",
        "wave": [{"id": sq.id, "agent": sq.agent} for sq in ready],
        "pending": [sq.id for sq in pending if sq not in ready],
    })
    return [
        Send(f"{sq.agent}_agent", {
            "task_sq": sq.model_dump(mode="json"),
            "context": _dep_findings(state, sq.depends_on),
            "question": state["question"],
        })
        for sq in ready
    ]
