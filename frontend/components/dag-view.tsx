"use client";
import { useMemo } from "react";
import {
  Background,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plan, SqStatus } from "@/lib/types";

const AGENT_META: Record<string, { icon: string; color: string; label: string }> = {
  web: { icon: "🌐", color: "text-sky-400", label: "Web search" },
  code: { icon: "🧮", color: "text-emerald-400", label: "Code sandbox" },
  rag: { icon: "📚", color: "text-violet-400", label: "RAG corpus" },
  scholar: { icon: "🎓", color: "text-amber-400", label: "Scholar" },
};

const STATUS_NODE: Record<SqStatus, string> = {
  pending: "border-zinc-700/50 bg-surface-panel/90",
  running: "border-brand-400/60 bg-brand-500/[0.07] node-running",
  done: "border-emerald-500/40 bg-emerald-500/[0.05]",
  failed: "border-rose-500/50 bg-rose-500/[0.05]",
};

const STATUS_DOT: Record<SqStatus, string> = {
  pending: "bg-zinc-600",
  running: "bg-brand-400 pulse-dot",
  done: "bg-emerald-400",
  failed: "bg-rose-400",
};

function SqNode({
  data,
}: NodeProps<
  Node<{ label: string; agent: string; status: SqStatus; question: string; rationale?: string }>
>) {
  const meta = AGENT_META[data.agent] ?? { icon: "?", color: "text-zinc-400", label: data.agent };
  return (
    <div
      title={data.question}
      className={`group relative w-56 overflow-hidden rounded-xl border px-3.5 py-3 text-xs shadow-xl transition-all duration-200 hover:scale-[1.03] hover:shadow-2xl ${STATUS_NODE[data.status]}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-none !bg-brand-400/60"
      />
      <div className="flex items-center gap-2">
        <span className={`text-sm ${meta.color}`}>{meta.icon}</span>
        <span className="font-semibold tracking-wide text-zinc-200">{data.label}</span>
        <span className={`ml-auto h-2 w-2 rounded-full ${STATUS_DOT[data.status]}`} />
      </div>
      <p className="mt-2 line-clamp-2 leading-relaxed text-zinc-400">{data.question}</p>
      {/* hover tooltip */}
      <div className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 hidden w-64 rounded-lg border border-zinc-700/60 bg-surface-deep/95 p-3 shadow-2xl backdrop-blur-xl group-hover:block">
        <p className="text-[11px] leading-snug text-zinc-300">{data.question}</p>
        {data.rationale && (
          <p className="mt-1.5 text-[10px] text-zinc-500">
            <span className="font-medium text-zinc-400">Rationale:</span> {data.rationale}
          </p>
        )}
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-zinc-500">
          <span className={meta.color}>{meta.icon}</span>
          <span>{meta.label}</span>
          <span className="ml-auto capitalize">{data.status}</span>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-none !bg-brand-400/60"
      />
    </div>
  );
}

const nodeTypes = { sq: SqNode };

/** Topological wave layout: x = wave index, y = position within wave. */
function layout(plan: Plan): Map<string, { wave: number; row: number }> {
  const deps = new Map(plan.sub_questions.map((s) => [s.id, new Set(s.depends_on)]));
  const pos = new Map<string, { wave: number; row: number }>();
  let wave = 0;
  const remaining = new Set(deps.keys());
  while (remaining.size > 0 && wave < 10) {
    const ready = [...remaining].filter((id) =>
      [...deps.get(id)!].every((d) => pos.has(d) || !remaining.has(d))
    );
    if (ready.length === 0) break;
    ready.forEach((id, i) => {
      pos.set(id, { wave, row: i });
      remaining.delete(id);
    });
    wave++;
  }
  [...remaining].forEach((id, i) => pos.set(id, { wave, row: i }));
  return pos;
}

export function DagView({
  plan,
  sqStatus,
}: {
  plan: Plan | null;
  sqStatus: Record<string, SqStatus>;
}) {
  const { nodes, edges } = useMemo(() => {
    if (!plan) return { nodes: [] as Node[], edges: [] as Edge[] };
    const pos = layout(plan);
    const nodes: Node[] = plan.sub_questions.map((sq) => {
      const p = pos.get(sq.id) ?? { wave: 0, row: 0 };
      return {
        id: sq.id,
        type: "sq",
        position: { x: p.wave * 280, y: p.row * 120 },
        data: {
          label: sq.id,
          agent: sq.agent,
          status: sqStatus[sq.id] ?? "pending",
          question: sq.question,
          rationale: sq.rationale,
        },
      };
    });
    const edges: Edge[] = plan.sub_questions.flatMap((sq) =>
      sq.depends_on.map((dep) => {
        const running = (sqStatus[sq.id] ?? "pending") === "running";
        return {
          id: `${dep}->${sq.id}`,
          source: dep,
          target: sq.id,
          animated: running,
          style: {
            stroke: running ? "#38bdf8" : "#334155",
            strokeWidth: running ? 2 : 1.5,
            strokeDasharray: running ? "6 4" : undefined,
          },
        };
      })
    );
    return { nodes, edges };
  }, [plan, sqStatus]);

  if (!plan) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-zinc-500">
        <div className="relative">
          <span className="text-2xl opacity-40">🗺️</span>
          <span className="pulse-dot absolute -right-1 -top-1 h-2 w-2 rounded-full bg-brand-400" />
        </div>
        <span className="text-zinc-600">waiting for the planner…</span>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      zoomOnScroll={false}
      colorMode="dark"
    >
      <Background gap={20} size={1} color="rgba(148, 163, 184, 0.08)" />
    </ReactFlow>
  );
}
