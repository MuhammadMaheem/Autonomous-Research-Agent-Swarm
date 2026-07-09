"use client";
import { useMemo } from "react";
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plan, SqStatus } from "@/lib/types";

const AGENT_ICON: Record<string, string> = { web: "🌐", code: "🧮", rag: "📚" };

const STATUS_STYLE: Record<SqStatus, string> = {
  pending: "border-zinc-700 bg-zinc-900 text-zinc-400",
  running: "border-indigo-500 bg-indigo-950/60 text-indigo-200 node-running",
  done: "border-emerald-600 bg-emerald-950/50 text-emerald-100",
  failed: "border-rose-600 bg-rose-950/50 text-rose-200",
};

function SqNode({ data }: NodeProps<Node<{ label: string; agent: string; status: SqStatus; question: string }>>) {
  return (
    <div title={data.question}
         className={`w-52 rounded-lg border px-3 py-2 text-xs shadow-lg transition-colors ${STATUS_STYLE[data.status]}`}>
      <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
      <div className="flex items-center gap-2 font-semibold">
        <span>{AGENT_ICON[data.agent] ?? "?"}</span>
        <span>{data.label}</span>
        <span className="ml-auto text-[10px] uppercase opacity-70">{data.status}</span>
      </div>
      <div className="mt-1 line-clamp-2 opacity-80">{data.question}</div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
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
      sq.depends_on.map((dep) => ({
        id: `${dep}->${sq.id}`,
        source: dep,
        target: sq.id,
        animated: (sqStatus[sq.id] ?? "pending") === "running",
        style: { stroke: "#52525b" },
      })));
    return { nodes, edges };
  }, [plan, sqStatus]);

  if (!plan) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        waiting for the planner…
      </div>
    );
  }
  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView
               proOptions={{ hideAttribution: true }}
               nodesDraggable={false} nodesConnectable={false} zoomOnScroll={false}
               colorMode="dark">
      <Background gap={24} color="#27272a" />
    </ReactFlow>
  );
}
