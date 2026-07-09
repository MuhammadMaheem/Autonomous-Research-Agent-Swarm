# Hallucination in Large Language Models

Hallucination denotes generated content that is fluent but factually wrong or unverifiable. A common taxonomy distinguishes intrinsic hallucination (output contradicts the provided source) from extrinsic hallucination (output cannot be verified against the source at all). Both matter for research assistants: intrinsic errors misrepresent retrieved evidence, extrinsic errors fabricate beyond it.

Causes include the next-token training objective (which rewards plausible continuations, not verified facts), knowledge cutoffs, exposure to noisy training data, and sampling temperature. Instruction-tuned models also exhibit sycophantic hallucination: agreeing with a user's false premise rather than correcting it.

Mitigation strategies span the generation pipeline. Retrieval grounding (RAG) supplies verifiable context. Constrained decoding and lower temperature reduce fabrication in structured outputs. Post-hoc verification checks generated claims against sources — the approach used in citation-audited report generation, where each sentence is validated against the evidence it cites. Self-consistency sampling and chain-of-verification prompt the model to cross-examine its own outputs. None of these eliminates hallucination; layered defenses with a final verification gate are the accepted best practice.

Measurement requires a ground truth. For closed-book QA, benchmarks like TruthfulQA probe common misconceptions. For grounded generation, faithfulness metrics compare output against provided sources: entailment-based scores (an NLI model judges whether the source entails the claim), QA-based scores (questions generated from the output are answered from the source), and human annotation, which remains the gold standard.

In multi-agent pipelines hallucination can compound: a fabricated "fact" produced by one agent enters a downstream agent's context as if it were evidence. Verification is therefore most effective at the synthesis boundary — after evidence gathering, before final output — where every claim can be traced to a concrete retrieved artifact with an identifier.
