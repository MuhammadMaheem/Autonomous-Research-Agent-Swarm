import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.run_manager import manager
from app.db import store

router = APIRouter(prefix="/api")


class ResearchRequest(BaseModel):
    question: str = Field(min_length=8, max_length=500)
    use_rag: bool = True
    no_critic: bool = False
    mock: bool = False


@router.post("/research")
async def start_research(req: ResearchRequest) -> dict:
    run_id = await manager.start(req.question, use_rag=req.use_rag,
                                 no_critic=req.no_critic, mock=req.mock)
    return {"run_id": run_id}


@router.get("/research")
async def list_research() -> list[dict]:
    return await store.list_runs()


@router.get("/research/{run_id}")
async def get_research(run_id: str) -> dict:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.get("result_json"):
        run["result"] = json.loads(run.pop("result_json"))
    else:
        run.pop("result_json", None)
        run["result"] = None
    return run


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.get("/research/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    async def gen():
        # Subscribe BEFORE replay so no event falls between replay and live phases.
        q = manager.subscribe(run_id)
        try:
            last_seq = 0
            for ev in await store.get_events(run_id):
                yield _sse({"seq": ev["seq"], "ts": ev["ts"], "node": ev["node"],
                            "event": ev["event"], "payload": ev["payload"]})
                last_seq = ev["seq"]
            current = await store.get_run(run_id)
            if current["status"] != "running" and not manager.is_running(run_id):
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    current = await store.get_run(run_id)
                    if current["status"] != "running" and not manager.is_running(run_id):
                        return
                    continue
                if ev.seq <= last_seq:
                    continue
                last_seq = ev.seq
                yield _sse({"seq": ev.seq, "ts": ev.ts.isoformat(), "node": ev.node,
                            "event": ev.event, "payload": ev.payload})
                if ev.event in ("run_finished", "run_failed"):
                    return
        finally:
            manager.unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/research/{run_id}/report.md", response_class=PlainTextResponse)
async def get_report_md(run_id: str) -> str:
    run = await store.get_run(run_id)
    if run is None or not run.get("report_md"):
        raise HTTPException(404, "report not available")
    return run["report_md"]


@router.get("/research/{run_id}/report.pdf")
async def get_report_pdf(run_id: str) -> FileResponse:
    run = await store.get_run(run_id)
    if run is None or not run.get("report_dir"):
        raise HTTPException(404, "report not available")
    pdf = Path(run["report_dir"]) / "report.pdf"
    if not pdf.exists():
        raise HTTPException(404, "pdf not generated")
    return FileResponse(pdf, media_type="application/pdf", filename=f"report-{run_id}.pdf")
