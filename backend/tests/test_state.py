import pytest

from app.graph.state import CitationReport, ResearchPlan, SentenceVerdict, SubQuestion


def plan(*sqs):
    return ResearchPlan(sub_questions=list(sqs))


def sq(id, deps=(), agent="web"):
    return SubQuestion(id=id, question=f"q-{id}", agent=agent, depends_on=list(deps))


def test_waves_diamond():
    p = plan(sq("sq1"), sq("sq2"), sq("sq3", deps=["sq1", "sq2"]), sq("sq4", deps=["sq3"]))
    assert p.waves() == [["sq1", "sq2"], ["sq3"], ["sq4"]]


def test_waves_parallel_flat():
    p = plan(sq("sq1"), sq("sq2"), sq("sq3"))
    assert p.waves() == [["sq1", "sq2", "sq3"]]


def test_cycle_raises():
    p = plan(sq("sq1", deps=["sq2"]), sq("sq2", deps=["sq1"]))
    with pytest.raises(ValueError, match="cycle"):
        p.waves()


def test_unknown_dep_raises():
    p = plan(sq("sq1", deps=["sq9"]))
    with pytest.raises(ValueError, match="unknown"):
        p.waves()


def test_duplicate_ids_raise():
    p = plan(sq("sq1"), sq("sq1"))
    with pytest.raises(ValueError, match="duplicate"):
        p.waves()


def test_self_dep_raises():
    p = plan(sq("sq1", deps=["sq1"]))
    with pytest.raises(ValueError):
        p.waves()


def test_coverage_math():
    verdicts = [
        SentenceVerdict(index=0, sentence="a", label="supported"),
        SentenceVerdict(index=1, sentence="b", label="supported"),
        SentenceVerdict(index=2, sentence="c", label="partially_supported"),
        SentenceVerdict(index=3, sentence="d", label="unsupported"),
        SentenceVerdict(index=4, sentence="e", label="no_claim"),
    ]
    rep = CitationReport.from_verdicts(verdicts)
    assert rep.coverage == 0.5           # 2 supported / 4 claim sentences
    assert rep.unsupported_rate == 0.25  # 1 / 4


def test_coverage_no_claims_is_zero():
    rep = CitationReport.from_verdicts([SentenceVerdict(index=0, sentence="x", label="no_claim")])
    assert rep.coverage == 0.0
