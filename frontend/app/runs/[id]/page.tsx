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
  ["planner", "Planner"],
  ["scheduler", "Swarm"],
  ["synthesizer", "Synthesizer"],
  ["citation_checker", "Citation audit"],
  ["critic", "Critic"],
  ["finalizer", "Final report"],
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300">← new question</Link>
          <h1 className="mt-1 truncate text-xl font-semibold text-zinc-100" title={run?.question}>
            {run?.question ?? "…"}
          </h1>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {coverage != null && (
            <span className={`rounded-full px-3 py-1.5 font-semibold ${
              coverage >= 0.75 ? "bg-emerald-950 text-emerald-300" :
              coverage >= 0.5 ? "bg-amber-950 text-amber-300" : "bg-rose-950 text-rose-300"}`}>
              {Math.round(coverage * 100)}% cited
            </span>
          )}
          <span className={`rounded-full px-3 py-1.5 ${
            live.failed ? "bg-rose-950 text-rose-300" :
            live.finished ? "bg-emerald-950 text-emerald-300" : "bg-indigo-950 text-indigo-300"}`}>
            {live.failed ? "failed" : live.finished ? "done" : live.connected ? "running" : "connecting"}
          </span>
          {live.finished && !live.failed && (
            <>
              <a href={`${API_URL}/api/research/${id}/report.md`} target="_blank"
                 className="rounded-full border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:border-indigo-500">.md</a>
              <a href={`${API_URL}/api/research/${id}/report.pdf`} target="_blank"
                 className="rounded-full border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:border-indigo-500">.pdf</a>
            </>
          )}
        </div>
      </div>

      <div className="mt-5 flex items-center gap-1 text-[11px]">
        {STAGES.map(([key, label], i) => (
          <div key={key} className="flex items-center gap-1">
            {i > 0 && <div className="h-px w-6 bg-zinc-800" />}
            <span className={`rounded-full px-2.5 py-1 ${
              i === stageIdx && !live.finished ? "bg-indigo-600 text-white" :
              i < stageIdx || live.finished ? "bg-zinc-800 text-zinc-300" : "bg-zinc-900 text-zinc-600"}`}>
              {label}{live.iteration > 0 && key === "planner" && ` ×${live.iteration + 1}`}
            </span>
          </div>
        ))}
      </div>

      {live.failed && (
        <div className="mt-4 rounded-lg border border-rose-900 bg-rose-950/40 p-4 text-sm text-rose-200">
          {live.failed}
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="h-[380px] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
          <header className="border-b border-zinc-800 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Sub-question DAG
          </header>
          <div className="h-[340px]">
            <DagView plan={plan} sqStatus={sqStatus} />
          </div>
        </section>
        <section className="h-[380px] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
          <header className="border-b border-zinc-800 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Live agent trace
          </header>
          <div className="h-[340px] p-3">
            <EventTimeline events={live.events} />
          </div>
        </section>
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
        <div className="flex border-b border-zinc-800 text-sm">
          <button onClick={() => setTab("report")}
                  className={`px-5 py-2.5 ${tab === "report" ? "border-b-2 border-indigo-500 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
            Report {!live.finished && live.draft && <span className="ml-1 animate-pulse text-indigo-400">●</span>}
          </button>
          <button onClick={() => setTab("audit")}
                  className={`px-5 py-2.5 ${tab === "audit" ? "border-b-2 border-indigo-500 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
            Citation audit {verdicts.length > 0 && <span className="ml-1 text-xs text-zinc-500">({verdicts.length})</span>}
          </button>
        </div>
        {tab === "report"
          ? <ReportView markdown={reportMd} streaming={!live.finished && !!live.draft} />
          : <AuditPanel verdicts={verdicts} evidence={evidence} />}
      </div>
    </main>
  );
}
