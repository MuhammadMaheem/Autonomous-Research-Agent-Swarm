"""Integration: the critic reflection loop — doctored low coverage triggers exactly one
replan, second (passing) audit finalizes. No LLM/network: planner/specialists/synthesizer/
finalizer are overridden; the REAL scheduler, dispatch, critic and routing run.
"""
from app.graph.builder import build_graph
from app.graph.state import (
    CitationReport,
    Evidence,
    Finding,
    ResearchPlan,
    SentenceVerdict,
    SubQuestion,
    initial_state,
)


class Fakes:
    def __init__(self):
        self.planner_calls = 0
        self.checker_calls = 0

    async def planner(self, state, config):
        self.planner_calls += 1
        sqs = [SubQuestion(id="sq1", question="a", agent="web")]
        if self.planner_calls > 1:  # replan adds a repair sub-question
            sqs.append(SubQuestion(id="sq2", question="b", agent="web", depends_on=["sq1"]))
        existing = state.get("plan")
        if existing:
            sqs = existing.sub_questions + [s for s in sqs if s.id not in {x.id for x in existing.sub_questions}]
        return {"plan": ResearchPlan(sub_questions=sqs), "token_usage": 0}

    async def web_agent(self, payload, config):
        sq_id = payload["task_sq"]["id"]
        ev = Evidence(id=f"E{sq_id[-1]}_1", sub_question_id=sq_id, source_type="web",
                      url="https://x", title="t", snippet="evidence text")
        return {"findings": [Finding(sub_question_id=sq_id, agent="web", summary="s", evidence_ids=[ev.id])],
                "evidence": {ev.id: ev}, "token_usage": 0}

    async def synthesizer(self, state, config):
        return {"draft": "Draft claim [E1_1].", "token_usage": 0}

    async def checker(self, state, config):
        self.checker_calls += 1
        if self.checker_calls == 1:  # doctored: fail the first audit
            verdicts = [SentenceVerdict(index=0, sentence="x", label="unsupported")]
        else:
            verdicts = [SentenceVerdict(index=0, sentence="x", label="supported")]
        return {"citation_report": CitationReport.from_verdicts(verdicts), "token_usage": 0}

    async def finalizer(self, state, config):
        return {"final_report": "final", "report_dir": "/tmp/none"}


async def _run(monkeypatch, max_iterations: int):
    from app.config import settings
    from app.graph.nodes.critic import _FeedbackSchema

    monkeypatch.setattr(settings, "max_iterations", max_iterations)

    async def fake_structured(role, system, user, schema, **kw):
        assert schema is _FeedbackSchema
        return schema(passed=False, weak_sub_questions=["sq1"], notes="need better sources"), 0

    monkeypatch.setattr("app.services.llm.structured", fake_structured)

    fakes = Fakes()
    graph = build_graph(node_overrides={
        "planner": fakes.planner,
        "web_agent": fakes.web_agent,
        "synthesizer": fakes.synthesizer,
        "citation_checker": fakes.checker,
        "finalizer": fakes.finalizer,
    })
    final = await graph.ainvoke(initial_state("Q"), {"configurable": {"run_id": "test"}, "recursion_limit": 60})
    return fakes, final


async def test_low_coverage_triggers_exactly_one_replan(monkeypatch):
    fakes, final = await _run(monkeypatch, max_iterations=2)
    assert fakes.planner_calls == 2          # initial plan + one replan
    assert fakes.checker_calls == 2          # audit before and after replan
    assert final["iteration"] == 1
    assert final["final_report"] == "final"
    assert final["citation_report"].coverage == 1.0
    assert len(final["plan"].sub_questions) == 2  # replan merged sq2


async def test_iteration_cap_forces_finalize(monkeypatch):
    fakes, final = await _run(monkeypatch, max_iterations=0)  # loop disabled by cap
    assert fakes.planner_calls == 1
    assert fakes.checker_calls == 1
    assert final["iteration"] == 0
    assert final["final_report"] == "final"  # finalized despite coverage 0.0
