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
    <main className="mx-auto max-w-3xl px-6 py-16">
      <div className="text-center">
        <div className="text-5xl mb-4">🐝</div>
        <h1 className="text-3xl font-bold tracking-tight">Autonomous Research Agent Swarm</h1>
        <p className="mt-3 text-zinc-400">
          A planner decomposes your question into a DAG of sub-questions. Specialist agents
          research them in parallel. Every sentence of the report is audited against its citations.
        </p>
      </div>

      <div className="mt-10 rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit())}
          rows={3}
          placeholder="Ask a research question…"
          className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 p-4 text-zinc-100 placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
        />
        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)}
                   className="accent-indigo-500" />
            allow local-corpus RAG agent
          </label>
          <button
            onClick={submit}
            disabled={busy || question.trim().length < 8}
            className="rounded-lg bg-indigo-600 px-6 py-2 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          >
            {busy ? "Launching swarm…" : "Research"}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => setQuestion(ex)}
                  className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400 transition hover:border-indigo-600 hover:text-zinc-200">
            {ex.length > 72 ? ex.slice(0, 72) + "…" : ex}
          </button>
        ))}
      </div>

      {runs.length > 0 && (
        <div className="mt-12">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500">Recent runs</h2>
          <div className="divide-y divide-zinc-800 overflow-hidden rounded-xl border border-zinc-800">
            {runs.slice(0, 8).map((r) => (
              <button key={r.id} onClick={() => router.push(`/runs/${r.id}`)}
                      className="flex w-full items-center justify-between gap-4 bg-zinc-900/40 px-4 py-3 text-left transition hover:bg-zinc-900">
                <span className="truncate text-sm text-zinc-300">{r.question}</span>
                <span className="flex shrink-0 items-center gap-3 text-xs">
                  {r.coverage != null && (
                    <span className="text-zinc-400">{Math.round(r.coverage * 100)}% cited</span>
                  )}
                  <span className={
                    r.status === "done" ? "text-emerald-400" :
                    r.status === "failed" ? "text-rose-400" : "text-indigo-400"
                  }>{r.status}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
