"""Trace event bus: nodes emit domain events; sinks render (CLI), persist (DB) or stream (SSE)."""
import asyncio
import inspect
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run_started",
    "plan_ready",
    "node_started",
    "node_finished",
    "search_results",
    "code_executed",
    "finding_ready",
    "draft_token",
    "verdict",
    "citation_summary",
    "route_decision",
    "run_finished",
    "run_failed",
]

Sink = Callable[["TraceEvent"], None | Awaitable[None]]


class TraceEvent(BaseModel):
    run_id: str
    seq: int
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node: str
    event: EventType
    payload: dict[str, Any] = {}


class EventEmitter:
    def __init__(self, run_id: str, sinks: list[Sink] | None = None):
        self.run_id = run_id
        self.sinks = sinks or []
        self._seq = 0
        self._lock = asyncio.Lock()

    async def emit(self, node: str, event: EventType, payload: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._seq += 1
            ev = TraceEvent(run_id=self.run_id, seq=self._seq, node=node, event=event, payload=payload or {})
        for sink in self.sinks:
            try:
                res = sink(ev)
                if inspect.isawaitable(res):
                    await res
            except Exception:  # a broken sink must never kill the run
                pass


class NullEmitter(EventEmitter):
    def __init__(self):
        super().__init__(run_id="null")

    async def emit(self, node, event, payload=None) -> None:  # noqa: ARG002
        return


def get_emitter(config: dict) -> EventEmitter:
    return (config or {}).get("configurable", {}).get("emitter") or NullEmitter()
