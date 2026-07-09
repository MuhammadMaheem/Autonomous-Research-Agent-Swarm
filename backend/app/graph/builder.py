"""StateGraph assembly.

START -> planner -> scheduler =Send waves=> {web,code,rag}_agent -> scheduler ... -> synthesizer
      -> citation_checker -> critic -> (planner | finalizer) -> END
"""
from typing import Callable

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.citation_checker import citation_checker
from app.graph.nodes.critic import critic, route_after_critic
from app.graph.nodes.finalizer import finalizer
from app.graph.nodes.planner import planner
from app.graph.nodes.scheduler import dispatch, scheduler
from app.graph.nodes.specialists import code_agent, rag_agent, web_agent
from app.graph.nodes.synthesizer import synthesizer
from app.graph.state import SwarmState


def build_graph(node_overrides: dict[str, Callable] | None = None):
    """Compile the swarm graph. `node_overrides` swaps node implementations for testing."""
    nodes: dict[str, Callable] = {
        "planner": planner,
        "scheduler": scheduler,
        "web_agent": web_agent,
        "code_agent": code_agent,
        "rag_agent": rag_agent,
        "synthesizer": synthesizer,
        "citation_checker": citation_checker,
        "critic": critic,
        "finalizer": finalizer,
    }
    nodes.update(node_overrides or {})

    g = StateGraph(SwarmState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.add_edge(START, "planner")
    g.add_edge("planner", "scheduler")
    g.add_conditional_edges(
        "scheduler", dispatch,
        ["web_agent", "code_agent", "rag_agent", "synthesizer"],
    )
    g.add_edge("web_agent", "scheduler")
    g.add_edge("code_agent", "scheduler")
    g.add_edge("rag_agent", "scheduler")
    g.add_edge("synthesizer", "citation_checker")
    g.add_edge("citation_checker", "critic")
    g.add_conditional_edges("critic", route_after_critic, ["planner", "finalizer"])
    g.add_edge("finalizer", END)
    return g.compile()
