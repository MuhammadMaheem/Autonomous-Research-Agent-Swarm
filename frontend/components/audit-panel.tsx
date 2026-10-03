"use client";
import { useMemo, useState } from "react";
import { EvidenceInfo, Verdict, VerdictLabel } from "@/lib/types";

const LABEL_META: Record<VerdictLabel, { badge: string; bar: string; name: string; border: string }> = {
  supported: {
    badge: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/30",
    bar: "bg-emerald-400",
    name: "supported",
    border: "border-emerald-500/40",
  },
  partially_supported: {
    badge: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/30",
    bar: "bg-amber-400",
    name: "partial",
    border: "border-amber-500/40",
  },
  unsupported: {
    badge: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/30",
    bar: "bg-rose-400",
    name: "unsupported",
    border: "border-rose-500/40",
  },
  no_claim: {
    badge: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
    bar: "bg-zinc-500",
    name: "no claim",
    border: "border-zinc-600/40",
  },
};

const LABEL_ORDER: VerdictLabel[] = ["supported", "partially_supported", "unsupported", "no_claim"];

export function AuditPanel({
  verdicts,
  evidence,
}: {
  verdicts: Verdict[];
  evidence: Record<string, EvidenceInfo>;
}) {
  const [filter, setFilter] = useState<VerdictLabel | "all">("all");

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const v of verdicts) c[v.label] = (c[v.label] ?? 0) + 1;
    return c;
  }, [verdicts]);

  const filtered = filter === "all" ? verdicts : verdicts.filter((v) => v.label === filter);

  if (verdicts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 p-14 text-sm text-zinc-500">
        <div className="relative">
          <span className="text-3xl opacity-40">🔬</span>
          <span className="pulse-dot absolute -right-1 -top-1 h-2 w-2 rounded-full bg-teal-400" />
        </div>
        no citation audit yet — the checker has not run
      </div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      {/* filter chips + distribution bar */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setFilter("all")}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              filter === "all"
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
            }`}
          >
            all ({verdicts.length})
          </button>
          {LABEL_ORDER.map((l) => {
            const n = counts[l] ?? 0;
            if (n === 0) return null;
            return (
              <button
                key={l}
                onClick={() => setFilter(filter === l ? "all" : l)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                  filter === l ? LABEL_META[l].badge : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                }`}
              >
                {LABEL_META[l].name} ({n})
              </button>
            );
          })}
        </div>
        {/* stacked distribution bar */}
        <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-zinc-800/80">
          {LABEL_ORDER.map((l) => {
            const n = counts[l] ?? 0;
            if (n === 0) return null;
            return (
              <span
                key={l}
                className={`h-full transition-all duration-500 ${LABEL_META[l].bar}`}
                style={{ width: `${(n / verdicts.length) * 100}%` }}
              />
            );
          })}
        </div>
      </div>

      {/* verdict cards */}
      <div className="space-y-2">
        {filtered.map((v, i) => (
          <div
            key={v.index}
            className={`slide-in rounded-lg border-l-2 bg-white/[0.02] p-3.5 text-sm transition hover:bg-white/[0.04] ${LABEL_META[v.label].border}`}
            style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
          >
            <div className="flex items-start justify-between gap-3">
              <p className="leading-relaxed text-zinc-200">{v.sentence}</p>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${LABEL_META[v.label].badge}`}
              >
                {LABEL_META[v.label].name}
              </span>
            </div>
            {v.reason && <p className="mt-1.5 pl-3 text-xs italic text-zinc-500">{v.reason}</p>}
            {v.cited.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1">
                {v.cited.map((cid) => {
                  const ev = evidence[cid];
                  return (
                    <span
                      key={cid}
                      className="group/ev relative cursor-help rounded-md bg-brand-500/10 px-1.5 py-0.5 font-mono text-[10px] text-brand-300 ring-1 ring-brand-400/20 transition hover:bg-brand-500/20"
                    >
                      {cid}
                      {ev && (
                        <span className="pointer-events-none absolute bottom-full left-0 z-20 mb-1.5 hidden w-96 rounded-xl border border-zinc-700/60 bg-surface-deep/95 p-3 text-[11px] leading-snug text-zinc-300 shadow-2xl backdrop-blur-xl group-hover/ev:block">
                          <span className="mb-1 flex items-center gap-1.5 font-semibold text-zinc-100">
                            <span className="text-xs">
                              {ev.source_type === "web"
                                ? "🌐"
                                : ev.source_type === "scholar"
                                  ? "🎓"
                                  : ev.source_type === "code"
                                    ? "🧮"
                                    : "📚"}
                            </span>
                            {ev.title ?? ev.source_type}
                          </span>
                          {ev.url && (
                            <span className="mb-1 block truncate text-brand-400">{ev.url}</span>
                          )}
                          <span className="text-zinc-400">{ev.snippet.slice(0, 300)}…</span>
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
