"""CLI entry point.

    uv run python -m app.cli "your research question" [--mock] [--no-critic] [--no-rag]
                                                       [--events-out events.jsonl]
"""
import argparse
import asyncio
import json
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from app.events import EventEmitter, TraceEvent
from app.graph.runner import run_research

console = Console()

_STYLE = {
    "run_started": ("bold cyan", ">>"),
    "plan_ready": ("bold magenta", "DAG"),
    "node_started": ("dim", ".."),
    "node_finished": ("dim", "ok"),
    "search_results": ("yellow", "www"),
    "code_executed": ("green", "py"),
    "finding_ready": ("bold green", "F"),
    "verdict": ("blue", "v"),
    "citation_summary": ("bold blue", "AUDIT"),
    "route_decision": ("bold yellow", "->"),
    "run_finished": ("bold cyan", "DONE"),
    "run_failed": ("bold red", "FAIL"),
}


def _render(ev: TraceEvent) -> None:
    style, tag = _STYLE.get(ev.event, ("white", "?"))
    p = ev.payload
    if ev.event == "plan_ready":
        lines = [f"{sq['id']} [{sq['agent']}] deps={sq['depends_on']} — {sq['question']}"
                 for sq in p["plan"]["sub_questions"]]
        console.print(Panel("\n".join(lines),
                            title=f"plan (replan={p['replan']}, iter={p['iteration']})",
                            border_style="magenta"))
        return
    if ev.event == "draft_token":
        return  # too noisy for terminal; streamed in the web UI
    if ev.event == "verdict":
        console.print(f"  [blue]v[/blue] s{p['index']} [{p['label']}] {p['sentence'][:80]}", highlight=False)
        return
    if ev.event == "search_results":
        titles = ", ".join(r["title"][:40] for r in p["results"][:3])
        console.print(f"[{style}]{tag:>5}[/{style}] {ev.node} ({p['provider']}): {titles}", highlight=False)
        return
    if ev.event == "finding_ready":
        console.print(f"[{style}]{tag:>5}[/{style}] {p['sub_question_id']}: {p['summary'][:110]}", highlight=False)
        return
    detail = json.dumps({k: v for k, v in p.items() if k not in ("plan", "code", "text")}, default=str)[:160]
    console.print(f"[{style}]{tag:>5}[/{style}] {ev.node}.{ev.event} {detail}", highlight=False)


async def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous Research Agent Swarm CLI")
    ap.add_argument("question")
    ap.add_argument("--mock", action="store_true", help="mock search/RAG tools (real LLM)")
    ap.add_argument("--no-critic", action="store_true", help="ablation: skip reflection loop")
    ap.add_argument("--no-rag", action="store_true", help="disable RAG agent option")
    ap.add_argument("--events-out", type=Path, default=None, help="write events JSONL (golden-run recording)")
    args = ap.parse_args()

    run_id = uuid.uuid4().hex[:12]
    sinks = [_render]
    fh = None
    if args.events_out:
        fh = args.events_out.open("w")
        sinks.append(lambda ev: (fh.write(ev.model_dump_json() + "\n"), fh.flush()) and None)

    emitter = EventEmitter(run_id=run_id, sinks=sinks)
    final = await run_research(
        args.question, emitter=emitter, run_id=run_id,
        mock=args.mock, no_critic=args.no_critic, use_rag=not args.no_rag)
    if fh:
        fh.close()

    rep = final.get("citation_report")
    console.print(Panel(
        f"run_id: {run_id}\n"
        f"coverage: {rep.coverage:.0%}  unsupported: {rep.unsupported_rate:.0%}\n"
        f"iterations: {final.get('iteration', 0)}   tokens: {final.get('token_usage', 0)}\n"
        f"report: {final.get('report_dir')}/report.md",
        title="run complete", border_style="cyan"))


if __name__ == "__main__":
    asyncio.run(main())
