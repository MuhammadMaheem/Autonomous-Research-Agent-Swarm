# Retrieval-Augmented Generation: Fundamentals

Retrieval-augmented generation (RAG) couples a large language model with an external retrieval system. At query time, relevant documents are retrieved from a corpus and injected into the model's context, so the model generates answers grounded in retrieved text rather than relying solely on parametric knowledge. The approach was popularized by Lewis et al. (2020), who combined a dense passage retriever with a sequence-to-sequence generator and showed improved factual accuracy on knowledge-intensive tasks.

A standard RAG pipeline has four stages: document ingestion (parsing and cleaning source files), chunking (splitting documents into passages, typically 200-800 tokens with 10-20% overlap), indexing (embedding chunks into a vector store and/or building a lexical index), and retrieval-generation (fetching top-k relevant chunks and conditioning the LLM on them).

Hybrid retrieval combines lexical matching (BM25) with dense vector similarity. BM25 excels at exact term matching — identifiers, names, rare technical terms — while dense embeddings capture semantic similarity between differently-worded texts. Fusion methods such as Reciprocal Rank Fusion (RRF) merge the two ranked lists; RRF scores each document by the sum of 1/(k + rank) across the lists, with k commonly set to 60. Empirical studies repeatedly find hybrid retrieval outperforms either method alone on heterogeneous corpora.

Chunk size trades off precision against context: small chunks improve retrieval precision but can strip away context needed to interpret the passage, while large chunks dilute the relevance signal. Re-ranking retrieved candidates with a cross-encoder is a common second-stage refinement that improves precision at the cost of latency.

RAG systems reduce, but do not eliminate, hallucination. The model can still ignore retrieved evidence, over-generalize from partial matches, or blend retrieved facts with fabricated details. This motivates post-generation verification such as citation checking, where each generated claim is validated against the retrieved sources that it cites.
