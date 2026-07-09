# Evaluating Citation Quality in Generated Text

Attribution evaluation asks whether generated text is supported by cited sources. The AIS framework (Attributable to Identified Sources, Rashkin et al., 2021) defines a sentence as attributable if a human could say "according to the cited source, ..." and have the statement be fully supported. AIS established the human-annotation protocol later work builds on.

ALCE (Gao et al., 2023) operationalized citation quality for automatic benchmarking of LLMs that generate text with citations. It measures citation recall — the fraction of generated statements that are supported by their cited passages — and citation precision — the fraction of citations that are actually necessary and relevant to the statements they attach to. ALCE uses a natural language inference (NLI) model to approximate human judgments, and reports that even strong LLMs frequently produce unsupported statements or irrelevant citations.

FActScore (Min et al., 2023) decomposes generated text into atomic facts and verifies each against a knowledge source, reporting the fraction of supported atomic facts. This finer granularity catches sentences that mix supported and unsupported claims — a common failure mode that sentence-level labels blur.

A practical three-way labeling scheme for sentence-level auditing is: supported (all claims in the sentence are backed by cited evidence), partially supported (some claims backed, others not), and unsupported (no adequate backing, including missing or irrelevant citations). Sentences without verifiable claims (transitions, framing) are excluded from the denominator. Coverage is then the supported fraction of claim-bearing sentences.

Automated judges (LLMs or NLI models) approximate human labels imperfectly, so studies validate the judge: a sample of sentences is labeled by humans, and agreement (e.g., Cohen's kappa) between judge and human labels is reported. Kappa above 0.6 is conventionally considered substantial agreement. Without this validation step, coverage numbers produced by an automated checker cannot be trusted as evaluation metrics.
