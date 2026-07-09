export type AgentType = "web" | "code" | "rag";

export interface SubQuestion {
  id: string;
  question: string;
  agent: AgentType;
  depends_on: string[];
  rationale: string;
}

export interface Plan {
  sub_questions: SubQuestion[];
}

export type VerdictLabel = "supported" | "partially_supported" | "unsupported" | "no_claim";

export interface Verdict {
  index: number;
  sentence: string;
  cited: string[];
  label: VerdictLabel;
  reason: string;
}

export interface TraceEvent {
  seq: number;
  ts: string;
  node: string;
  event: string;
  payload: Record<string, any>;
}

export interface EvidenceInfo {
  title: string | null;
  url: string | null;
  source_type: AgentType;
  snippet: string;
}

export interface RunSummary {
  id: string;
  question: string;
  status: "running" | "done" | "failed";
  coverage: number | null;
  iterations: number | null;
  token_usage: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  unsupported_rate: number | null;
  report_md: string | null;
  report_dir: string | null;
  error: string | null;
  result: {
    plan: Plan | null;
    verdicts: Verdict[];
    evidence: Record<string, EvidenceInfo>;
    findings: any[];
  } | null;
}

export type SqStatus = "pending" | "running" | "done" | "failed";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
