"""Owns background research runs: one asyncio task per run, events fanned out to
SQLite (replay) and to per-run subscriber queues (live SSE).
"""
import asyncio
import uuid
from collections import defaultdict

from app.db import store
from app.events import EventEmitter, TraceEvent
from app.graph.runner import run_research


class RunManager:
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._tasks: dict[str, asyncio.Task] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._subscribers[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subscribers[run_id].discard(q)

    def is_running(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def _fanout(self, ev: TraceEvent) -> None:
        for q in list(self._subscribers[ev.run_id]):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass  # slow consumer; it can recover via DB replay on reconnect

    async def start(self, question: str, *, use_rag: bool = True,
                    no_critic: bool = False, mock: bool = False) -> str:
        run_id = uuid.uuid4().hex[:12]
        await store.create_run(run_id, question)
        emitter = EventEmitter(run_id=run_id, sinks=[store.insert_event, self._fanout])
        self._tasks[run_id] = asyncio.create_task(
            self._run(run_id, question, emitter, use_rag=use_rag, no_critic=no_critic, mock=mock))
        return run_id

    async def _run(self, run_id: str, question: str, emitter: EventEmitter, **opts) -> None:
        try:
            final = await run_research(question, emitter=emitter, run_id=run_id, **opts)
        except Exception as exc:
            await store.fail_run(run_id, str(exc))
            return
        report = final.get("citation_report")
        best = final.get("best_report")
        if best is not None and (report is None or best.coverage > report.coverage):
            report = best  # what the finalizer actually published
        plan = final.get("plan")
        evidence = final.get("evidence", {})
        result = {
            "plan": plan.model_dump(mode="json") if plan else None,
            "verdicts": [v.model_dump(mode="json") for v in report.verdicts] if report else [],
            "evidence": {eid: {"title": e.title, "url": e.url, "source_type": e.source_type,
                               "snippet": e.snippet[:500]} for eid, e in evidence.items()},
            "findings": [f.model_dump(mode="json") for f in final.get("findings", [])],
        }
        await store.finish_run(
            run_id,
            coverage=report.coverage if report else None,
            unsupported_rate=report.unsupported_rate if report else None,
            iterations=final.get("iteration", 0),
            token_usage=final.get("token_usage", 0),
            report_md=final.get("final_report"),
            report_dir=final.get("report_dir"),
            result=result,
        )


manager = RunManager()
