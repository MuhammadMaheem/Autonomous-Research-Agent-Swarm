"use client";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { AuditPanel } from "@/components/audit-panel";
import { DagView } from "@/components/dag-view";
import { EventTimeline } from "@/components/event-timeline";
import { ReportView } from "@/components/report-view";
import { getRun } from "@/lib/api";
import { useRunEvents } from "@/lib/use-run-events";
import { API_URL, RunDetail } from "@/lib/types";

const STAGES = [
  ["planner", "Planner", "🗺️"],
  ["scheduler", "Swarm", "🐝"],
  ["synthesizer", "Synthesizer", "✍️"],
  ["citation_checker", "Citation audit", "🔬"],
  ["critic", "Critic", "♻️"],
  ["finalizer", "Final report", "🏁"],
] as const;

const STAGE_ALIAS: Record<string, string> = {
  web_agent: "scheduler", code_agent: "scheduler", rag_agent: "scheduler", runner: "planner",
};

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const live = useRunEvents(id);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [tab, setTab] = useState<"report" | "audit">("report");

  useEffect(() => {
    getRun(id).then(setRun).catch(() => {});
  }, [id, live.finished]);

  const stageKey = STAGE_ALIAS[live.stage] ?? live.stage;
  const stageIdx = STAGES.findIndex(([k]) => k === stageKey);

  const verdicts = live.finished && run?.result?.verdicts?.length ? run.result.verdicts : live.verdicts;
  const evidence = run?.result?.evidence ?? {};
  const reportMd = live.finished && run?.report_md ? run.report_md : live.draft;
  const coverage = run?.coverage ?? live.coverage;

  const plan = live.plan ?? run?.result?.plan ?? null;
  const sqStatus = useMemo(() => {
    if (!live.finished || live.plan) return live.sqStatus;
    const done: Record<string, "done"> = {};
    for (const sq of plan?.sub_questions ?? []) done[sq.id] = "done";
    return done;
  }, [live.finished, live.plan, live.sqStatus, plan]);

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      {/* header */}
      <div className="fade-up flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/"
                className="group inline-flex items-center gap-1.5 text-xs text-zinc-500 transition hover:text-indigo-300">
            <span className="transition group-hover:-translate-x-0.5">←</span> new question
          </Link>
          <h1 className="mt-1.5 truncate text-xl font-semibold tracking-tight text-zinc-100" title={run?.question}>
            {run?.question ?? "…"}
          </h1>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {coverage != null && (
            <span className={`rounded-full px-3 py-1.5 font-semibold ring-1 ${
              coverage >= 0.75 ? "bg-emerald-500/10 text-emerald-300 ring-emerald-400/30" :
              coverage >= 0.5 ? "bg-amber-500/10 text-amber-300 ring-amber-400/30" :
              "bg-rose-500/10 text-rose-300 ring-rose-400/30"}`}>
              {Math.round(coverage * 100)}% cited
            </span>
          )}
          <span className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 font-medium ring-1 ${
            live.failed ? "bg-rose-500/10 text-rose-300 ring-rose-400/30" :
            live.finished ? "bg-emerald-500/10 text-emerald-300 ring-emerald-400/30" :
            "bg-indigo-500/10 text-indigo-300 ring-indigo-400/30"}`}>
            {!live.failed && !live.finished && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-indigo-400" />}
            {live.failed ? "failed" : live.finished ? "done" : live.connected ? "running" : "connecting"}
          </span>
          {live.finished && !live.failed && (
            <>
              <a href={`${API_URL}/api/research/${id}/report.md`} target="_blank"
                 className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-zinc-300 transition hover:border-indigo-400/50 hover:bg-indigo-500/10 hover:text-indigo-200">↓ .md</a>
              <a href={`${API_URL}/api/research/${id}/report.pdf`} target="_blank"
                 className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-zinc-300 transition hover:border-indigo-400/50 hover:bg-indigo-500/10 hover:text-indigo-200">↓ .pdf</a>
            </>
          )}
        </div>
      </div>

      {/* stage pipeline */}
      <div className="glass fade-up d1 mt-5 flex flex-wrap items-center gap-1 px-4 py-3 text-[11px]">
        {STAGES.map(([key, label, icon], i) => {
          const active = i === stageIdx && !live.finished;
          const done = i < stageIdx || live.finished;
          return (
            <div key={key} className="flex items-center gap-1">
              {i > 0 && (
                <div className={`h-px w-5 sm:w-7 ${done ? "bg-gradient-to-r from-indigo-400/60 to-fuchsia-400/60" : "bg-zinc-800"}`} />
              )}
              <span className={`relative flex items-center gap-1.5 overflow-hidden rounded-full px-2.5 py-1.5 font-medium transition-colors ${
                active ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-[0_0_16px_rgba(129,140,248,0.45)]" :
                done ? "bg-white/[0.05] text-zinc-300 ring-1 ring-white/10" :
                "bg-transparent text-zinc-600"}`}>
                {active && <span className="shimmer absolute inset-0" />}
                <span className="relative">{done && !active ? "✓" : icon}</span>
                <span className="relative">
                  {label}{live.iteration > 0 && key === "planner" && ` ×${live.iteration + 1}`}
                </span>
              </span>
            </div>
          );
        })}
      </div>

      {live.failed && (
        <div className="fade-up mt-4 rounded-xl border border-rose-500/30 bg-rose-500/[0.07] p-4 text-sm text-rose-200 backdrop-blur-sm">
          💥 {live.failed}
        </div>
      )}

      {/* DAG + live trace */}
      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="glass fade-up d2 h-[380px] overflow-hidden">
          <header className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span className="text-sm">🕸️</span> Sub-question DAG
          </header>
          <div className="h-[338px]">
            <DagView plan={plan} sqStatus={sqStatus} />
          </div>
        </section>
        <section className="glass fade-up d3 h-[380px] overflow-hidden">
          <header className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <span className="text-sm">📡</span> Live agent trace
            {!live.finished && !live.failed && <span className="pulse-dot ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400" />}
          </header>
          <div className="h-[338px] p-3">
            <EventTimeline events={live.events} />
          </div>
        </section>
      </div>

      {/* report / audit */}
      <div className="glass fade-up d4 mt-4 overflow-hidden">
        <div className="flex items-center gap-1 border-b border-white/[0.06] px-3 py-2 text-sm">
          <button onClick={() => setTab("report")}
                  className={`rounded-lg px-4 py-1.5 font-medium transition ${
                    tab === "report"
                      ? "bg-gradient-to-r from-indigo-500/25 to-violet-500/25 text-indigo-200 ring-1 ring-indigo-400/30"
                      : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300"}`}>
            📄 Report {!live.finished && live.draft && <span className="ml-1 animate-pulse text-indigo-400">●</span>}
          </button>
          <button onClick={() => setTab("audit")}
                  className={`rounded-lg px-4 py-1.5 font-medium transition ${
                    tab === "audit"
                      ? "bg-gradient-to-r from-indigo-500/25 to-violet-500/25 text-indigo-200 ring-1 ring-indigo-400/30"
                      : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300"}`}>
            🔬 Citation audit {verdicts.length > 0 && <span className="ml-1 text-xs text-zinc-500">({verdicts.length})</span>}
          </button>
        </div>
        {tab === "report"
          ? <ReportView markdown={reportMd} streaming={!live.finished && !!live.draft} />
          : <AuditPanel verdicts={verdicts} evidence={evidence} />}
      </div>
    </main>
  );
}
