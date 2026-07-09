# Human Labeling Protocol — Citation Audit Validation (RQ3)

Purpose: validate the automated citation checker against human judgment, so the coverage
numbers used in RQ1/RQ2 are trustworthy. Precedent: AIS (Rashkin et al., 2021), ALCE
(Gao et al., 2023).

## What you label

For a sampled run, read each **claim sentence** of the report together with the full text of
the evidence it cites (shown in the Citation audit tab of the UI, or in `results.jsonl`
verdicts). Assign exactly one label:

| Label | Definition |
|---|---|
| `supported` | Every factual claim in the sentence is directly backed by its cited evidence. Numbers, dates and named entities must appear in, or follow arithmetically from, the evidence. |
| `partially_supported` | Some claims backed, others not; or the evidence only loosely implies the claim. |
| `unsupported` | Factual claim(s) with no citation, an irrelevant citation, or evidence that does not back the claim. |
| `no_claim` | No verifiable factual claim: transitions, section framing, questions, statements about the report itself. |

Rules:
- Judge ONLY against the cited evidence text — never your own knowledge of the topic.
- "According to the cited source, <sentence>" must read as true for `supported` (AIS test).
- When torn between two labels, choose the more severe (lower) one.
- Do not look at the checker's label before assigning yours.

## Procedure

1. Sample 10 questions; for each, take the swarm report and the baseline report (~300 claim
   sentences total).
2. Annotator A labels everything. Annotator B independently labels a random 30% subset.
3. Compute inter-annotator agreement (Cohen's kappa) on the overlap; report it. Target > 0.6.
4. Save labels as `eval/labels/human_labels.csv` with header:
   `run_key,sentence_index,human_label`  where `run_key` is `<question_id>:<system>`
   (e.g. `w01:swarm`) and `sentence_index` matches the verdict `index` in results.jsonl.
5. Run `uv run python -m eval.metrics` — it reports checker-vs-human kappa automatically.

## Metrics derived from these labels

- **Checker precision** = |checker-supported ∧ human-supported| / |checker-supported|
- **Checker recall** = |checker-supported ∧ human-supported| / |human-supported|
- **Report faithfulness** (headline RQ1 number) = human-supported fraction of claim sentences,
  compared between swarm and baseline on the same questions.
