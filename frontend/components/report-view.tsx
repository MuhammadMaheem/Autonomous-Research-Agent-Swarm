"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportView({ markdown, streaming }: { markdown: string; streaming?: boolean }) {
  if (!markdown) {
    return (
      <div className="flex flex-col items-center gap-3 p-14 text-sm text-zinc-500">
        <span className="text-3xl opacity-50">✍️</span>
        no report yet — the synthesizer has not run
      </div>
    );
  }
  return (
    <article className="prose prose-invert prose-zinc max-w-none p-8 prose-headings:tracking-tight prose-h1:text-gradient prose-h1:text-3xl prose-h2:mt-8 prose-h2:border-b prose-h2:border-white/[0.06] prose-h2:pb-2 prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline prose-strong:text-zinc-100 prose-li:marker:text-indigo-400">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {streaming && <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-gradient-to-b from-indigo-400 to-fuchsia-400" />}
    </article>
  );
}
