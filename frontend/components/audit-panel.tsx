"use client";
import { EvidenceInfo, Verdict, VerdictLabel } from "@/lib/types";

const LABEL_STYLE: Record<VerdictLabel, { border: string; badge: string; bar: string; name: string }> = {
  supported: {
    border: "border-emerald-400/60", badge: "bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-400/25",
    bar: "bg-emerald-400", name: "supported",
  },
  partially_supported: {
    border: "border-amber-400/60", badge: "bg-amber-500/10 text-amber-300 ring-1 ring-amber-400/25",
    bar: "bg-amber-400", name: "partial",
  },
  unsupported: {
    border: "border-rose-400/60", badge: "bg-rose-500/10 text-rose-300 ring-1 ring-rose-400/25",
    bar: "bg-rose-400", name: "unsupported",
  },
  no_claim: {
    border: "border-white/15", badge: "bg-white/[0.05] text-zinc-400 ring-1 ring-white/10",
    bar: "bg-zinc-600", name: "no claim",
  },
};

const LABEL_ORDER: VerdictLabel[] = ["supported", "partially_supported", "unsupported", "no_claim"];

export function AuditPanel({ verdicts, evidence }: {
  verdicts: Verdict[];
  evidence: Record<string, EvidenceInfo>;
}) {
  if (verdicts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 p-14 text-sm text-zinc-500">
        <span className="text-3xl opacity-50">🔬</span>
        no citation audit yet — the checker has not run
      </div>
    );
  }
  const counts = verdicts.reduce<Record<string, number>>((acc, v) => {
    acc[v.label] = (acc[v.label] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <div className="space-y-2 p-4">
      {/* label counts + stacked distribution bar */}
      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          {LABEL_ORDER.map((l) => (
            <span key={l} className={`rounded-full px-3 py-1 font-medium ${LABEL_STYLE[l].badge}`}>
              {LABEL_STYLE[l].name}: {counts[l] ?? 0}
            </span>
          ))}
        </div>
        <div className="flex h-2 w-full overflow-hidden rounded-full bg-zinc-800/80">
          {LABEL_ORDER.map((l) => {
            const n = counts[l] ?? 0;
            if (n === 0) return null;
            return (
              <span key={l} className={`h-full ${LABEL_STYLE[l].bar}`}
                    style={{ width: `${(n / verdicts.length) * 100}%` }} />
            );
          })}
        </div>
      </div>
      {verdicts.map((v) => (
        <div key={v.index}
             className={`group relative rounded-lg border-l-2 bg-white/[0.025] p-3.5 text-sm transition hover:bg-white/[0.045] ${LABEL_STYLE[v.label].border}`}>
          <div className="flex items-start justify-between gap-3">
            <p className="leading-relaxed text-zinc-200">{v.sentence}</p>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${LABEL_STYLE[v.label].badge}`}>
              {LABEL_STYLE[v.label].name}
            </span>
          </div>
          {v.reason && <p className="mt-1.5 text-xs italic text-zinc-500">{v.reason}</p>}
          {v.cited.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {v.cited.map((cid) => {
                const ev = evidence[cid];
                return (
                  <span key={cid}
                        className="group/ev relative cursor-help rounded-md bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300 ring-1 ring-indigo-400/20 transition hover:bg-indigo-500/20">
                    {cid}
                    {ev && (
                      <span className="pointer-events-none absolute bottom-full left-0 z-20 mb-1.5 hidden w-80 rounded-xl border border-white/10 bg-zinc-950/95 p-3 text-[11px] leading-snug text-zinc-300 shadow-2xl backdrop-blur-xl group-hover/ev:block">
                        <span className="mb-1 block font-semibold text-zinc-100">
                          {ev.title ?? ev.source_type}
                        </span>
                        {ev.url && <span className="mb-1 block truncate text-indigo-400">{ev.url}</span>}
                        {ev.snippet.slice(0, 350)}…
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
  );
}
