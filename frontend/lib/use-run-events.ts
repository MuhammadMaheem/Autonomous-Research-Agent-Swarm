"use client";
import { useEffect, useReducer, useRef } from "react";
import { API_URL, Plan, SqStatus, TraceEvent, Verdict } from "./types";

export interface LiveRunState {
  plan: Plan | null;
  iteration: number;
  sqStatus: Record<string, SqStatus>;
  events: TraceEvent[];
  draft: string;
  verdicts: Verdict[];
  coverage: number | null;
  unsupportedRate: number | null;
  stage: string;
  finished: boolean;
  failed: string | null;
  connected: boolean;
}

const initial: LiveRunState = {
  plan: null,
  iteration: 0,
  sqStatus: {},
  events: [],
  draft: "",
  verdicts: [],
  coverage: null,
  unsupportedRate: null,
  stage: "connecting",
  finished: false,
  failed: null,
  connected: false,
};

type Action = { type: "event"; ev: TraceEvent } | { type: "connected" } | { type: "disconnected" };

const AGENT_NODES = new Set(["web_agent", "code_agent", "rag_agent"]);
// draft_token / verdict spam is summarized in dedicated panels, not the raw feed
const FEED_SKIP = new Set(["draft_token", "verdict"]);

function reduce(state: LiveRunState, action: Action): LiveRunState {
  if (action.type === "connected") return { ...state, connected: true, stage: state.stage === "connecting" ? "waiting" : state.stage };
  if (action.type === "disconnected") return { ...state, connected: false };
  const ev = action.ev;
  const next: LiveRunState = { ...state };

  if (!FEED_SKIP.has(ev.event)) next.events = [...state.events, ev].slice(-500);
  if (!["draft_token", "verdict"].includes(ev.event)) next.stage = ev.node;

  switch (ev.event) {
    case "plan_ready": {
      next.plan = ev.payload.plan as Plan;
      next.iteration = ev.payload.iteration ?? 0;
      const statuses: Record<string, SqStatus> = {};
      for (const sq of next.plan!.sub_questions) {
        statuses[sq.id] = state.sqStatus[sq.id] === "done" || state.sqStatus[sq.id] === "failed"
          ? state.sqStatus[sq.id] : "pending";
      }
      next.sqStatus = statuses;
      break;
    }
    case "node_started":
      if (AGENT_NODES.has(ev.node) && ev.payload.sub_question_id) {
        next.sqStatus = { ...state.sqStatus, [ev.payload.sub_question_id]: "running" };
      }
      if (ev.node === "synthesizer") next.draft = "";
      if (ev.node === "citation_checker" && !ev.payload.warning) next.verdicts = [];
      break;
    case "node_finished":
      if (AGENT_NODES.has(ev.node) && ev.payload.sub_question_id) {
        next.sqStatus = {
          ...state.sqStatus,
          [ev.payload.sub_question_id]: ev.payload.error ? "failed" : "done",
        };
      }
      break;
    case "draft_token":
      next.draft = ev.payload.reset ? "" : state.draft + (ev.payload.text ?? "");
      break;
    case "verdict":
      next.verdicts = [...state.verdicts, ev.payload as Verdict];
      break;
    case "citation_summary":
      next.coverage = ev.payload.coverage;
      next.unsupportedRate = ev.payload.unsupported_rate;
      break;
    case "run_finished":
      next.finished = true;
      next.coverage = ev.payload.coverage ?? state.coverage;
      break;
    case "run_failed":
      next.failed = ev.payload.error ?? "unknown error";
      next.finished = true;
      break;
  }
  return next;
}

export function useRunEvents(runId: string): LiveRunState {
  const [state, dispatch] = useReducer(reduce, initial);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(`${API_URL}/api/research/${runId}/events`);
    sourceRef.current = es;
    es.onopen = () => dispatch({ type: "connected" });
    es.onmessage = (msg) => {
      try {
        dispatch({ type: "event", ev: JSON.parse(msg.data) });
      } catch {
        /* keepalive or malformed line */
      }
    };
    es.onerror = () => dispatch({ type: "disconnected" });
    return () => es.close();
  }, [runId]);

  useEffect(() => {
    if (state.finished) sourceRef.current?.close();
  }, [state.finished]);

  return state;
}
