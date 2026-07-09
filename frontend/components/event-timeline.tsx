"use client";
import { useEffect, useRef } from "react";
import { TraceEvent } from "@/lib/types";

function describe(ev: TraceEvent): { icon: string; text: string; tone: string; dot: string } {
  const p = ev.payload;
  switch (ev.event) {
    case "run_started":
      return { icon: "🚀", text: "run started", tone: "text-indigo-300", dot: "bg-indigo-400" };
    case "plan_ready":
      return {
        icon: "🗺️",
        text: `${p.replan ? "revised plan" : "plan"}: ${p.plan.sub_questions.length} sub-questions` +
              (p.replan ? ` (iteration ${p.iteration})` : ""),
        tone: "text-fuchsia-300",
        dot: "bg-fuchsia-400",
      };
    case "node_started":
      if (p.warning) return { icon: "⚠️", text: p.warning, tone: "text-amber-300", dot: "bg-amber-400" };
      return { icon: "▸", text: `${ev.node} started${p.sub_question_id ? ` on ${p.sub_question_id}` : ""}`, tone: "text-zinc-500", dot: "bg-zinc-600" };
    case "node_finished":
      if (p.error) return { icon: "✖", text: `${ev.node} failed on ${p.sub_question_id}: ${p.error}`, tone: "text-rose-400", dot: "bg-rose-400" };
      return { icon: "✓", text: `${ev.node} finished${p.sub_question_id ? ` (${p.sub_question_id})` : ""}`, tone: "text-zinc-500", dot: "bg-zinc-600" };
    case "search_results":
      return {
        icon: p.provider === "bm25" || p.provider === "stub" ? "📚" : "🔍",
        text: `${p.sub_question_id} · ${p.provider}: ${p.results.map((r: any) => r.title).slice(0, 3).join(" · ").slice(0, 110)}`,
        tone: "text-sky-300",
        dot: "bg-sky-400",
      };
    case "code_executed":
      return { icon: "🧮", text: `${p.sub_question_id} · sandbox output: ${String(p.stdout).slice(0, 100)}`, tone: "text-emerald-300", dot: "bg-emerald-400" };
    case "finding_ready":
      return { icon: "📄", text: `${p.sub_question_id} answered: ${String(p.summary).slice(0, 110)}…`, tone: "text-emerald-200", dot: "bg-emerald-300" };
    case "citation_summary":
      return {
        icon: "🔬",
        text: `citation audit: ${Math.round(p.coverage * 100)}% supported (${JSON.stringify(p.labels)})`,
        tone: "text-blue-300",
        dot: "bg-blue-400",
      };
    case "route_decision":
      return { icon: "⇢", text: `${ev.node}: ${p.route}${p.reason ? ` — ${p.reason}` : ""}`, tone: "text-amber-200", dot: "bg-amber-300" };
    case "run_finished":
      return { icon: "🏁", text: `done — coverage ${p.coverage != null ? Math.round(p.coverage * 100) + "%" : "n/a"}, ${p.iterations} reflection iteration(s), ${p.token_usage} tokens, ${p.elapsed_s}s`, tone: "text-indigo-300", dot: "bg-indigo-400" };
    case "run_failed":
      return { icon: "💥", text: `run failed: ${p.error}`, tone: "text-rose-400", dot: "bg-rose-400" };
    default:
      return { icon: "·", text: `${ev.node}.${ev.event}`, tone: "text-zinc-600", dot: "bg-zinc-700" };
  }
}

export function EventTimeline({ events }: { events: TraceEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [events.length]);

  return (
    <div className="h-full overflow-y-auto pr-1 font-mono text-[11px] leading-relaxed">
      <div className="relative ml-1.5 space-y-1 border-l border-white/[0.07] pl-3">
        {events.map((ev) => {
          const d = describe(ev);
          return (
            <div key={ev.seq} className="relative flex gap-2 rounded px-1 py-0.5 transition hover:bg-white/[0.03]">
              <span className={`absolute -left-[17.5px] top-[7px] h-1.5 w-1.5 rounded-full ${d.dot}`} />
              <span className="w-14 shrink-0 tabular-nums text-zinc-600">
                {new Date(ev.ts).toLocaleTimeString([], { hour12: false })}
              </span>
              <span className="shrink-0">{d.icon}</span>
              <span className={d.tone}>{d.text}</span>
            </div>
          );
        })}
        {events.length === 0 && <div className="py-1 text-zinc-600">waiting for events…</div>}
        <div ref={endRef} />
      </div>
    </div>
  );
}
