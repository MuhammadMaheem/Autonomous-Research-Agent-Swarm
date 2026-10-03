"use client";
import { useEffect, useRef } from "react";
import { TraceEvent } from "@/lib/types";

type EventStyle = {
  icon: string;
  text: string;
  major: boolean;
  bar: string;
  dot: string;
  tone: string;
};

function describe(ev: TraceEvent): EventStyle {
  const p = ev.payload;
  switch (ev.event) {
    case "run_started":
      return {
        icon: "🚀",
        text: "Run started",
        major: true,
        bar: "border-brand-500/40 bg-brand-500/[0.06]",
        dot: "bg-brand-400",
        tone: "text-brand-300",
      };
    case "plan_ready":
      return {
        icon: "🗺️",
        text:
          `${p.replan ? "Revised plan" : "Plan ready"}: ${p.plan.sub_questions.length} sub-questions` +
          (p.replan ? ` (iteration ${p.iteration})` : ""),
        major: true,
        bar: "border-violet-500/40 bg-violet-500/[0.06]",
        dot: "bg-violet-400",
        tone: "text-violet-300",
      };
    case "node_started":
      if (p.warning)
        return {
          icon: "⚠️",
          text: p.warning,
          major: false,
          bar: "",
          dot: "bg-amber-400",
          tone: "text-amber-300",
        };
      return {
        icon: "▸",
        text: `${ev.node}${p.sub_question_id ? ` → ${p.sub_question_id}` : ""}`,
        major: false,
        bar: "",
        dot: "bg-zinc-600",
        tone: "text-zinc-500",
      };
    case "node_finished":
      if (p.error)
        return {
          icon: "✖",
          text: `${ev.node} failed${p.sub_question_id ? ` on ${p.sub_question_id}` : ""}: ${p.error}`,
          major: false,
          bar: "",
          dot: "bg-rose-400",
          tone: "text-rose-400",
        };
      return {
        icon: "✓",
        text: `${ev.node}${p.sub_question_id ? ` → ${p.sub_question_id}` : ""}`,
        major: false,
        bar: "",
        dot: "bg-zinc-600",
        tone: "text-zinc-500",
      };
    case "search_results":
      return {
        icon: p.provider === "bm25" || p.provider === "stub" ? "📚" : p.provider === "openalex" ? "🎓" : "🔍",
        text: `${p.sub_question_id} · ${p.provider}: ${p.results
          .map((r: any) => r.title)
          .slice(0, 2)
          .join(" · ")
          .slice(0, 100)}`,
        major: false,
        bar: "",
        dot: "bg-sky-400",
        tone: "text-sky-300",
      };
    case "code_executed":
      return {
        icon: "🧮",
        text: `${p.sub_question_id} · ${String(p.stdout).slice(0, 90)}`,
        major: false,
        bar: "",
        dot: "bg-emerald-400",
        tone: "text-emerald-300",
      };
    case "finding_ready":
      return {
        icon: "📄",
        text: `${p.sub_question_id}: ${String(p.summary).slice(0, 100)}…`,
        major: false,
        bar: "",
        dot: "bg-emerald-300",
        tone: "text-emerald-200",
      };
    case "citation_summary":
      return {
        icon: "🔬",
        text: `Audit: ${Math.round(p.coverage * 100)}% supported (${JSON.stringify(p.labels)})`,
        major: true,
        bar: "border-teal-500/40 bg-teal-500/[0.06]",
        dot: "bg-teal-400",
        tone: "text-teal-300",
      };
    case "route_decision":
      return {
        icon: "⇢",
        text: `${ev.node}: ${p.route}${p.reason ? ` — ${p.reason}` : ""}`,
        major: false,
        bar: "",
        dot: "bg-amber-300",
        tone: "text-amber-200",
      };
    case "run_finished":
      return {
        icon: "🏁",
        text: `Done — ${p.coverage != null ? Math.round(p.coverage * 100) + "% cited" : ""}, ${p.iterations} iteration(s), ${p.token_usage} tokens, ${p.elapsed_s}s`,
        major: true,
        bar: "border-emerald-500/40 bg-emerald-500/[0.06]",
        dot: "bg-emerald-400",
        tone: "text-emerald-300",
      };
    case "run_failed":
      return {
        icon: "💥",
        text: `Run failed: ${p.error}`,
        major: true,
        bar: "border-rose-500/40 bg-rose-500/[0.06]",
        dot: "bg-rose-400",
        tone: "text-rose-400",
      };
    default:
      return {
        icon: "·",
        text: `${ev.node}.${ev.event}`,
        major: false,
        bar: "",
        dot: "bg-zinc-700",
        tone: "text-zinc-600",
      };
  }
}

function timeStr(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour12: false });
}

export function EventTimeline({ events }: { events: TraceEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [events.length]);

  return (
    <div className="h-full overflow-y-auto pr-1 text-[11px] leading-relaxed">
      <div className="space-y-0.5">
        {events.map((ev, i) => {
          const d = describe(ev);
          if (d.major) {
            return (
              <div
                key={ev.seq}
                className={`slide-in flex items-center gap-2.5 rounded-lg border-l-2 px-3 py-2 ${d.bar}`}
                style={{ animationDelay: `${Math.min(i * 20, 200)}ms` }}
              >
                <span className="shrink-0 text-sm">{d.icon}</span>
                <span className={`flex-1 font-medium ${d.tone}`}>{d.text}</span>
                <span className="shrink-0 font-mono text-zinc-600 tabular-nums">{timeStr(ev.ts)}</span>
              </div>
            );
          }
          return (
            <div
              key={ev.seq}
              className="slide-in flex items-center gap-2 rounded px-2.5 py-1 transition hover:bg-white/[0.02]"
              style={{ animationDelay: `${Math.min(i * 15, 150)}ms` }}
            >
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${d.dot}`} />
              <span className="w-12 shrink-0 font-mono text-zinc-600 tabular-nums">
                {timeStr(ev.ts)}
              </span>
              <span className="shrink-0 text-[10px]">{d.icon}</span>
              <span className={`truncate ${d.tone}`}>{d.text}</span>
            </div>
          );
        })}
        {events.length === 0 && (
          <div className="flex items-center gap-2 py-3 text-zinc-600">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-zinc-600" />
            listening for agent activity…
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
