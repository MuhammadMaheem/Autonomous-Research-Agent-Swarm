"""Single entry point used by both the CLI and the FastAPI layer."""
import time
import uuid

from app.events import EventEmitter
from app.graph.builder import build_graph
from app.graph.state import SwarmState, initial_state

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_research(
    question: str,
    *,
    emitter: EventEmitter,
    run_id: str | None = None,
    mock: bool = False,
    no_critic: bool = False,
    use_rag: bool = True,
) -> SwarmState:
    run_id = run_id or uuid.uuid4().hex[:12]
    config = {
        "configurable": {
            "emitter": emitter,
            "run_id": run_id,
            "mock": mock,
            "no_critic": no_critic,
            "use_rag": use_rag,
        },
        "recursion_limit": 60,
    }
    started = time.monotonic()
    await emitter.emit("runner", "run_started", {
        "question": question, "mock": mock, "no_critic": no_critic, "use_rag": use_rag})
    try:
        final: SwarmState = await get_graph().ainvoke(initial_state(question), config)
    except Exception as exc:
        await emitter.emit("runner", "run_failed", {"error": str(exc)[:500]})
        raise
    report = final.get("citation_report")
    best = final.get("best_report")
    if best is not None and (report is None or best.coverage > report.coverage):
        report = best  # the finalizer publishes the best-coverage draft
    await emitter.emit("runner", "run_finished", {
        "coverage": report.coverage if report else None,
        "unsupported_rate": report.unsupported_rate if report else None,
        "iterations": final.get("iteration", 0),
        "token_usage": final.get("token_usage", 0),
        "elapsed_s": round(time.monotonic() - started, 1),
        "report_dir": final.get("report_dir"),
    })
    return final
