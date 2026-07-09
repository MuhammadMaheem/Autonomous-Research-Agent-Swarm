"""Aggregate eval results and compare systems.

    uv run python -m eval.metrics                    # summary table
    uv run python -m eval.metrics --paired swarm baseline   # paired comparison + sign test

Also computes checker-vs-human agreement (Cohen's kappa) when labels exist at
eval/labels/human_labels.csv with columns: run_key,sentence_index,human_label
(run_key = "<question_id>:<system>").
"""
import argparse
import csv
import json
import math
import statistics as stats
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS = EVAL_DIR / "results" / "results.jsonl"
HUMAN = EVAL_DIR / "labels" / "human_labels.csv"


def load() -> list[dict]:
    if not RESULTS.exists():
        raise SystemExit(f"no results at {RESULTS} — run eval.run_eval first")
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
    # keep the latest row per (id, system)
    latest: dict[tuple, dict] = {}
    for r in rows:
        latest[(r["id"], r["system"])] = r
    return [r for r in latest.values() if "coverage" in r and r["coverage"] is not None]


def summary(rows: list[dict]) -> None:
    by_system: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_system[r["system"]].append(r)
    print(f"{'system':<10} {'n':>3} {'coverage':>9} {'unsup.':>7} {'sources':>8} {'tokens':>8} {'sec':>6}")
    for system, rs in sorted(by_system.items()):
        cov = [r["coverage"] for r in rs]
        uns = [r["unsupported_rate"] for r in rs]
        print(f"{system:<10} {len(rs):>3} "
              f"{stats.mean(cov):>8.2%} {stats.mean(uns):>6.2%} "
              f"{stats.mean([r['n_sources'] for r in rs]):>8.1f} "
              f"{stats.mean([r['token_usage'] for r in rs]):>8.0f} "
              f"{stats.mean([r['elapsed_s'] for r in rs]):>6.0f}")


def sign_test(diffs: list[float]) -> float:
    """Two-sided sign test p-value (exact binomial) on nonzero paired differences."""
    pos = sum(1 for d in diffs if d > 0)
    n = sum(1 for d in diffs if d != 0)
    if n == 0:
        return 1.0
    k = max(pos, n - pos)
    p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * p)


def paired(rows: list[dict], a: str, b: str) -> None:
    ra = {r["id"]: r for r in rows if r["system"] == a}
    rb = {r["id"]: r for r in rows if r["system"] == b}
    common = sorted(set(ra) & set(rb))
    if not common:
        raise SystemExit(f"no common questions between {a} and {b}")
    diffs = [ra[q]["coverage"] - rb[q]["coverage"] for q in common]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    print(f"paired coverage, {a} vs {b} (n={len(common)}):")
    for q, d in zip(common, diffs):
        print(f"  {q}: {ra[q]['coverage']:.2f} vs {rb[q]['coverage']:.2f}  (Δ{d:+.2f})")
    print(f"mean Δ = {stats.mean(diffs):+.3f}   median Δ = {stats.median(diffs):+.3f}")
    print(f"wins/losses/ties = {wins}/{losses}/{len(common) - wins - losses}")
    print(f"sign test p = {sign_test(diffs):.4f}"
          + ("  (small n — interpret cautiously)" if len(common) < 15 else ""))


def kappa(rows: list[dict]) -> None:
    if not HUMAN.exists():
        print(f"(no human labels at {HUMAN} — kappa skipped; see labels/rubric.md)")
        return
    checker: dict[tuple, str] = {}
    for r in rows:
        for v in r.get("verdicts", []):
            checker[(f"{r['id']}:{r['system']}", v["index"])] = v["label"]
    pairs = []
    with HUMAN.open() as fh:
        for row in csv.DictReader(fh):
            key = (row["run_key"], int(row["sentence_index"]))
            if key in checker:
                pairs.append((checker[key], row["human_label"].strip()))
    if len(pairs) < 10:
        print(f"(only {len(pairs)} matched human labels — kappa skipped)")
        return
    labels = sorted({l for p in pairs for l in p})
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / n
    pe = sum((sum(1 for a, _ in pairs if a == l) / n) * (sum(1 for _, b in pairs if b == l) / n)
             for l in labels)
    k = (po - pe) / (1 - pe) if pe < 1 else 0.0
    print(f"checker-vs-human agreement: n={n}, observed={po:.2%}, Cohen's kappa={k:.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--paired", nargs=2, metavar=("SYS_A", "SYS_B"))
    args = ap.parse_args()
    rows = load()
    summary(rows)
    print()
    if args.paired:
        paired(rows, *args.paired)
        print()
    kappa(rows)
