# Research Agent Swarm — Full Project Explainer

> A multi-agent, LangGraph-orchestrated research system that
> decomposes a question into a DAG of sub-questions, answers them in parallel with specialist
> agents, writes a cited report, and **audits its own citations sentence by sentence** — looping
> back to re-plan if the audit fails. This document explains what every part does, why it exists,
> and the concepts behind it, so you can explain/defend the project end to end.

---

## 1. The one-paragraph pitch

Most "AI research assistants" search the web, paste text into an LLM, and print whatever comes
out — with no way to know if the claims are actually backed by the sources. This project's core
idea is: **treat citation correctness as a first-class, machine-checked signal**, not a hope. A
Planner breaks the question into sub-questions. Specialist agents (web / code / RAG) answer them,
each attaching evidence IDs to every claim. A Synthesizer writes the final report, still citing
those IDs. A Citation-Checker then re-reads the report **sentence by sentence** and asks an LLM
"does the cited evidence actually support this sentence?" — producing a numeric coverage score.
If coverage is too low, a Critic diagnoses what's missing and sends the Planner back to fill the
gap — up to twice. Only then is the report finalized, renumbered, and exported to Markdown/PDF.

---

## 2. High-level architecture

```
START
  │
  ▼
planner ──────────────► scheduler ══Send()══► { web_agent | code_agent | rag_agent }
  ▲                         │  ▲                          │
  │                         │  └──────────────────────────┘  (loops until DAG done)
  │                         ▼
  │                    synthesizer
  │                         │
  │                         ▼
  │                  citation_checker
  │                         │
  │                         ▼
  └──────────────────── critic ─────────────► finalizer ─► END
       (loop back if           (pass / budget /
        coverage < threshold)   max iterations)
```

This is a **LangGraph `StateGraph`**: a directed graph of async Python functions ("nodes") that
all read and write a single shared `state` object. LangGraph handles routing between nodes,
running independent branches concurrently, and merging their state writes back together.

### Why a graph instead of a linear pipeline or a single ReAct agent?

- **Parallelism**: independent sub-questions (e.g. "what is RAG?" and "what is a vector database?")
  have no data dependency, so they can be answered by different agents *at the same time*.
- **Specialization**: a web-search agent and a Python-execution agent need completely different
  tools and prompts — cramming both into one generic agent produces worse results than routing
  each sub-question to the right specialist.
- **Self-correction**: a single-pass agent has no way to notice "I under-cited this claim" and
  fix it. The graph has an explicit feedback edge (`critic → planner`) that makes reflection a
  first-class part of the control flow, not an afterthought.

The `eval/baseline.py` system is a deliberate **ablation**: same LLM, same search tool, same
citation audit, but no planner/swarm/critic — just a single ReAct-style loop. It exists so the
project can empirically answer "does the multi-agent structure actually help?" (see §8).

---

## 3. The shared state (`app/graph/state.py`)

Every node reads/writes a `SwarmState`, a `TypedDict` with these fields:

| Field | Type | Purpose |
|---|---|---|
| `question` | `str` | the original user question |
| `plan` | `ResearchPlan \| None` | current DAG of sub-questions |
| `findings` | `list[Finding]` (append-merged) | one per completed sub-question |
| `evidence` | `dict[str, Evidence]` (dict-merged) | evidence store, keyed by ID like `E2_1` |
| `draft` | `str \| None` | the synthesizer's current report text |
| `citation_report` | `CitationReport \| None` | per-sentence audit of `draft` |
| `feedback` | `CriticFeedback \| None` | critic's verdict + replan suggestions |
| `iteration` | `int` | number of critic loop-backs so far |
| `token_usage` | `int` (sum-merged) | running LLM token spend for the whole run |
| `best_draft` / `best_report` | — | highest-coverage draft seen across iterations |
| `final_report`, `report_dir` | — | finalizer output |

### The concurrency trick: reducer functions

LangGraph nodes can run **in parallel** (e.g. three specialist agents in the same wave). If two
parallel nodes both tried to do `state["findings"] = state["findings"] + [new]`, one write would
silently clobber the other. LangGraph solves this with **`Annotated[type, reducer]`**:

