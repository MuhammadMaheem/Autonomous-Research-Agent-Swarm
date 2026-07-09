# Autonomous Research Agent Swarm

A multi-agent research system (BSAI Final Year Project). A **Planner** decomposes a research
question into a **DAG of sub-questions**; specialist agents (web search, sandboxed Python,
local-corpus RAG) execute them in parallel topological waves; a **Synthesizer** writes a cited
report; a **Citation-Checker** audits every sentence against the retrieved evidence; a
**Critic** loops back to the Planner when citation coverage is low (max 2 reflection
iterations); the frontend shows the **live agent execution trace** over SSE.

![Final report view](screenshots/03-final-report.png)

## Architecture

```
START → planner → scheduler ⇒ Send() waves ⇒ {web_agent | code_agent | rag_agent} → scheduler …
      → synthesizer → citation_checker → critic → (planner ↺ | finalizer) → END
```

- **planner** (`openai/gpt-oss-120b` on Groq): structured-output DAG of 3–6 sub-questions with
  `depends_on` edges; validated by topological sort; delta-only replans on critic feedback.
- **scheduler** (pure Python): dispatches every ready sub-question as a parallel LangGraph
  `Send()`; dependency answers are injected into dependent agents' context; enforces the
  per-run token budget.
- **web_agent**: DuckDuckGo (`ddgs`, keyless) or Tavily (if `TAVILY_API_KEY` set) + page-text
  extraction; every claim in its summary cites evidence ids like `[E2_1]`.
- **code_agent**: LLM-generated Python runs in a sandbox — import allowlist, CPU/memory rlimits,
  network isolation via `unshare -rn`, hard timeout. One repair retry on failure.
- **rag_agent**: BM25 retrieval over `backend/data/corpus/` behind a pluggable `Retriever`
  protocol (hybrid Chroma+BM25 is a drop-in extension point).
- **citation_checker** (novel part 1): markdown-aware sentence splitting (pysbd), per-sentence
  LLM judging against *only* the cited evidence → `supported / partially_supported /
  unsupported / no_claim`; coverage = supported / claim sentences. Invalid citation ids are
  ruled unsupported without spending tokens; failed judge batches fall back conservatively.
- **critic** (novel part 2): coverage gate (default 0.75). Below it, produces targeted feedback
  and new sub-questions, loops to the planner — hard-capped at 2 iterations, `recursion_limit`
  safety net. The **best-coverage draft** across iterations is what gets published (reflection
  can regress).
- **finalizer**: renumbers `[E2_1]` → `[1]` by first appearance, appends references + audit
  footer, writes `report.md` and `report.pdf` (headless chromium).

State is a `TypedDict` with reducer-merged fields (`operator.add` for findings/tokens, dict
merge for evidence) so parallel agent writes are safe. All nodes emit typed `TraceEvent`s to an
event bus → SQLite (replayable) + SSE (live UI).

## Stack

Python 3.13+/uv · LangGraph 1.x · langchain-groq (`gpt-oss-120b` reasoner, `llama-3.1-8b-instant`
workers) · FastAPI + SSE · SQLite (aiosqlite) · Next.js 15 + React Flow + Tailwind · pysbd,
rank-bm25, ddgs, trafilatura · pytest.

## Setup

Prereqs: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, chromium (for PDF export +
screenshots), Linux (sandbox uses `unshare`; degrades gracefully without it).

```bash
# 1. backend
cd backend
cp .env.example .env        # add GROQ_API_KEY (free, no card: console.groq.com)
                            # optional: TAVILY_API_KEY (1000 free credits/mo: app.tavily.com)
uv sync
uv run python scripts/smoke_keys.py   # verify keys

# 2. run the pipeline from the CLI (no server needed)
uv run python -m app.cli "How does RAG reduce hallucination in LLMs?" \
    [--mock] [--no-critic] [--no-rag] [--events-out run.jsonl]

# 3. full stack
bash scripts/serve.sh                 # FastAPI on :8000
cd ../frontend && npm install && bash scripts/dev.sh   # Next.js on :3000
# open http://localhost:3000
```

