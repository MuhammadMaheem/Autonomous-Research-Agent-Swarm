import { API_URL, RunDetail, RunSummary } from "./types";

export async function startResearch(question: string, useRag = true): Promise<string> {
  const res = await fetch(`${API_URL}/api/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, use_rag: useRag }),
  });
  if (!res.ok) throw new Error(`start failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.run_id as string;
}

export async function listRuns(): Promise<RunSummary[]> {
  const res = await fetch(`${API_URL}/api/research`, { cache: "no-store" });
  if (!res.ok) throw new Error(`list failed: ${res.status}`);
  return res.json();
}

export async function getRun(runId: string): Promise<RunDetail> {
  const res = await fetch(`${API_URL}/api/research/${runId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get failed: ${res.status}`);
  return res.json();
}