```python
findings: Annotated[list[Finding], operator.add]          # concatenate lists
evidence: Annotated[dict[str, Evidence], merge_evidence]   # merge dicts
token_usage: Annotated[int, operator.add]                  # sum integers
```

Each parallel node returns *only the delta it produced* (e.g. `{"findings": [one_finding]}`), and
LangGraph combines all the deltas from a wave using the declared reducer. This is what makes
"three agents write to shared state simultaneously" both safe and simple — no locks, no manual
merging in the node code.

### `ResearchPlan.waves()` — topological sort (Kahn's algorithm)

The plan is a DAG: each `SubQuestion` has `depends_on: list[str]`. `waves()` computes the
execution order as a list of "waves" — each wave is a list of sub-question IDs that can run in
parallel because their dependencies are already satisfied:

```python
remaining = {sq.id: set(sq.depends_on) for sq in self.sub_questions}
while remaining:
    ready = sorted(i for i, deps in remaining.items() if not deps)
    if not ready:
        raise ValueError("dependency cycle")
    waves.append(ready)
    for i in ready: del remaining[i]
    for deps in remaining.values(): deps.difference_update(ready)
```

This is textbook **Kahn's algorithm** for topological sorting: repeatedly peel off nodes with no
remaining incoming edges. It also validates the plan — duplicate IDs, references to unknown IDs,
self-dependencies, and cycles all raise `ValueError`, which the planner node catches and retries.

### Evidence IDs and the citation format

Evidence is identified as `E{sub_question_number}_{n}`, e.g. `E2_1` = the first piece of evidence
gathered for `sq2`. Every specialist agent cites its own evidence like `[E2_1]`; the synthesizer
copies those same IDs into the final report. `normalize_citations()` cleans up sloppy LLM output
(`[ E1_1 ]`, `[E1_1, E2_3]`) into canonical bracket-per-ID form before anything downstream parses
it — LLMs are inconsistent about exact formatting, so this regex-based normalization step avoids
losing citations to a formatting quirk.

---

## 4. Node-by-node walkthrough

### 4.1 `planner` (`app/graph/nodes/planner.py`)

**Job**: turn the natural-language question into a `ResearchPlan` (a DAG of `SubQuestion`s), each
tagged with which specialist agent should handle it (`web` / `code` / `rag`).

- Uses the **reasoner** LLM tier (`openai/gpt-oss-120b` on Groq) with **structured output**
  (JSON mode + Pydantic validation) — see §5.
- **First entry**: fresh plan from `PLANNER_SYSTEM` prompt, capped at `max_subquestions` (6).
- **Replan** (after critic feedback): instead of regenerating everything, it asks the LLM for
  **1–3 new** sub-questions targeting the gap, then **appends** them to the existing plan
  (`REPLAN_SYSTEM` prompt). This is a deliberate design choice — a full regeneration would throw
  away work already done (and its evidence); a delta-plan is cheaper and safer.
- **Validation loop**: `candidate.waves()` is called to catch cycles/unknown deps. On failure, the
  error message is fed back into the prompt for **one retry**. If that also fails, it falls back
  to a **deterministic 3-question flat plan** (`fallback_plan`) — the system must never crash just
  because the planner LLM produced malformed JSON.

### 4.2 `scheduler` / `dispatch` (`app/graph/nodes/scheduler.py`)

This is the most "graph-native" part of the system. `scheduler` itself is a no-op node — all the
logic lives in `dispatch`, a **conditional edge function** that LangGraph calls after `scheduler`
to decide where to route next.

`dispatch` returns either:
- a **string** (`"synthesizer"`) — a normal single-target edge, or
- a **list of `Send(...)` objects** — LangGraph's mechanism for fanning out to N parallel node
  invocations, each with its own private payload (not a diff of the shared state).

```python
return [
    Send(f"{sq.agent}_agent", {"task_sq": sq.model_dump(...), "context": deps, "question": ...})
    for sq in ready
]
```

Each ready sub-question becomes one `Send()` to the matching specialist node
(`web_agent`/`code_agent`/`rag_agent`). Each of those specialist nodes' outputs edge back to
`scheduler`, so control returns to `dispatch` again — which computes the **next** wave (whatever
sub-questions just became "ready" now that their dependencies are answered), or routes to
`synthesizer` once everything is done. This loop *is* the "waves" execution of the DAG — no
explicit wave-index counter is needed; readiness is recomputed from `answered = {findings...}`
each time.

