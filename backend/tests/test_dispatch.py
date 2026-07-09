from langgraph.types import Send

from app.config import settings
from app.graph.nodes.scheduler import dispatch
from app.graph.state import Finding, ResearchPlan, SubQuestion


def make_state(**over):
    plan = ResearchPlan(sub_questions=[
        SubQuestion(id="sq1", question="a", agent="web"),
        SubQuestion(id="sq2", question="b", agent="code"),
        SubQuestion(id="sq3", question="c", agent="web", depends_on=["sq1", "sq2"]),
    ])
    state = {"question": "Q", "plan": plan, "findings": [], "token_usage": 0}
    state.update(over)
    return state


def finding(sq_id, agent="web", status="ok"):
    return Finding(sub_question_id=sq_id, agent=agent, summary=f"ans-{sq_id}", status=status)


async def test_first_wave_parallel_sends():
    routes = await dispatch(make_state(), {})
    assert isinstance(routes, list) and len(routes) == 2
    targets = {s.node for s in routes}
    assert targets == {"web_agent", "code_agent"}
    assert all(isinstance(s, Send) for s in routes)


async def test_dependent_blocked_until_deps_answered():
    state = make_state(findings=[finding("sq1")])
    routes = await dispatch(state, {})
    assert [s.node for s in routes] == ["code_agent"]  # sq3 still blocked, sq1 answered

    state = make_state(findings=[finding("sq1"), finding("sq2", agent="code")])
    routes = await dispatch(state, {})
    assert len(routes) == 1 and routes[0].node == "web_agent"
    assert routes[0].arg["task_sq"]["id"] == "sq3"
    # dependency context flows into the Send payload
    ctx_ids = {c["sub_question_id"] for c in routes[0].arg["context"]}
    assert ctx_ids == {"sq1", "sq2"}


async def test_failed_dep_still_dispatches_dependent():
    state = make_state(findings=[finding("sq1"), finding("sq2", agent="code", status="failed")])
    routes = await dispatch(state, {})
    assert routes[0].arg["task_sq"]["id"] == "sq3"
    assert {c["sub_question_id"] for c in routes[0].arg["context"]} == {"sq1"}  # failed dep excluded


async def test_all_answered_routes_to_synthesizer():
    state = make_state(findings=[finding("sq1"), finding("sq2"), finding("sq3")])
    assert await dispatch(state, {}) == "synthesizer"


async def test_token_budget_short_circuits():
    state = make_state(token_usage=settings.token_budget + 1)
    assert await dispatch(state, {}) == "synthesizer"
