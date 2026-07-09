"""Plug-in domain retriever. Current implementation: BM25 over a local text corpus.

The `Retriever` protocol is the extension point — a hybrid ChromaDB+BM25 retriever
(as in the full plan) drops in without touching the rag_agent node.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import settings


@dataclass
class Chunk:
    id: str
    text: str
    source: str


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int = 5) -> list[Chunk]: ...


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _chunk_file(path: Path, target_words: int = 220) -> list[str]:
    paragraphs = [p.strip() for p in path.read_text(errors="replace").split("\n\n") if p.strip()]
    chunks, cur, count = [], [], 0
    for p in paragraphs:
        cur.append(p)
        count += len(p.split())
        if count >= target_words:
            chunks.append("\n\n".join(cur))
            cur, count = [], 0
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


class BM25Retriever:
    name = "bm25"

    def __init__(self, corpus_dir: Path | None = None):
        from rank_bm25 import BM25Okapi

        corpus_dir = corpus_dir or settings.corpus_dir
        self.chunks: list[Chunk] = []
        for path in sorted(list(corpus_dir.glob("*.md")) + list(corpus_dir.glob("*.txt"))):
            for i, text in enumerate(_chunk_file(path)):
                self.chunks.append(Chunk(id=f"{path.stem}#{i}", text=text, source=path.name))
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self.chunks]) if self.chunks else None

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(scores, range(len(self.chunks))), key=lambda t: -t[0])
        return [self.chunks[i] for s, i in ranked[:k] if s > 0]


class StubRetriever:
    name = "stub"

    def search(self, query: str, k: int = 5) -> list[Chunk]:  # noqa: ARG002
        return [
            Chunk(id="stub#0", source="stub-corpus.md",
                  text="Local corpus stub: retrieval-augmented generation grounds LLM answers in retrieved "
                       "documents, reducing hallucination when answers cite retrieved evidence."),
            Chunk(id="stub#1", source="stub-corpus.md",
                  text="Local corpus stub: citation verification labels each generated sentence as supported, "
                       "partially supported, or unsupported against its cited sources."),
        ]


def get_retriever(mock: bool = False) -> Retriever:
    if mock:
        return StubRetriever()
    r = BM25Retriever()
    return r if r.chunks else StubRetriever()
