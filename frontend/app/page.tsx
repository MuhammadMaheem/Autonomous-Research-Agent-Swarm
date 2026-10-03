"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listRuns, startResearch } from "@/lib/api";
import { RunSummary } from "@/lib/types";

const EXAMPLES = [
  "How do retrieval-augmented generation systems reduce hallucination in LLMs?",
  "What evaluation frameworks exist for measuring citation quality in LLM-generated text?",
  "A team of 5 researchers each saves 30% of a 40-hour week with AI tools. How many person-hours per year is that?",
];

const AGENTS = [
  { color: "bg-sky-400", name: "Web", desc: "Live search" },
  { color: "bg-amber-400", name: "Scholar", desc: "Academic papers" },
  { color: "bg-emerald-400", name: "Code", desc: "Sandboxed Python" },
  { color: "bg-violet-400", name: "RAG", desc: "Local corpus" },
];

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function Home() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    listRuns().then(setRuns).catch(() => {});
  }, []);

  async function submit() {
    if (question.trim().length < 8 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const runId = await startResearch(question.trim(), useRag);
      router.push(`/runs/${runId}`);
    } catch (e: any) {
      setError(e.message ?? "failed to start run");
      setBusy(false);
    }
  }

  const charCount = question.trim().length;
  const canSubmit = charCount >= 8 && !busy;

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 pb-12 pt-12">
      {/* ── brand bar ── */}
      <div className="fade-up flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-500/15 text-lg ring-1 ring-brand-400/30">
            🐝
          </span>
          <div className="leading-tight">
            <span className="block text-sm font-bold tracking-wide text-zinc-100">
              Research Swarm
            </span>
            <span className="block text-[10px] font-medium uppercase tracking-[0.25em] text-zinc-500">
              multi-agent · langgraph
            </span>
          </div>
        </div>
        <span className="rounded-full border border-zinc-700/60 bg-zinc-900/60 px-3 py-1 font-mono text-[10px] text-zinc-500">
          v0.1
        </span>
      </div>

      {/* ── hero ── */}
      <div className="fade-up d1 mt-20 text-center">
        <h1 className="text-4xl font-extrabold leading-[1.15] tracking-tight sm:text-5xl">
          Research that{" "}
          <span className="word-cycle-wrap text-gradient">
            <span className="word">searches</span>
            <span className="word">codes</span>
            <span className="word">reads papers</span>
            <span className="word">cites its sources</span>
          </span>
          <br />
          or says nothing at all.
        </h1>
        <p className="mx-auto mt-5 max-w-lg text-[15px] leading-relaxed text-zinc-400">
          A planner decomposes your question into a DAG. Specialist agents
          research in parallel. Every sentence is audited against its citations.
        </p>
      </div>

      {/* ── agent legend ── */}
      <div className="fade-up d2 mt-8 flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
        {AGENTS.map((a) => (
          <div key={a.name} className="flex items-center gap-1.5 text-xs text-zinc-400">
            <span className={`h-2 w-2 rounded-full ${a.color}`} />
            <span className="font-medium text-zinc-300">{a.name}</span>
            <span className="text-zinc-600">·</span>
            <span>{a.desc}</span>
          </div>
        ))}
      </div>

      {/* ── question card ── */}
      <div className="fade-up d3 mt-10 border-animated ring-glow p-1 transition-all duration-300">
        <div className="rounded-[calc(1rem-4px)] bg-surface-panel">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit())}
            rows={3}
            placeholder="Ask a research question…"
            className="w-full resize-none rounded-t-xl bg-transparent p-5 pb-3 font-mono text-[14px] text-zinc-100 placeholder-zinc-600 focus:outline-none"
          />
          {/* character progress bar */}
          <div className="mx-5 h-px overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(100, (charCount / 8) * 100)}%`,
                backgroundColor: charCount >= 8 ? "var(--accent-emerald)" : "var(--accent-orange)",
              }}
            />
          </div>
          <div className="flex items-center justify-between gap-3 px-5 pb-4 pt-3">
            {/* segmented rag toggle */}
            <div className="flex overflow-hidden rounded-lg border border-zinc-700/60 text-xs">
              <button
                onClick={() => setUseRag(false)}
                className={`px-3 py-1.5 font-medium transition ${
                  !useRag
                    ? "bg-brand-500/20 text-brand-300"
                    : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                }`}
              >
                🌐 Web only
              </button>
              <button
                onClick={() => setUseRag(true)}
                className={`px-3 py-1.5 font-medium transition ${
                  useRag
                    ? "bg-brand-500/20 text-brand-300"
                    : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                }`}
              >
                🌐 + 📚 RAG
              </button>
            </div>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="btn-primary flex items-center gap-2 px-6 py-2.5 text-sm"
            >
              {busy ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                  </svg>
                  Deploying…
                </>
              ) : (
                <>
                  Research
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </>
              )}
            </button>
          </div>
          {error && (
            <div className="mx-5 mb-4 rounded-lg border border-rose-500/30 bg-rose-500/[0.07] px-4 py-2.5 text-sm text-rose-300">
              {error}
            </div>
          )}
        </div>
      </div>

      {/* ── example prompts ── */}
      <div className="fade-up d4 mt-5 flex flex-wrap justify-center gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => setQuestion(ex)}
            className="group rounded-full border border-zinc-800 bg-zinc-900/40 px-3.5 py-1.5 text-xs text-zinc-500 transition hover:border-brand-400/30 hover:bg-brand-500/10 hover:text-zinc-300"
          >
            <span className="mr-1 text-brand-400/60 transition group-hover:text-brand-400">→</span>
            {ex.length > 72 ? ex.slice(0, 72) + "…" : ex}
          </button>
        ))}
      </div>

      {/* ── run history ── */}
      {runs.length > 0 && (
        <div className="fade-up d5 mt-14">
          <h2 className="mb-3 flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-700 to-transparent" />
            Recent runs
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-zinc-700 to-transparent" />
          </h2>
          <div className="space-y-1.5">
            {runs.slice(0, 5).map((r) => {
              const covPct = r.coverage != null ? Math.round(r.coverage * 100) : null;
              const borderColor =
                covPct == null
                  ? "border-zinc-700"
                  : covPct >= 75
                    ? "border-emerald-500/60"
                    : covPct >= 50
                      ? "border-amber-500/60"
                      : "border-rose-500/60";
              return (
                <button
                  key={r.id}
                  onClick={() => router.push(`/runs/${r.id}`)}
                  className={`group flex w-full items-center gap-4 rounded-lg border-l-2 bg-zinc-900/40 px-4 py-3 text-left transition-all duration-200 hover:-translate-y-px hover:bg-zinc-900/70 hover:shadow-lg ${borderColor}`}
                >
                  {/* status dot */}
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      r.status === "done"
                        ? "bg-emerald-400"
                        : r.status === "failed"
                          ? "bg-rose-400"
                          : "pulse-dot bg-brand-400"
                    }`}
                  />
                  {/* question */}
                  <span className="min-w-0 flex-1 truncate text-sm text-zinc-300 transition group-hover:text-zinc-100">
                    {r.question}
                  </span>
                  {/* meta */}
                  <div className="flex shrink-0 items-center gap-3 text-xs text-zinc-500">
                    {r.iterations != null && (
                      <span className="hidden sm:inline" title="reflection iterations">
                        ×{r.iterations}
                      </span>
                    )}
                    {covPct != null && (
                      <span className="flex items-center gap-1.5">
                        <span className="hidden h-1 w-12 overflow-hidden rounded-full bg-zinc-800 sm:block">
                          <span
                            className={`block h-full rounded-full ${
                              covPct >= 75 ? "bg-emerald-400" : covPct >= 50 ? "bg-amber-400" : "bg-rose-400"
                            }`}
                            style={{ width: `${covPct}%` }}
                          />
                        </span>
                        <span className="tabular-nums">{covPct}%</span>
                      </span>
                    )}
                    <span className="tabular-nums text-zinc-600">{timeAgo(r.created_at)}</span>
                    <span className="text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-brand-400">
                      →
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── footer ── */}
      <div className="mt-auto pt-10 text-center text-[11px] text-zinc-600">
        Powered by LangGraph · OpenAlex · DuckDuckGo
      </div>
    </main>
  );
}
