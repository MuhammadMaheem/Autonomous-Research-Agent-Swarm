"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listRuns, startResearch } from "@/lib/api";
import { RunSummary } from "@/lib/types";

const EXAMPLES = [
  "How do retrieval-augmented generation systems reduce hallucination in LLMs?",
  "What evaluation frameworks exist for measuring citation quality in LLM-generated text?",
  "A team of 5 researchers each saves 30% of a 40-hour week with AI tools. How many person-hours per year is that, and how does it compare to reported productivity gains?",
];

const AGENTS = [
  { icon: "🗺️", name: "Planner", desc: "DAG of sub-questions" },
  { icon: "🌐", name: "Web", desc: "live search" },
  { icon: "🧮", name: "Code", desc: "sandboxed Python" },
  { icon: "📚", name: "RAG", desc: "local corpus" },
  { icon: "🔬", name: "Auditor", desc: "per-sentence citations" },
  { icon: "♻️", name: "Critic", desc: "reflection loop" },
];

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

  return (
    <main className="mx-auto max-w-3xl px-6 pb-24 pt-14">
      {/* brand bar */}
      <div className="fade-up flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500/30 to-fuchsia-500/20 text-lg shadow-[0_0_18px_rgba(129,140,248,0.25)] ring-1 ring-white/10">
            🐝
          </span>
          <span className="text-sm font-semibold tracking-wide text-zinc-200">
            Research Agent <span className="text-gradient">Swarm</span>
          </span>
        </div>
        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[10px] font-medium uppercase tracking-widest text-zinc-500">
          LangGraph · multi-agent
        </span>
      </div>

      {/* hero */}
      <div className="fade-up d1 mt-16 text-center">
        <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
          Research that <span className="text-gradient">cites its sources</span>
          <br />
          or says nothing at all.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-zinc-400">
          A planner decomposes your question into a DAG of sub-questions. Specialist agents
          research them in parallel. Every sentence of the report is audited against its citations.
        </p>
      </div>

      {/* agent capability chips */}
      <div className="fade-up d2 mt-8 flex flex-wrap items-center justify-center gap-2">
        {AGENTS.map((a) => (
          <span key={a.name}
                className="group flex items-center gap-1.5 rounded-full border border-white/[0.07] bg-white/[0.03] px-3 py-1.5 text-xs text-zinc-400 transition hover:border-indigo-400/40 hover:bg-indigo-500/10 hover:text-zinc-200">
            <span>{a.icon}</span>
            <span className="font-medium text-zinc-300">{a.name}</span>
            <span className="hidden text-zinc-500 sm:inline">· {a.desc}</span>
          </span>
        ))}
      </div>

      {/* question card */}
      <div className="glass ring-glow fade-up d3 mt-10 p-1.5 transition-all duration-300">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit())}
          rows={3}
          placeholder="Ask a research question…"
          className="w-full resize-none rounded-xl bg-transparent p-4 text-[15px] text-zinc-100 placeholder-zinc-500 focus:outline-none"
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5 pt-1">
          <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-zinc-400">
            <span className="relative inline-flex">
              <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)}
                     className="peer sr-only" />
              <span className="h-5 w-9 rounded-full bg-zinc-700/80 transition peer-checked:bg-indigo-500/80" />
              <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-zinc-300 shadow transition peer-checked:translate-x-4 peer-checked:bg-white" />
            </span>
            local-corpus RAG agent
          </label>
          <button
            onClick={submit}
            disabled={busy || question.trim().length < 8}
            className="btn-gradient rounded-xl px-7 py-2.5 text-sm font-semibold text-white disabled:opacity-40 disabled:shadow-none"
          >
            {busy ? "Launching swarm…" : "Research ⚡"}
          </button>
        </div>
        {error && <p className="px-4 pb-3 text-sm text-rose-400">{error}</p>}
      </div>

      {/* example prompts */}
      <div className="fade-up d4 mt-6 flex flex-wrap justify-center gap-2">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => setQuestion(ex)}
                  className="rounded-full border border-white/[0.07] bg-white/[0.02] px-3.5 py-1.5 text-xs text-zinc-500 transition hover:border-fuchsia-400/40 hover:bg-fuchsia-500/10 hover:text-zinc-200">
            ✦ {ex.length > 72 ? ex.slice(0, 72) + "…" : ex}
          </button>
        ))}
      </div>

      {/* run history */}
      {runs.length > 0 && (
        <div className="fade-up d5 mt-16">
          <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
            <span className="h-px w-6 bg-gradient-to-r from-transparent to-zinc-600" />
            Recent runs
            <span className="h-px flex-1 bg-gradient-to-r from-zinc-600 to-transparent" />
          </h2>
          <div className="space-y-2">
            {runs.slice(0, 8).map((r) => (
              <button key={r.id} onClick={() => router.push(`/runs/${r.id}`)}
                      className="group glass flex w-full items-center gap-4 px-4 py-3.5 text-left transition duration-200 hover:-translate-y-0.5 hover:border-indigo-400/30 hover:shadow-[0_8px_40px_rgba(99,102,241,0.12)]">
                <span className={`h-2 w-2 shrink-0 rounded-full ${
                  r.status === "done" ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" :
                  r.status === "failed" ? "bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.8)]" :
                  "pulse-dot bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]"}`} />
                <span className="min-w-0 flex-1 truncate text-sm text-zinc-300 transition group-hover:text-zinc-100">
                  {r.question}
                </span>
                {r.coverage != null && (
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800 sm:block">
                      <span className={`block h-full rounded-full ${
                        r.coverage >= 0.75 ? "bg-emerald-400" : r.coverage >= 0.5 ? "bg-amber-400" : "bg-rose-400"}`}
                            style={{ width: `${Math.round(r.coverage * 100)}%` }} />
                    </span>
                    <span className="text-xs tabular-nums text-zinc-400">{Math.round(r.coverage * 100)}% cited</span>
                  </span>
                )}
                <span className="shrink-0 text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-indigo-300">→</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
