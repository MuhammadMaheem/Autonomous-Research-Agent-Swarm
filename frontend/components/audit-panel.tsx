"use client";
import { EvidenceInfo, Verdict, VerdictLabel } from "@/lib/types";

const LABEL_STYLE: Record<VerdictLabel, { border: string; badge: string; name: string }> = {
  supported: { border: "border-emerald-600", badge: "bg-emerald-950 text-emerald-300", name: "supported" },
  partially_supported: { border: "border-amber-600", badge: "bg-amber-950 text-amber-300", name: "partial" },
  unsupported: { border: "border-rose-600", badge: "bg-rose-950 text-rose-300", name: "unsupported" },
  no_claim: { border: "border-zinc-700", badge: "bg-zinc-800 text-zinc-400", name: "no claim" },
};

export function AuditPanel({ verdicts, evidence }: {
  verdicts: Verdict[];
  evidence: Record<string, EvidenceInfo>;
}) {
  if (verdicts.length === 0) {
    return <div className="p-8 text-sm text-zinc-500">no citation audit yet — the checker has not run</div>;
  }
  const counts = verdicts.reduce<Record<string, number>>((acc, v) => {
    acc[v.label] = (acc[v.label] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <div className="space-y-2 p-4">
      <div className="mb-4 flex flex-wrap gap-2 text-xs">
        {(Object.keys(LABEL_STYLE) as VerdictLabel[]).map((l) => (
          <span key={l} className={`rounded-full px-3 py-1 ${LABEL_STYLE[l].badge}`}>
            {LABEL_STYLE[l].name}: {counts[l] ?? 0}
          </span>
        ))}
      </div>
      {verdicts.map((v) => (
        <div key={v.index}
             className={`group relative rounded-md border-l-4 bg-zinc-900/60 p-3 text-sm ${LABEL_STYLE[v.label].border}`}>
          <div className="flex items-start justify-between gap-3">
            <p className="text-zinc-200">{v.sentence}</p>
            <span className={`shrink-0 rounded px-2 py-0.5 text-[10px] uppercase tracking-wide ${LABEL_STYLE[v.label].badge}`}>
              {LABEL_STYLE[v.label].name}
            </span>
          </div>
          {v.reason && <p className="mt-1 text-xs italic text-zinc-500">{v.reason}</p>}
          {v.cited.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {v.cited.map((cid) => {
                const ev = evidence[cid];
                return (
                  <span key={cid} className="group/ev relative cursor-help rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-indigo-300">
                    {cid}
                    {ev && (
                      <span className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 hidden w-80 rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-[11px] leading-snug text-zinc-300 shadow-2xl group-hover/ev:block">
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
