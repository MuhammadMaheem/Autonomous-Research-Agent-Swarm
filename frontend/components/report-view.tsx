"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportView({ markdown, streaming }: { markdown: string; streaming?: boolean }) {
  const [paraCount, setParaCount] = useState(0);
  const prevCountRef = useRef(0);

  useEffect(() => {
    // Count paragraphs (double newlines) to animate new ones
    const count = (markdown.match(/\n\n/g) || []).length + 1;
    if (count !== prevCountRef.current) {
      prevCountRef.current = count;
      setParaCount(count);
    }
  }, [markdown]);

  if (!markdown) {
    return (
      <div className="flex flex-col items-center gap-3 p-14 text-sm text-zinc-500">
        <div className="relative">
          <span className="text-3xl opacity-40">✍️</span>
          <span className="pulse-dot absolute -right-1 -top-1 h-2 w-2 rounded-full bg-violet-400" />
        </div>
        no report yet — the synthesizer has not run
      </div>
    );
  }

  return (
    <article className="prose prose-invert prose-zinc max-w-none p-8 text-[15px] leading-relaxed prose-headings:tracking-tight prose-h1:text-3xl prose-h1:font-extrabold prose-h2:mt-8 prose-h2:border-b prose-h2:border-zinc-700/40 prose-h2:pb-2 prose-a:text-brand-400 prose-a:no-underline hover:prose-a:underline prose-strong:text-zinc-100 prose-code:rounded prose-code:bg-zinc-800/80 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-brand-300 prose-blockquote:border-l-brand-400/50 prose-blockquote:italic prose-blockquote:text-zinc-400 prose-li:marker:text-brand-400">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {streaming && (
        <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-gradient-to-b from-brand-400 to-teal-400" />
      )}
    </article>
  );
}