**Guardrails baked into `dispatch`**:
- Empty plan → straight to synthesizer.
- All sub-questions answered → synthesizer.
- `token_usage > token_budget` → **abort remaining sub-questions**, go straight to synthesizer
  with whatever evidence exists so far (graceful degradation instead of an expensive runaway run).
- No ready sub-questions but some pending (should be unreachable given a validated DAG) →
  synthesizer, to guarantee **the graph can never deadlock**.

`_dep_findings` injects only the **findings of a sub-question's own dependencies** into its
payload — not the whole state — so a specialist agent's prompt only ever sees the specific prior
answers it actually depends on.

### 4.3 Specialist agents (`app/graph/nodes/specialists.py`)

All three share a contract: take a `{task_sq, context, question}` payload from a `Send()`, and
**never raise** — every specialist wraps its body in try/except and turns any failure into
`Finding(status="failed", error=...)`. This is important: one bad sub-question (e.g. a search
engine timeout) must not crash the whole run — the scheduler/synthesizer treat failed findings as
"answer unavailable" and move on.

**`web_agent`**
1. Calls the active `SearchProvider` (Tavily or DuckDuckGo, see §6) for the sub-question text.
2. If zero results, retries once with a compacted keyword query (long natural-language questions
   trip up some search backends).
3. For the top 2 results, fetches the full page and extracts clean article text via `trafilatura`
   (search snippets are too short to ground claims reliably).
4. Wraps each result as an `Evidence` object with a fresh `E{n}_{k}` ID.
5. Calls `summarize_with_citations` (shared helper, **worker**-tier LLM) to produce a 3–6 sentence
   answer to the sub-question, citing only the evidence just gathered.

**`code_agent`**
1. LLM (reasoner tier, temperature 0) generates a standalone Python script from `CODEGEN_SYSTEM`
   (allowed imports only, no I/O, must `print()` the answer).
2. Runs it in the sandbox (`app/services/sandbox.py`, see §6).
3. **One repair attempt**: if the script fails, the error + original code are fed back to the LLM
   for a fix, then re-executed once more.
4. The script + its stdout become a single `Evidence` entry, then summarized like the web agent.

**`rag_agent`**
1. Queries the local BM25 retriever over `backend/data/corpus/` (see §6).
2. Wraps each retrieved chunk as `Evidence`, then summarizes with citations, same pattern.

**Anti-fabrication prompt discipline** (`SUMMARIZE_SYSTEM`): the shared summarizer prompt
explicitly instructs the LLM that if the evidence doesn't mention the sub-question's actual
subject, it must say so ("The retrieved evidence does not mention X...") rather than inventing
plausible-sounding facts. This matters because search results are often *tangentially* related,
and an ungrounded LLM will happily fill gaps with hallucinated specifics.

### 4.4 `synthesizer` (`app/graph/nodes/synthesizer.py`)

Composes the final draft report from **all** findings + the full evidence catalog (not just the
latest wave). Two efficiency/correctness details:

- **Skip-if-unchanged**: if a replan produced zero new evidence (e.g. the new sub-questions'
  agents also failed), regenerating an identical draft would waste tokens re-auditing the same
  text — so it compares `evidence_at_draft` (evidence count when the last draft was written) to
  the current count and short-circuits if nothing changed.
- **Streaming**: uses `stream_complete`, emitting `draft_token` trace events as text arrives, so
  the frontend can show the report being written live, token by token (`ReportView` in the UI).

The `SYNTHESIZER_SYSTEM` prompt is the second layer of the anti-hallucination design: "if no
evidence supports a claim, do not write it," prose-only (no tables — tables would hide claims
from the sentence-level auditor described next), and reuse the specific evidence IDs from
findings rather than inventing new citation patterns.

### 4.5 `citation_checker` (`app/graph/nodes/citation_checker.py`) — **novel contribution #1**

This is the heart of the "trust but verify" design. Given the draft and the evidence store, it
produces a `CitationReport` with a numeric **coverage** score.

