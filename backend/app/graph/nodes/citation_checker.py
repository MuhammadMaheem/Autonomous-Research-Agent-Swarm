"""Citation-Checker: per-sentence verification of the draft against retrieved evidence.

Pipeline: pysbd sentence segmentation (markdown-aware) -> parse [E*] citations per sentence
-> batched LLM judging against ONLY the cited evidence text -> labels
supported / partially_supported / unsupported / no_claim -> CitationReport with coverage.

Deterministic guarantees:
- A sentence citing an id that does not exist in the evidence store is 'unsupported' (rule, no LLM).
- If a judge batch fails twice, a conservative fallback labels its sentences (cited ->
  partially_supported, uncited claims -> unsupported) so the checker never blocks the run.
"""
import hashlib
import re

import pysbd
from pydantic import BaseModel

from langchain_core.runnables import RunnableConfig

from app.events import get_emitter
from app.graph import prompts
from app.graph.state import CITE_RE, CitationReport, SentenceVerdict, SwarmState, VerdictLabel
from app.services import llm as llm_service

_BATCH_SIZE = 6
_SEGMENTER = pysbd.Segmenter(language="en", clean=False)
_SKIP_LINE = re.compile(r"^\s*(#{1,6}\s|```|\||!\[)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


class _JudgeVerdict(BaseModel):
    index: int
    label: VerdictLabel
    reason: str = ""


class _JudgeBatch(BaseModel):
    verdicts: list[_JudgeVerdict]


def split_sentences(draft: str) -> list[str]:
    """Markdown-aware sentence units: skips headers/fences/tables/images, unwraps bullets."""
    sentences: list[str] = []
    in_fence = False
    for line in draft.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or _SKIP_LINE.match(line):
            continue
        text = _BULLET.sub("", stripped)
        for sent in _SEGMENTER.segment(text):
            sent = sent.strip()
            if len(sent.split()) >= 3:
                sentences.append(sent)
    return sentences


def _short_transition(sentence: str) -> bool:
    return len(sentence.split()) < 6 and not CITE_RE.search(sentence)


async def judge_batch(batch: list[tuple[int, str, list[str]]], evidence: dict) -> list[_JudgeVerdict]:
    """batch: (global_index, sentence, valid_cited_ids). Judged with LOCAL 0-based indices
    (models renumber unreliably), remapped to global on return. Raises on judge failure."""
    blocks = []
    for local, (_gidx, sentence, cited) in enumerate(batch):
        if cited:
            ev_text = "\n".join(f"  [{cid}]: {evidence[cid].snippet[:800]}" for cid in cited)
        else:
            ev_text = "  NONE"
        blocks.append(f"Sentence {local}: {sentence}\nCited evidence:\n{ev_text}")
    user = "\n\n".join(blocks)
    result, tokens = await llm_service.structured(
        "reasoner", prompts.JUDGE_SYSTEM, user, _JudgeBatch,
        temperature=0.0, max_tokens=220 + 90 * len(batch), retries=1)
    verdicts = result.verdicts
    got = sorted(v.index for v in verdicts)
    if got != list(range(len(batch))):
        if len(verdicts) == len(batch):  # right count, wrong numbering -> remap positionally
            verdicts = [_JudgeVerdict(index=i, label=v.label, reason=v.reason)
                        for i, v in enumerate(verdicts)]
        else:
            raise ValueError(f"judge returned {len(verdicts)} verdicts for {len(batch)} sentences")
    remapped = [_JudgeVerdict(index=batch[v.index][0], label=v.label, reason=v.reason)
                for v in verdicts]
    judge_batch.last_tokens = tokens  # accumulated by caller
    return remapped


def _fallback_verdicts(batch: list[tuple[int, str, list[str]]]) -> list[_JudgeVerdict]:
    out = []
    for idx, sentence, cited in batch:
        if cited:
            out.append(_JudgeVerdict(index=idx, label="partially_supported",
                                     reason="judge unavailable; cited but unverified"))
        elif _short_transition(sentence):
            out.append(_JudgeVerdict(index=idx, label="no_claim", reason="judge unavailable; short transition"))
        else:
            out.append(_JudgeVerdict(index=idx, label="unsupported", reason="judge unavailable; uncited claim"))
    return out


async def citation_checker(state: SwarmState, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    await emitter.emit("citation_checker", "node_started", {})
    draft = state.get("draft") or ""
    evidence = state.get("evidence", {})

    draft_hash = hashlib.sha1(draft.encode()).hexdigest()
    if state.get("audited_hash") == draft_hash and state.get("citation_report"):
        # Same draft as the previous audit (synthesizer reused it) — verdicts are identical.
        await emitter.emit("citation_checker", "node_finished",
                           {"skipped": "draft unchanged — reusing previous audit",
                            "coverage": state["citation_report"].coverage})
        return {}

    sentences = split_sentences(draft)
    tokens_total = 0

    units: list[tuple[int, str, list[str], list[str]]] = []  # idx, sentence, valid_cited, invalid_cited
    for i, sent in enumerate(sentences):
        cited = CITE_RE.findall(sent)
        valid = [c for c in cited if c in evidence]
        invalid = [c for c in cited if c not in evidence]
        units.append((i, sent, valid, invalid))

    verdicts: dict[int, SentenceVerdict] = {}

    # Rule: invalid citation ids -> unsupported without spending judge tokens.
    to_judge = []
    for i, sent, valid, invalid in units:
        if invalid and not valid:
            verdicts[i] = SentenceVerdict(index=i, sentence=sent, cited=invalid, label="unsupported",
                                          reason=f"citation of non-existent evidence {invalid}")
        else:
            to_judge.append((i, sent, valid))

    for start in range(0, len(to_judge), _BATCH_SIZE):
        batch = to_judge[start:start + _BATCH_SIZE]
        try:
            judged = await judge_batch(batch, evidence)
            tokens_total += getattr(judge_batch, "last_tokens", 0)
        except Exception as exc:
            await emitter.emit("citation_checker", "node_started",  # surfaced, not silent
                               {"warning": f"judge batch failed, conservative fallback: {str(exc)[:200]}"})
            judged = _fallback_verdicts(batch)
        by_idx = {v.index: v for v in judged}
        for i, sent, valid in batch:
            jv = by_idx[i]
            verdicts[i] = SentenceVerdict(index=i, sentence=sent, cited=valid,
                                          label=jv.label, reason=jv.reason)

    ordered = [verdicts[i] for i in sorted(verdicts)]
    report = CitationReport.from_verdicts(ordered)

    for v in ordered:
        await emitter.emit("citation_checker", "verdict", v.model_dump(mode="json"))
    await emitter.emit("citation_checker", "citation_summary", {
        "coverage": report.coverage,
        "unsupported_rate": report.unsupported_rate,
        "sentences": len(ordered),
        "labels": {lbl: sum(1 for v in ordered if v.label == lbl)
                   for lbl in ("supported", "partially_supported", "unsupported", "no_claim")},
    })
    await emitter.emit("citation_checker", "node_finished", {"coverage": report.coverage})
    return {"citation_report": report, "token_usage": tokens_total, "audited_hash": draft_hash}
