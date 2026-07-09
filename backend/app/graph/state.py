import operator
import re
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

AgentType = Literal["web", "code", "rag"]

CITE_RE = re.compile(r"\[(E\d+_\d+)\]")

# Tolerant matcher for model output quirks: "[ E1_1 ]", "[E1_1, E2_3]", "[E1_1; E2_3]"
_SLOPPY_CITE_RE = re.compile(r"\[\s*(E\d+_\d+(?:\s*[,;]\s*E\d+_\d+)*)\s*\]")


def normalize_citations(text: str) -> str:
    """Rewrite sloppy citation brackets into canonical [E1_1][E2_3] form."""
    def _fix(m: re.Match) -> str:
        ids = re.findall(r"E\d+_\d+", m.group(1))
        return "".join(f"[{i}]" for i in ids)

    return _SLOPPY_CITE_RE.sub(_fix, text)


class SubQuestion(BaseModel):
    id: str = Field(pattern=r"^sq\d+$")
    question: str
    agent: AgentType
    depends_on: list[str] = []
    rationale: str = ""


class ResearchPlan(BaseModel):
    sub_questions: list[SubQuestion]

    def waves(self) -> list[list[str]]:
        """Topological waves (Kahn). Raises ValueError on cycles/unknown deps/duplicates."""
        ids = [sq.id for sq in self.sub_questions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate sub-question ids: {ids}")
        known = set(ids)
        for sq in self.sub_questions:
            unknown = set(sq.depends_on) - known
            if unknown:
                raise ValueError(f"{sq.id} depends on unknown ids: {sorted(unknown)}")
            if sq.id in sq.depends_on:
                raise ValueError(f"{sq.id} depends on itself")
        remaining = {sq.id: set(sq.depends_on) for sq in self.sub_questions}
        waves: list[list[str]] = []
        while remaining:
            ready = sorted(i for i, deps in remaining.items() if not deps)
            if not ready:
                raise ValueError(f"dependency cycle among: {sorted(remaining)}")
            waves.append(ready)
            for i in ready:
                del remaining[i]
            for deps in remaining.values():
                deps.difference_update(ready)
        return waves


class Evidence(BaseModel):
    id: str  # "E{sq_number}_{n}", cited in the draft as [E2_1]
    sub_question_id: str
    source_type: AgentType
    url: str | None = None
    title: str | None = None
    snippet: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Finding(BaseModel):
    sub_question_id: str
    agent: AgentType
    summary: str
    evidence_ids: list[str] = []
    status: Literal["ok", "failed"] = "ok"
    error: str | None = None


VerdictLabel = Literal["supported", "partially_supported", "unsupported", "no_claim"]


class SentenceVerdict(BaseModel):
    index: int
    sentence: str
    cited: list[str] = []
    label: VerdictLabel
    reason: str = ""


class CitationReport(BaseModel):
    verdicts: list[SentenceVerdict]
    coverage: float
    unsupported_rate: float

    @classmethod
    def from_verdicts(cls, verdicts: list[SentenceVerdict]) -> "CitationReport":
        claims = [v for v in verdicts if v.label != "no_claim"]
        if not claims:
            return cls(verdicts=verdicts, coverage=0.0, unsupported_rate=1.0)
        supported = sum(1 for v in claims if v.label == "supported")
        unsupported = sum(1 for v in claims if v.label == "unsupported")
        return cls(
            verdicts=verdicts,
            coverage=round(supported / len(claims), 4),
            unsupported_rate=round(unsupported / len(claims), 4),
        )


class CriticFeedback(BaseModel):
    passed: bool
    weak_sub_questions: list[str] = []
    suggested_sub_questions: list[SubQuestion] = []
    notes: str = ""


def merge_evidence(a: dict[str, Evidence], b: dict[str, Evidence]) -> dict[str, Evidence]:
    return {**a, **b}


class SwarmState(TypedDict, total=False):
    question: str
    plan: ResearchPlan | None
    findings: Annotated[list[Finding], operator.add]
    evidence: Annotated[dict[str, Evidence], merge_evidence]
    draft: str | None
    citation_report: CitationReport | None
    feedback: CriticFeedback | None
    iteration: int
    token_usage: Annotated[int, operator.add]
    evidence_at_draft: int        # evidence count when the draft was written (skip re-synthesis)
    audited_hash: str | None      # sha1 of the last audited draft (skip re-audit)
    best_draft: str | None        # highest-coverage draft across reflection iterations
    best_report: CitationReport | None
    final_report: str | None
    report_dir: str | None


def initial_state(question: str) -> SwarmState:
    return SwarmState(
        question=question,
        plan=None,
        findings=[],
        evidence={},
        draft=None,
        citation_report=None,
        feedback=None,
        iteration=0,
        token_usage=0,
        evidence_at_draft=-1,
        audited_hash=None,
        best_draft=None,
        best_report=None,
        final_report=None,
        report_dir=None,
    )


def sq_number(sq_id: str) -> int:
    return int(sq_id.removeprefix("sq"))