Tests: `cd backend && uv run pytest` (19 tests: DAG validation, wave dispatch, citation
mechanics, reflection-loop integration with doctored coverage).

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/research` `{question, use_rag?, no_critic?, mock?}` | start a run → `{run_id}` |
| `GET /api/research` | run history |
| `GET /api/research/{id}` | status + result (plan, verdicts, evidence) |
| `GET /api/research/{id}/events` | SSE trace — replays persisted events, then streams live |
| `GET /api/research/{id}/report.md` / `report.pdf` | final report |

## Evaluation (viva methodology)

Research questions: **RQ1** does DAG decomposition + specialist agents improve citation
coverage vs a single search agent? **RQ2** does the critic loop help? (ablation) **RQ3** how
reliable is the automated checker vs humans?

- Dataset: `backend/eval/dataset/questions.jsonl` — 30 questions (12 web / 8 computational /
  6 multi-hop / 4 adversarial).
- Systems: `swarm` (full), `no-critic` (ablation), `baseline` (single ReAct-style agent, same
  model + search + audit, no planner/swarm/critic).

```bash
cd backend
uv run python -m eval.run_eval --system swarm    --split smoke   # or --split full
uv run python -m eval.run_eval --system baseline --split smoke
uv run python -m eval.run_eval --system no-critic --split smoke
uv run python -m eval.metrics --paired swarm baseline
```

Metrics: automated citation coverage + unsupported rate per system, paired per-question deltas
with an exact sign test, plus checker-vs-human Cohen's kappa once `eval/labels/human_labels.csv`
exists (protocol in `eval/labels/rubric.md`). Smoke result (n=2, illustrative): swarm 50.0%
mean coverage vs baseline 10.5%; the baseline structurally cannot answer computational
questions (no code agent).

Free-tier note: a full 30-question × 3-system eval ≈ 90 runs ≈ 25–35 LLM calls each. On Groq's
free tier (200k reasoner tokens/day) spread it over ~3 days, or it costs ~$2–3 on the paid tier.

## Configuration (backend/.env or env vars)

`GROQ_API_KEY` (required) · `TAVILY_API_KEY` (optional; ddgs fallback otherwise) ·
`MODEL_REASONER` / `MODEL_WORKER` · `COVERAGE_THRESHOLD` (0.75) · `MAX_ITERATIONS` (2) ·
`MAX_SUBQUESTIONS` (6) · `TOKEN_BUDGET` (80000/run) · `LLM_CONCURRENCY` (2).

## Repo layout

```
backend/
  app/graph/        # state, prompts, builder, nodes/ (planner, scheduler, specialists,
                    # synthesizer, citation_checker, critic, finalizer)
  app/services/     # llm (tiering/backoff), search, sandbox, rag
  app/api/          # FastAPI routes + RunManager        app/db/  # SQLite store
  app/cli.py        # terminal runner with rich trace
  eval/             # dataset, baseline, run_eval, metrics, labeling rubric
  data/corpus/      # demo RAG corpus     data/golden/  # recorded event streams
frontend/
  app/              # home + runs/[id] (live DAG, trace, report, citation audit)
  components/       # dag-view (React Flow), event-timeline, report-view, audit-panel
screenshots/        # demo captures (query, live trace, report, audit)
```

## Known limitations

- Web evidence quality bounds coverage: ddgs returns short snippets (top-2 pages get full-text
  extraction). Tavily improves this materially — set `TAVILY_API_KEY`.
- RAG retriever is BM25-only over a small curated corpus; the hybrid dense+BM25 design is
  specced behind the `Retriever` protocol but not implemented.
- Reports are audited at sentence level, so the synthesizer is instructed to write prose only
  (tables would hide citations from the audit).
- Sandbox threat model: defends against accidental/LLM-generated misbehaviour (allowlist,
  rlimits, no network), not against a determined adversary; only system-generated code runs.
- Single-process, single-user: no auth, in-flight runs die with the server (events up to that
  point persist).
# Autonomous-Research-Agent-Swarm
