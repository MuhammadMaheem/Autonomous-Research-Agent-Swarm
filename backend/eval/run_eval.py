"""Evaluation runner.

    uv run python -m eval.run_eval --system swarm --split smoke
    uv run python -m eval.run_eval --system baseline --split smoke
    uv run python -m eval.run_eval --system no-critic --ids w01,c04

Systems: swarm (full pipeline) | no-critic (ablation) | baseline (single ReAct-style agent).
Results appended to eval/results/results.jsonl - one row per (question, system) run.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
DATASET = EVAL_DIR / "dataset" / "questions.jsonl"
RESULTS = EVAL_DIR / "results" / "results.jsonl"

SMOKE_IDS = ["w01", "c04"]  # one web-heavy + one computational


def load_questions(split: str, ids: list[str] | None) -> list[dict]:
    rows = [json.loads(l) for l in DATASET.read_text().splitlines() if l.strip()]
    if ids:
        return [r for r in rows if r["id"] in ids]
    if split == "smoke":
        return [r for r in rows if r["id"] in SMOKE_IDS]
    return rows


async def run_one(system: str, row: dict) -> dict:
    from app.events import NullEmitter

    started = time.monotonic()
    if system == "baseline":
        from eval.baseline import run_baseline

        out = await run_baseline(row["question"])
        n_sources = out.pop("n_evidence")
        verdicts = out.pop("verdicts")
        out.pop("draft")
    else:
        from app.graph.runner import run_research

        final = await run_research(row["question"], emitter=NullEmitter(),
                                   no_critic=(system == "no-critic"),
                                   run_id=f"eval-{system}-{row['id']}")
        report = final.get("citation_report")
        best = final.get("best_report")
        if best is not None and (report is None or best.coverage > report.coverage):
            report = best
        out = {
            "coverage": report.coverage if report else None,
            "unsupported_rate": report.unsupported_rate if report else None,
            "iterations": final.get("iteration", 0),
            "token_usage": final.get("token_usage", 0),
        }
        n_sources = len(final.get("evidence", {}))
        verdicts = [v.model_dump(mode="json") for v in report.verdicts] if report else []
    return {
        "id": row["id"], "category": row["category"], "system": system,
        "question": row["question"], **out, "n_sources": n_sources,
        "n_claim_sentences": sum(1 for v in verdicts if v["label"] != "no_claim"),
        "elapsed_s": round(time.monotonic() - started, 1),
        "verdicts": verdicts,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, choices=["swarm", "no-critic", "baseline"])
    ap.add_argument("--split", default="smoke", choices=["smoke", "full"])
    ap.add_argument("--ids", default=None, help="comma-separated question ids (overrides split)")
    args = ap.parse_args()

    questions = load_questions(args.split, args.ids.split(",") if args.ids else None)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    print(f"running {len(questions)} questions with system={args.system}")
    with RESULTS.open("a") as fh:
        for row in questions:  # sequential: stay inside free-tier rate limits
            print(f"- {row['id']}: {row['question'][:70]}…")
            try:
                res = await run_one(args.system, row)
            except Exception as exc:
                res = {"id": row["id"], "category": row["category"], "system": args.system,
                       "question": row["question"], "error": str(exc)[:300]}
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            if "coverage" in res:
                print(f"  coverage={res['coverage']}  unsupported={res['unsupported_rate']}  "
                      f"tokens={res['token_usage']}  {res['elapsed_s']}s")
            else:
                print(f"  ERROR: {res.get('error')}")
    print(f"results appended to {RESULTS}")


if __name__ == "__main__":
    asyncio.run(main())
