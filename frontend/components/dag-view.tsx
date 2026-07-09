"use client";
import { useMemo } from "react";
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plan, SqStatus } from "@/lib/types";

const AGENT_ICON: Record<string, string> = { web: "🌐", code: "🧮", rag: "📚" };
const AGENT_CHIP: Record<string, string> = {
  web: "bg-sky-500/15 text-sky-300 ring-1 ring-sky-400/25",
  code: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/25",
  rag: "bg-violet-500/15 text-violet-300 ring-1 ring-violet-400/25",
};

const STATUS_STYLE: Record<SqStatus, string> = {
  pending: "border-white/10 bg-zinc-900/80 text-zinc-400",
  running: "border-indigo-400/70 bg-indigo-950/70 text-indigo-100 node-running",
  done: "border-emerald-400/50 bg-emerald-950/60 text-emerald-100 shadow-[0_0_14px_rgba(52,211,153,0.12)]",
  failed: "border-rose-400/60 bg-rose-950/60 text-rose-200 shadow-[0_0_14px_rgba(251,113,133,0.15)]",
};

const STATUS_BADGE: Record<SqStatus, string> = {
  pending: "bg-white/[0.06] text-zinc-500",
  running: "bg-indigo-400/20 text-indigo-200",
  done: "bg-emerald-400/20 text-emerald-300",
  failed: "bg-rose-400/20 text-rose-300",
};

function SqNode({ data }: NodeProps<Node<{ label: string; agent: string; status: SqStatus; question: string }>>) {
  return (
    <div title={data.question}
         className={`relative w-52 overflow-hidden rounded-xl border px-3 py-2.5 text-xs shadow-lg backdrop-blur-sm transition-colors ${STATUS_STYLE[data.status]}`}>
      {data.status === "running" && <div className="shimmer absolute inset-x-0 top-0 h-0.5" />}
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-none !bg-indigo-400/70" />
      <div className="flex items-center gap-1.5 font-semibold">
        <span className={`flex h-5 w-5 items-center justify-center rounded-md text-[10px] ${AGENT_CHIP[data.agent] ?? "bg-white/[0.06]"}`}>
          {AGENT_ICON[data.agent] ?? "?"}
        </span>
        <span className="tracking-wide">{data.label}</span>
        <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider ${STATUS_BADGE[data.status]}`}>
          {data.status}
        </span>
      </div>
      <div className="mt-1.5 line-clamp-2 leading-snug opacity-80">{data.question}</div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-none !bg-fuchsia-400/70" />
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
    const ready = [...remaining].filter((id) => [...deps.get(id)!].every((d) => pos.has(d) || !remaining.has(d)));
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

export function DagView({ plan, sqStatus }: { plan: Plan | null; sqStatus: Record<string, SqStatus> }) {
  const { nodes, edges } = useMemo(() => {
    if (!plan) return { nodes: [] as Node[], edges: [] as Edge[] };
    const pos = layout(plan);
    const nodes: Node[] = plan.sub_questions.map((sq) => {
      const p = pos.get(sq.id) ?? { wave: 0, row: 0 };
      return {
        id: sq.id,
        type: "sq",
        position: { x: p.wave * 260, y: p.row * 110 },
        data: { label: sq.id, agent: sq.agent, status: sqStatus[sq.id] ?? "pending", question: sq.question },
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
          style: { stroke: running ? "#818cf8" : "#3f3f46", strokeWidth: running ? 2 : 1.5 },
        };
      }));
    return { nodes, edges };
  }, [plan, sqStatus]);

  if (!plan) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-zinc-500">
        <span className="pulse-dot text-2xl">🗺️</span>
        waiting for the planner…
      </div>
    );
  }
  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView
               proOptions={{ hideAttribution: true }}
               nodesDraggable={false} nodesConnectable={false} zoomOnScroll={false}
               colorMode="dark">
      <Background gap={26} color="#26263a" />
    </ReactFlow>
  );
}
