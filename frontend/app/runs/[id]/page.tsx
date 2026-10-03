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
  ["synthesizer", "Synthesize", "✍️"],
  ["citation_checker", "Audit", "🔬"],
  ["critic", "Critic", "♻️"],
  ["finalizer", "Finalize", "🏁"],
] as const;

const STAGE_ALIAS: Record<string, string> = {
  web_agent: "scheduler",
  code_agent: "scheduler",
  rag_agent: "scheduler",
  scholar_agent: "scheduler",
  runner: "planner",
};

/** SVG circular progress ring */
function CoverageRing({ pct, size = 40 }: { pct: number; size?: number }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const color = pct >= 75 ? "#34d399" : pct >= 50 ? "#fbbf24" : "#fb7185";

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth="3" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        className="ring-fill-anim transition-all duration-700"
        style={{ ["--circ" as string]: circ }}
      />
      <text
        x={size / 2}
        y={size / 2}
        textAnchor="middle"
        dominantBaseline="central"
        className="rotate-90 fill-zinc-200 text-[10px] font-bold tabular-nums"
        style={{ transformOrigin: "center" }}
      >
        {pct}%
      </text>
    </svg>
  );
}

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

  const covPct = coverage != null ? Math.round(coverage * 100) : null;

  return (
    <div className="flex min-h-screen flex-col">
      {/* ── sticky header ── */}
      <header className="fade-up sticky top-0 z-30 border-b border-zinc-800/60 bg-surface-deep/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-3">
          <Link
            href="/"
            className="group flex items-center gap-1.5 text-xs text-zinc-500 transition hover:text-brand-300"
          >
            <span className="transition group-hover:-translate-x-0.5">←</span>
            <span className="hidden sm:inline">new question</span>
          </Link>
          <h1
            className="min-w-0 flex-1 truncate text-sm font-semibold text-zinc-200"
            title={run?.question}
          >
            {run?.question ?? "…"}
          </h1>
          <div className="flex items-center gap-2">
            {covPct != null && <CoverageRing pct={covPct} />}
            <span
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${
                live.failed
                  ? "bg-rose-500/10 text-rose-300 ring-rose-500/30"
                  : live.finished
                    ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"
                    : "bg-brand-500/10 text-brand-300 ring-brand-500/30"
              }`}
            >
              {!live.failed && !live.finished && (
                <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-brand-400" />
              )}
              {live.failed ? "failed" : live.finished ? "done" : live.connected ? "running" : "connecting"}
            </span>
            {live.finished && !live.failed && (
              <>
                <a
                  href={`${API_URL}/api/research/${id}/report.md`}
                  target="_blank"
                  className="hidden rounded-full border border-zinc-700/60 bg-zinc-900/60 px-2.5 py-1 text-[11px] text-zinc-400 transition hover:border-brand-400/40 hover:text-brand-300 sm:inline"
                >
                  ↓ .md
                </a>
                <a
                  href={`${API_URL}/api/research/${id}/report.pdf`}
                  target="_blank"
                  className="hidden rounded-full border border-zinc-700/60 bg-zinc-900/60 px-2.5 py-1 text-[11px] text-zinc-400 transition hover:border-brand-400/40 hover:text-brand-300 sm:inline"
                >
                  ↓ .pdf
                </a>
              </>
            )}
          </div>
        </div>
      </header>

      {live.failed && (
        <div className="mx-auto w-full max-w-7xl px-6 pt-3">
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/[0.06] px-4 py-3 text-sm text-rose-300">
            💥 {live.failed}
          </div>
        </div>
      )}

      {/* ── dashboard grid ── */}
      <div className="fade-up d1 mx-auto w-full max-w-7xl flex-1 px-6 py-4">
        <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
          {/* ── left column: pipeline + DAG + trace ── */}
          <div className="flex flex-col gap-3 lg:max-h-[calc(100vh-88px)] lg:overflow-hidden">
            {/* vertical pipeline */}
            <div className="panel-solid px-4 py-3">
              <div className="flex items-center gap-1.5">
                {STAGES.map(([key, label, icon], i) => {
                  const active = i === stageIdx && !live.finished;
                  const done = i < stageIdx || live.finished;
                  return (
                    <div key={key} className="flex items-center gap-0.5">
                      {i > 0 && (
                        <div
                          className={`h-px w-3 sm:w-4 ${
                            done
                              ? "bg-gradient-to-r from-brand-400/50 to-teal-400/50"
                              : "bg-zinc-800"
                          }`}
                        />
                      )}
                      <span
                        className={`relative flex items-center gap-1 overflow-hidden rounded-full px-2 py-1 text-[10px] font-medium transition-colors ${
                          active
                            ? "bg-brand-500/20 text-brand-200 ring-1 ring-brand-400/40 glow-pulse"
                            : done
                              ? "bg-white/[0.04] text-zinc-400 ring-1 ring-zinc-700/50"
                              : "text-zinc-600"
                        }`}
                      >
                        {active && <span className="shimmer absolute inset-0" />}
                        <span className="relative">{done && !active ? "✓" : icon}</span>
                        <span className="relative hidden sm:inline">
                          {label}
                          {live.iteration > 0 && key === "planner" && ` ×${live.iteration + 1}`}
                        </span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* DAG */}
            <div className="panel-solid overflow-hidden" style={{ height: 280 }}>
              <header className="flex items-center gap-2 border-b border-zinc-800/50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                <span className="text-xs">🕸️</span> Sub-question DAG
              </header>
              <div style={{ height: 248 }}>
                <DagView plan={plan} sqStatus={sqStatus} />
              </div>
            </div>

            {/* live trace */}
            <div className="panel-solid flex-1 overflow-hidden lg:flex-1">
              <header className="flex items-center gap-2 border-b border-zinc-800/50 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                <span className="text-xs">📡</span> Live trace
                {!live.finished && !live.failed && (
                  <span className="pulse-dot ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400" />
                )}
                <span className="ml-auto text-zinc-600 font-mono">{live.events.length}</span>
              </header>
              <div className="h-[calc(100%-32px)] overflow-y-auto p-2.5">
                <EventTimeline events={live.events} />
              </div>
            </div>
          </div>

          {/* ── right column: report / audit ── */}
          <div className="panel-solid flex flex-col overflow-hidden lg:max-h-[calc(100vh-88px)]">
            {/* tabs */}
            <div className="flex items-center gap-0.5 border-b border-zinc-800/50 px-2 py-1.5">
              <button
                onClick={() => setTab("report")}
                className={`relative rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  tab === "report"
                    ? "text-brand-200"
                    : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300"
                }`}
              >
                📄 Report
                {!live.finished && live.draft && (
                  <span className="ml-1.5 animate-pulse text-brand-400">●</span>
                )}
                {tab === "report" && (
                  <span className="absolute bottom-0 left-2 right-2 h-px bg-gradient-to-r from-brand-400 to-teal-400" />
                )}
              </button>
              <button
                onClick={() => setTab("audit")}
                className={`relative rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  tab === "audit"
                    ? "text-brand-200"
                    : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300"
                }`}
              >
                🔬 Audit
                {verdicts.length > 0 && (
                  <span className="ml-1 text-xs text-zinc-500">({verdicts.length})</span>
                )}
                {tab === "audit" && (
                  <span className="absolute bottom-0 left-2 right-2 h-px bg-gradient-to-r from-brand-400 to-teal-400" />
                )}
              </button>
            </div>

            {/* tab content */}
            <div className="flex-1 overflow-y-auto">
              {tab === "report" ? (
                <ReportView markdown={reportMd} streaming={!live.finished && !!live.draft} />
              ) : (
                <AuditPanel verdicts={verdicts} evidence={evidence} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
