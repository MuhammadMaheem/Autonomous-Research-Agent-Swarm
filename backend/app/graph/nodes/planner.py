"""Planner node: decompose the research question into a DAG of sub-questions.

Fresh plan on first entry; delta replan when critic feedback is present.
Validation: pydantic schema + topological (cycle/unknown-dep) check, one retry with
the validation error in-prompt, then a deterministic flat fallback plan.
"""
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.events import get_emitter
from app.graph import prompts
from app.graph.state import CriticFeedback, ResearchPlan, SubQuestion, SwarmState
from app.graph.nodes.common import cfg_flag
from app.services import llm as llm_service


def fallback_plan(question: str) -> ResearchPlan:
    q = question.rstrip("?")
    return ResearchPlan(sub_questions=[
        SubQuestion(id="sq1", question=f"What is {q}? Key definitions and background.",
                    agent="web", rationale="fallback: background"),
        SubQuestion(id="sq2", question=f"What current data, statistics or findings exist about {q}?",
                    agent="web", rationale="fallback: evidence"),
        SubQuestion(id="sq3", question=f"What are the main open challenges or recent developments regarding {q}?",
                    agent="web", depends_on=["sq1"], rationale="fallback: synthesis"),
    ])


def _findings_digest(state: SwarmState) -> str:
    lines = []
    for f in state.get("findings", []):
        status = "OK" if f.status == "ok" else f"FAILED ({f.error})"
        lines.append(f"- {f.sub_question_id} [{status}]: {f.summary[:200]}")
    return "\n".join(lines) or "(none)"


async def planner(state: SwarmState, config: RunnableConfig) -> dict:
    emitter = get_emitter(config)
    await emitter.emit("planner", "node_started", {"iteration": state.get("iteration", 0)})
    question = state["question"]
    use_rag = cfg_flag(config, "use_rag", True)
    feedback: CriticFeedback | None = state.get("feedback")
    existing: ResearchPlan | None = state.get("plan")
    replan = bool(feedback and not feedback.passed and existing)
    tokens_total = 0

    if replan:
        rag_opt = ", rag (local corpus)" if use_rag else ""
        system = prompts.REPLAN_SYSTEM.format(rag_opt=rag_opt)
        suggested = "\n".join(
            f"- {s.id}: {s.question} (agent={s.agent})" for s in feedback.suggested_sub_questions
        ) or "(none)"
        user = (
            f"Research question: {question}\n\n"
            f"Current plan:\n" +
            "\n".join(f"- {sq.id} ({sq.agent}, deps={sq.depends_on}): {sq.question}"
                      for sq in existing.sub_questions) +
            f"\n\nWhat each sub-question found:\n{_findings_digest(state)}\n\n"
            f"Critic feedback: {feedback.notes}\n"
            f"Weak sub-questions: {feedback.weak_sub_questions}\n"
            f"Critic-suggested additions (refine or adopt):\n{suggested}\n\n"
            f"Existing ids go up to sq{len(existing.sub_questions)}; new ids start at "
            f"sq{len(existing.sub_questions) + 1}."
        )
    else:
        rag_line = prompts.PLANNER_RAG_LINE.format(
            corpus_desc="LLM agents, retrieval-augmented generation and citation evaluation"
        ) if use_rag else ""
        system = prompts.PLANNER_SYSTEM.format(max_sq=settings.max_subquestions, rag_line=rag_line)
        user = f"Research question: {question}"

    plan: ResearchPlan | None = None
    for attempt in range(2):
        try:
            candidate, toks = await llm_service.structured(
                "reasoner", system, user, ResearchPlan, max_tokens=1200)
            tokens_total += toks
            if replan:
                merged = ResearchPlan(
                    sub_questions=[*existing.sub_questions, *candidate.sub_questions])
                if len(merged.sub_questions) > settings.max_subquestions_total:
                    merged.sub_questions = merged.sub_questions[:settings.max_subquestions_total]
                candidate = merged
            elif len(candidate.sub_questions) > settings.max_subquestions:
                candidate.sub_questions = candidate.sub_questions[:settings.max_subquestions]
            candidate.waves()  # raises on cycle / unknown dep / duplicates
            plan = candidate
            break
        except Exception as exc:
            user = f"{user}\n\nYour previous plan was invalid: {str(exc)[:400]}. Fix it."
            if attempt == 1:
                plan = existing if replan else fallback_plan(question)

    await emitter.emit("planner", "plan_ready", {
        "plan": plan.model_dump(mode="json"),
        "replan": replan,
        "iteration": state.get("iteration", 0),
    })
    await emitter.emit("planner", "node_finished", {"sub_questions": len(plan.sub_questions)})
    return {"plan": plan, "token_usage": tokens_total}