**Step 1 — sentence segmentation** (`split_sentences`): markdown-aware splitting using
[`pysbd`](https://github.com/nipunsadvilkar/pySBD) (Python Sentence Boundary Disambiguation,
which handles abbreviations/decimals/etc. far better than a naive `.split(". ")`). Headers, code
fences, tables, and images are skipped entirely (they're not "claims" to audit); bullet markers
are stripped so the sentence inside a bullet is still evaluated on its own merits.

**Step 2 — citation extraction & rule-based short-circuit**: for each sentence, `CITE_RE` finds
`[E\d+_\d+]` patterns and splits them into `valid` (exists in the evidence store) vs `invalid`
(doesn't — e.g. a hallucinated ID). **Any sentence whose only citations are invalid is
automatically labeled `unsupported` — no LLM call spent.** This is a cheap, 100%-reliable rule
that also protects against a subtle failure mode: an LLM "judge" might be fooled into rating a
confidently-worded but fabricated-ID sentence as plausible; a hard rule can't be fooled that way.

**Step 3 — LLM judging** (`judge_batch`): remaining sentences are batched (6 at a time) and sent
to the reasoner LLM with **only the text of their own cited evidence** — the judge never sees the
full corpus, so it can't "connect the dots" itself; it can only verify what's actually written in
the cited snippet. Labels: `supported`, `partially_supported`, `unsupported`, `no_claim` (for
non-factual sentences like transitions — these are excluded from the coverage denominator).

A subtlety: the judge is asked to use **local 0-based indices per batch** rather than global
sentence indices, because LLMs are unreliable at echoing back arbitrary large numbers correctly;
`judge_batch` remaps local→global indices after the fact, and even self-heals if the model
returns the right *count* of verdicts but garbled indices (falls back to positional mapping).

**Step 4 — graceful degradation**: if a judge batch fails twice (LLM error, malformed JSON), a
**conservative rule-based fallback** kicks in instead of blocking the run: cited sentences become
`partially_supported`, uncited claim-like sentences become `unsupported`, short uncited fragments
become `no_claim`. The citation checker is designed to **always produce a report**, never throw.

**Step 5 — coverage math** (`CitationReport.from_verdicts`):
```
claims = sentences where label != "no_claim"
coverage = count(supported) / count(claims)
unsupported_rate = count(unsupported) / count(claims)
```

**Caching**: a SHA1 hash of the draft (`audited_hash`) lets a re-entry into this node (after a
no-op synthesizer skip) reuse the previous audit instead of re-running the whole judge pipeline.

### 4.6 `critic` (`app/graph/nodes/critic.py`) — **novel contribution #2**

Implements the **reflection loop**. Given the citation report:

- If `no_critic` flag is set (ablation mode), or `coverage >= coverage_threshold` (default 0.75),
  or `iteration >= max_iterations` (hard cap of 2) → **pass**, route to `finalizer`.
- Otherwise → **fail**: take up to 8 of the worst-scoring sentences (`unsupported` /
  `partially_supported`), ask the LLM (`CRITIC_SYSTEM`) to diagnose which sub-questions are weak
  and suggest 1–3 new sub-questions to fill the gap. This `CriticFeedback` is what the planner's
  replan branch consumes.
- **Best-draft tracking**: because reflection can *regress* (a replan's new evidence might produce
  a worse-cited draft, or its agents might fail entirely), the critic keeps `best_draft` /
  `best_report` — whichever iteration had the highest coverage — and the **finalizer publishes the
  best one seen across all iterations, not necessarily the last one**. This is a subtle but
  important correctness choice: naively "always use the latest draft" could make the reflection
  loop actively harmful in the worst case.

`route_after_critic` is the conditional edge: `finalizer` if `feedback.passed`, else back to
`planner`. Combined with the `recursion_limit: 60` set in `runner.py` and the hard
`max_iterations` cap, there are **two independent safety nets** against infinite loops.

### 4.7 `finalizer` (`app/graph/nodes/finalizer.py`)

- Chooses the best-coverage draft (as above).
- **`renumber_citations`**: rewrites `[E2_1]`-style internal IDs into reader-facing `[1]`, `[2]`,
  ... in **order of first appearance** in the text — the internal IDs are useful for pipeline
  bookkeeping but meaningless to a reader; the renumbering makes the final report look like a
  normal cited document.
- Appends a `## References` section (one line per cited evidence, with source type and retrieval
  date) and an audit footer summarizing coverage and how many reflection iterations ran — this
  turns the internal audit trail into a transparency feature of the delivered report.
- Writes `report.md`, and if a headless Chromium binary is available, renders it to `report.pdf`
  by converting Markdown→HTML→PDF via `subprocess` (`--headless=new --print-to-pdf=...`). PDF
  generation is best-effort — its absence never fails the run.

---

## 5. The LLM access layer (`app/services/llm.py`)

This module is the single choke point through which **every** LLM call in the system passes. It
solves three problems that show up constantly when building on free-tier LLM APIs:

### 5.1 Model tiering
Two roles, mapped to two different Groq models:
- **`reasoner`** (`openai/gpt-oss-120b`, 200k tokens/day free): planning, replanning, critic
  feedback, citation judging, code generation, synthesis — anything requiring real reasoning.
- **`worker`** (`llama-3.1-8b-instant`, 500k tokens/day free): the repetitive, low-stakes
  "summarize this evidence with citations" calls that happen once per sub-question per specialist.

This is a cost/quality tradeoff pattern common in production LLM systems: don't pay
reasoning-model prices for tasks a fast/cheap model handles fine.

### 5.2 Structured output (`structured()`)
LLMs don't reliably emit valid JSON on the first try. `structured()`:
1. Calls the LLM in **JSON mode** (`response_format: json_object`, a Groq/OpenAI-compatible flag
   that constrains the model's output to be valid JSON syntactically).
2. Extracts the JSON object via regex, then validates it against a **Pydantic schema**
   (`schema.model_validate(...)`).
3. On `ValidationError`/parse failure, **appends the exact error message to the prompt** and
   retries (default: 2 retries) — this "self-repair via error-in-context" pattern is far more
   reliable than blindly retrying the same prompt.

This is used for `ResearchPlan`, `CriticFeedback`, and the citation judge's `_JudgeBatch` — every
place where downstream code needs a strongly-typed object, not free text.

### 5.3 Retry/backoff + daily-limit fallback
- `tenacity.AsyncRetrying` with **exponential backoff + jitter** (`wait_random_exponential`)
  handles transient errors: rate limits, timeouts, 5xx — up to 7 attempts.
- **Daily quota exhaustion is different from a transient rate limit** — retrying within the same
  day won't help. `_is_daily_limit()` detects this specific error pattern and instead marks that
  model as `_daily_limited` for the rest of the process, causing `_model_for("reasoner")` to fall
  through to `settings.reasoner_fallbacks` (two backup models) — keeping the whole pipeline
  running even after burning through one model's free daily allowance.
- A global `asyncio.Semaphore(llm_concurrency=2)` caps in-flight LLM calls so parallel specialist
  waves don't all hit the API simultaneously and trip rate limits.

### 5.4 Streaming (`stream_complete`)
Used only by the synthesizer, so the frontend can render the report as it's generated. Buffers
small chunks (≥48 chars) before emitting a trace event (to avoid flooding the SSE connection with
one event per token), retries the *entire stream* on a transient failure (signalling `reset=True`
so the UI clears partial output instead of duplicating it), and falls back to a non-streaming call
as a last resort after repeated stream failures.

---

## 6. Supporting services

### 6.1 `search.py` — pluggable web search
A `SearchProvider` protocol with three implementations, selected by `get_search_provider()`:
- **`TavilyProvider`** — used automatically if `TAVILY_API_KEY` is set; a paid-tier-friendly search
  API returning fuller content per result.
- **`DDGSProvider`** — keyless fallback via the `ddgs` package. Tries three backends in sequence
  (`duckduckgo`, `bing`, then ddgs's own auto-selection) because individual scraping backends
  behind `ddgs` are flaky/rate-limited; failing over rather than surfacing one backend's timeout
  materially improves reliability on the free tier.
- **`MockSearchProvider`** — deterministic canned results for `--mock` runs (tests, demos, offline
  development without burning API quota).

`enrich_with_page_text` fetches the top-2 result URLs and runs `trafilatura.extract()` (a
boilerplate-stripping HTML→clean-text extractor) to get full article text instead of a 1–2 line
snippet — snippets alone are usually too thin to support a specific, citable claim.

### 6.2 `sandbox.py` — safe code execution
Defends the system against **accidental** LLM-generated misbehavior (infinite loops, huge memory
allocation, disallowed imports) — explicitly *not* against a determined adversary, since only
system-generated code (never user input) ever reaches it. Layers, in order:
1. **Static import allowlist**: regex-scans for `import X` / `from X import` and rejects anything
   outside a small safe set (`math`, `statistics`, `numpy`, etc.) *before* execution.
2. **`resource.setrlimit`** (POSIX) caps CPU time, virtual memory (1 GiB), max file size, and open
   file descriptors — applied via `preexec_fn` in the child process.
3. **Network isolation**: if the `unshare` binary is available, the script runs inside
   `unshare -rn` (a new user + network namespace with no interfaces) — the process is not
   network-capable at the OS level, not just "asked nicely" not to make requests. Degrades
   gracefully (skips this layer) on systems without `unshare`.
4. **Hard wall-clock timeout** via `asyncio.wait_for(..., timeout=sandbox_timeout_s)`, killing the
   subprocess if it overruns.

### 6.3 `rag.py` — local corpus retrieval
`BM25Retriever` implements classic **BM25 ranking** (via `rank_bm25`) over the markdown files in
`backend/data/corpus/`: files are chunked into ~220-word paragraphs, tokenized (lowercase
alphanumerics), and scored against the query's tokenized terms. BM25 is a strong, cheap,
embedding-free baseline for keyword-based retrieval — appropriate for a small curated demo corpus
where an expensive vector index would be overkill. The `Retriever` protocol is deliberately
designed as a swap point: the README explicitly notes a hybrid dense+BM25 retriever could replace
this without touching `rag_agent` at all — a clean **strategy pattern** for extension.

---

## 7. Observability: the event bus, SQLite, and live SSE

Every node emits typed `TraceEvent`s (`app/events.py`) through an `EventEmitter`. This is a
classic **pub/sub** design: nodes don't know who's listening — they just call
`emitter.emit(node, event_type, payload)`, and a list of **sinks** (subscribed callables) fan out:

- **CLI mode** (`app/cli.py`): a `rich`-formatted console renderer sink prints colored, styled
  trace lines live as the pipeline runs.
- **Server mode** (`app/api/run_manager.py`): two sinks — `store.insert_event` (persists every
  event to SQLite) and `RunManager._fanout` (pushes to per-run `asyncio.Queue`s, one per connected
  SSE client).

### Why persist events at all, not just stream them live?
Because a browser tab can disconnect and reconnect mid-run (or load a page for a run that already
finished). The `/api/research/{id}/events` SSE endpoint **replays all persisted events from
SQLite first**, then switches to live streaming from the subscriber queue — a reconnecting client
always sees the full history before continuing live, and a client that opens a page for an
already-finished run just gets the full replay with no live phase needed. The subscribe-then-replay
ordering in `routes.py` (`q = manager.subscribe(run_id)` happens **before** the DB replay loop) is
deliberately structured so no event can be emitted and missed in the gap between "read from DB"
and "start listening live."

`RunManager` runs each research request as a **detached `asyncio.Task`** (`asyncio.create_task`),
so the HTTP request that kicks off a run returns immediately with a `run_id`, and the actual
multi-minute agent pipeline runs in the background — the frontend polls/streams progress
separately. This single-process, in-memory task model is explicitly called out in the README as a
known limitation (no auth, in-flight runs die if the server restarts) — an appropriate scope
tradeoff for a demo system, not a production SaaS.

---

## 8. Evaluation methodology (`backend/eval/`)

The evaluation is framed around empirical research questions, not just "it works on my machine":

- **RQ1**: does DAG decomposition + specialist agents improve citation coverage vs. a single
  search agent? → compare `swarm` vs `baseline` (`eval/baseline.py`, a single ReAct-style loop
  using the *same* reasoner model, *same* search provider, and *same* citation-audit code — so any
  measured difference is attributable to the multi-agent structure, not confounding factors).
- **RQ2**: does the critic/reflection loop help? → **ablation**: `swarm` vs `no-critic` (same
  system, critic auto-passes without looping).
- **RQ3**: how reliable is the automated citation checker compared to human judgment? →
  **Cohen's kappa** between checker labels and `eval/labels/human_labels.csv` (a manual labeling
  protocol defined in `eval/labels/rubric.md`).

`eval/run_eval.py` runs each dataset question (`eval/dataset/questions.jsonl`, categorized
web/computational/multi-hop/adversarial) through a chosen system and appends a result row —
JSONL, append-only, so partial runs across multiple days (to respect free-tier daily token caps)
naturally accumulate. `eval/metrics.py` aggregates: mean coverage/unsupported-rate per system,
**paired per-question deltas** (both systems answer the *same* question, so the comparison
controls for question difficulty), and an **exact sign test** (binomial test on the sign of paired
differences — appropriate given the very small sample sizes typical of a free-tier-constrained
eval) rather than a t-test, which would be a poor fit for n≈2–30 paired samples.

---

## 9. Frontend (`frontend/`) — Next.js 15 + React Flow + SSE

- **`app/page.tsx`** — landing page: question input, RAG toggle, example prompts, recent-run list
  (`GET /api/research`).
- **`app/runs/[id]/page.tsx`** — the live run view. Combines two data sources:
  - `useRunEvents(id)` (`lib/use-run-events.ts`): opens an `EventSource` (native browser SSE
    client) to `/api/research/{id}/events` and reduces the incoming event stream into UI state
    (current stage, sub-question statuses, streaming draft text, verdicts, coverage) via a
    `useReducer` — a clean **event-sourcing** pattern on the frontend mirroring the backend's own
    event-log design.
  - `getRun(id)` (`lib/api.ts`): a one-shot REST fetch of the persisted final result, used once
    the run is finished (or for viewing a historical run) so the page doesn't depend on the SSE
    connection outliving the tab.
- **`components/dag-view.tsx`** — renders the sub-question DAG as an interactive graph (React
  Flow), color-coding each node's status (pending/running/done/failed) as events arrive live.
- **`components/event-timeline.tsx`** — scrolling raw trace feed (skips high-frequency
  `draft_token`/`verdict` events, which have their own dedicated panels).
- **`components/report-view.tsx`** — renders the (possibly still-streaming) Markdown report.
- **`components/audit-panel.tsx`** — the citation audit UI: each sentence with its verdict label
  and the evidence it cites, letting a reader (or examiner) inspect *why* the system trusts or
  distrusts each claim — this is the "novel contribution" of the project made visible, not just a
  hidden backend number.

---

## 10. Key concepts glossary

- **DAG (Directed Acyclic Graph) decomposition**: breaking one big question into smaller
  sub-questions with explicit dependencies, so independent parts can be solved in parallel and
  dependent parts get the right context. Implemented via Pydantic models + Kahn's topological sort.
- **LangGraph `StateGraph`**: a framework for building agent pipelines as an explicit graph of
  nodes over shared, reducer-merged state — as opposed to a single monolithic prompt loop. Gives
  you controllable branching, parallel fan-out (`Send`), and conditional routing as first-class
  primitives instead of ad hoc control flow.
- **`Send()` / fan-out**: LangGraph's mechanism for dynamically dispatching N parallel node
  invocations with different payloads from one conditional edge — used here to run a whole wave
  of independent sub-questions concurrently.
- **Reducer-merged state**: declaring how concurrent partial writes to the same state key should
  be combined (`operator.add`, dict merge) so parallel nodes never need locks or manual merge
  logic.
- **RAG (Retrieval-Augmented Generation)**: grounding LLM output in retrieved documents instead of
  parametric memory alone — reduces (but does not eliminate) hallucination. This project's RAG
  agent is one of three evidence sources feeding the same citation pipeline.
- **BM25**: a classical, embedding-free term-frequency ranking function for keyword search over a
  document corpus. Chosen here for a small, cheap, transparent local-corpus retriever.
- **Structured output / JSON mode**: constraining an LLM's output to conform to a schema (here:
  Pydantic models), with a validate→retry-with-error loop as the reliability backstop.
- **Citation grounding & sentence-level verification**: rather than trusting a model's citations
  at face value, independently re-checking — sentence by sentence, using only the cited evidence
  text — whether each claim is actually supported. This is the project's core novel mechanism.
- **Reflection / self-critique loop**: an agent evaluates its own output against a quality gate
  and, if it fails, revises its plan and retries — bounded by a hard iteration cap and a
  recursion-limit safety net to guarantee termination.
- **Ablation study**: removing one component (here: the critic loop, or the whole multi-agent
  structure) and re-measuring, to isolate that component's actual contribution — the standard
  methodology for justifying "this design choice matters" empirically rather than by assertion.
- **Sign test**: a nonparametric statistical test on paired comparisons, robust to small sample
  sizes and non-normal distributions — appropriate given free-tier LLM quota constraints limiting
  eval scale.
- **Cohen's kappa**: an inter-rater agreement statistic that corrects for chance agreement — used
  here to validate that the automated citation checker's labels are trustworthy compared to human
  judgment, not just self-consistent.
- **Sandboxing (defense in depth)**: layering independent restrictions (import allowlist → OS
  resource limits → network namespace isolation → timeout) so that no single control failing
  leaves the system fully exposed.
- **Event sourcing**: representing system behavior as an append-only, replayable log of typed
  events, which two independent consumers (SQLite persistence, live SSE fan-out) can consume from
  the same source of truth — enables both "replay history on reconnect" and "stream live" from one
  mechanism.
- **SSE (Server-Sent Events)**: a simple one-directional HTTP streaming protocol (vs. WebSockets)
  well-suited to "server continuously pushes progress updates to a browser tab," used here instead
  of a heavier bidirectional protocol since the frontend never needs to push data back mid-run.

---

## 11. Repo map (quick reference)

```
backend/
  app/graph/state.py          shared state schema, DAG validation, citation ID plumbing
  app/graph/builder.py        StateGraph wiring (nodes + edges)
  app/graph/runner.py         single entry point (used by both CLI and API)
  app/graph/prompts.py        every LLM prompt, centralized
  app/graph/nodes/
    planner.py                 question -> DAG plan (+ delta replanning)
    scheduler.py                wave dispatch via Send(), budget/deadlock guards
    specialists.py              web_agent / code_agent / rag_agent
    synthesizer.py               findings+evidence -> cited draft (streamed)
    citation_checker.py          sentence-level audit -> coverage score  [novel #1]
    critic.py                    coverage gate -> replan or finalize     [novel #2]
    finalizer.py                 renumber citations, write report.md/.pdf
    common.py                    shared helpers (summarize_with_citations, etc.)
  app/services/
    llm.py                      model tiering, structured output, retry/fallback
    search.py                   Tavily / DuckDuckGo / mock search providers
    sandbox.py                  layered sandboxing for LLM-generated Python
    rag.py                      BM25 local-corpus retriever
  app/api/                    FastAPI routes + RunManager (background tasks, SSE fan-out)
  app/db/store.py             SQLite persistence (runs + replayable events)
  app/cli.py                  terminal runner with rich live trace
  eval/                       dataset, baseline system, eval runner, metrics/stats
  data/corpus/                demo RAG corpus (markdown files)
frontend/
  app/page.tsx                 landing / new-run page
  app/runs/[id]/page.tsx       live run view (DAG + trace + report + audit)
  lib/use-run-events.ts        SSE consumer -> reducer -> live UI state
  components/                  dag-view, event-timeline, report-view, audit-panel
```

---

## 12. Known limitations

- Web evidence quality bounds achievable coverage — DuckDuckGo snippets are short; only the top 2
  results get full-text extraction; Tavily (paid-tier-friendlier) improves this materially.
- RAG is BM25-only over a small curated corpus — no dense/hybrid retrieval yet (the `Retriever`
  protocol is designed to support it as a drop-in, but it isn't implemented).
- Prose-only report constraint (no tables) exists specifically so the sentence-level auditor can
  see every claim — a real usability/rigor tradeoff, not an oversight.
- Sandbox threat model is "defend against accidental misbehavior," not "defend against a
  determined adversary" — acceptable because only system-generated code ever runs there.
- Single-process, single-user, no auth — in-flight runs are lost if the server restarts (though
  events already emitted persist in SQLite).
