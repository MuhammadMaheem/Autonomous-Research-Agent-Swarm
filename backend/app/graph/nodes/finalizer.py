"""Finalizer: renumber [E*] citations to [n] by first appearance, append references and
audit footer, write report.md (+ report.pdf via headless chromium when available).
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.events import get_emitter
from app.graph.state import CITE_RE, SwarmState


def renumber_citations(draft: str, evidence_ids: set[str]) -> tuple[str, list[str]]:
    """Replace [E2_1]-style citations with [n] in order of first appearance.
    Returns (rewritten_text, ordered_evidence_ids). Unknown ids are left untouched."""
    order: list[str] = []
    for m in CITE_RE.finditer(draft):
        eid = m.group(1)
        if eid in evidence_ids and eid not in order:
            order.append(eid)
    mapping = {eid: i + 1 for i, eid in enumerate(order)}

    def _sub(m: re.Match) -> str:
        eid = m.group(1)
        return f"[{mapping[eid]}]" if eid in mapping else m.group(0)

    return CITE_RE.sub(_sub, draft), order


def _pdf_from_markdown(md: str, out_pdf: Path) -> bool:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        return False
    try:
        import markdown as mdlib

        body = mdlib.markdown(md, extensions=["tables"])
        html = (
            "<html><head><meta charset='utf-8'><style>"
            "body{font-family:Georgia,serif;max-width:800px;margin:2em auto;line-height:1.55;color:#111}"
            "h1{border-bottom:2px solid #333;padding-bottom:.3em}h2{margin-top:1.4em}"
            "code{background:#f4f4f4;padding:1px 4px;border-radius:3px}"
            "</style></head><body>" + body + "</body></html>"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            html_path = f.name
        res = subprocess.run(
            [chromium, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={out_pdf}", f"file://{html_path}"],
            capture_output=True, timeout=60)
        Path(html_path).unlink(missing_ok=True)
        return res.returncode == 0 and out_pdf.exists()
    except Exception:
        return False


async def finalizer(state: SwarmState, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    await emitter.emit("finalizer", "node_started", {})
    draft = state.get("draft") or "# Report\n\nNo draft was produced."
    evidence = state.get("evidence", {})
    report = state.get("citation_report")
    # Publish the best-coverage draft across reflection iterations, not necessarily the last.
    best_report = state.get("best_report")
    if (best_report is not None and state.get("best_draft")
            and (report is None or best_report.coverage > report.coverage)):
        draft, report = state["best_draft"], best_report
        await emitter.emit("finalizer", "route_decision", {
            "route": "finalizer", "reason":
                f"publishing best-coverage draft ({best_report.coverage:.0%}) over last draft"})

    text, order = renumber_citations(draft, set(evidence))

    refs = ["", "## References", ""]
    for i, eid in enumerate(order, start=1):
        e = evidence[eid]
        src = e.url or e.title or e.source_type
        kind = {"web": "web", "code": "computation", "rag": "local corpus"}[e.source_type]
        refs.append(f"{i}. {e.title or src} — {src} ({kind}, retrieved {e.retrieved_at:%Y-%m-%d})")
    footer = ["", "---", ""]
    if report:
        footer.append(
            f"*Citation audit: coverage {report.coverage:.0%} "
            f"({sum(1 for v in report.verdicts if v.label == 'supported')} supported / "
            f"{sum(1 for v in report.verdicts if v.label != 'no_claim')} claim sentences; "
            f"{state.get('iteration', 0)} reflection iteration(s)).*")
    final_md = text + "\n" + "\n".join(refs + footer) + "\n"

    run_id = (config or {}).get("configurable", {}).get("run_id", "run")
    out_dir = settings.reports_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(final_md)
    pdf_ok = _pdf_from_markdown(final_md, out_dir / "report.pdf")

    await emitter.emit("finalizer", "node_finished", {
        "report_dir": str(out_dir), "pdf": pdf_ok, "references": len(order)})
    return {"final_report": final_md, "report_dir": str(out_dir)}
