"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportView({ markdown, streaming }: { markdown: string; streaming?: boolean }) {
  if (!markdown) {
    return <div className="p-8 text-sm text-zinc-500">no report yet — the synthesizer has not run</div>;
  }
  return (
    <article className="prose prose-invert prose-zinc max-w-none p-6 prose-headings:tracking-tight prose-a:text-indigo-400">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {streaming && <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-indigo-400" />}
    </article>
  );
}
