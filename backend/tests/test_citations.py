from app.graph.nodes.citation_checker import _fallback_verdicts, split_sentences
from app.graph.nodes.finalizer import renumber_citations

SAMPLE = """# Report Title

Intro sentence with a citation [E1_1]. Another claim here [E1_2][E2_1].

## Section

- Bullet claim about numbers [E2_1].
- Short one.

```python
code = "should be ignored [E9_9]"
```

| table | ignored |
|---|---|

Closing sentence without citation that still makes a factual claim about adoption rates.
"""


def test_split_sentences_markdown_aware():
    sents = split_sentences(SAMPLE)
    joined = " ".join(sents)
    assert "Report Title" not in joined          # header skipped
    assert "should be ignored" not in joined     # fence skipped
    assert "table" not in joined                 # table skipped
    assert any("Bullet claim" in s for s in sents)
    assert any(s.startswith("Intro sentence") for s in sents)
    assert any("Closing sentence" in s for s in sents)


def test_renumber_citations_first_appearance_order():
    draft = "A [E2_1]. B [E1_1]. C [E2_1][E3_1]. Unknown [E9_9]."
    text, order = renumber_citations(draft, {"E1_1", "E2_1", "E3_1"})
    assert order == ["E2_1", "E1_1", "E3_1"]
    assert "A [1]." in text and "B [2]." in text and "C [1][3]." in text
    assert "[E9_9]" in text  # unknown untouched


def test_fallback_verdicts_conservative():
    batch = [
        (0, "Cited claim about stats [E1_1].", ["E1_1"]),
        (1, "Uncited factual claim about adoption rates in 2024.", []),
        (2, "In summary then.", []),
    ]
    out = {v.index: v.label for v in _fallback_verdicts(batch)}
    assert out[0] == "partially_supported"
    assert out[1] == "unsupported"
    assert out[2] == "no_claim"


def test_normalize_citations_variants():
    from app.graph.state import normalize_citations
    assert normalize_citations("Claim [ E1_1 ].") == "Claim [E1_1]."
    assert normalize_citations("Claim [E1_1, E2_3].") == "Claim [E1_1][E2_3]."
    assert normalize_citations("Claim [E1_1; E2_3].") == "Claim [E1_1][E2_3]."
    assert normalize_citations("Already [E1_1][E2_3].") == "Already [E1_1][E2_3]."
    assert normalize_citations("Not a cite [2020, 2021].") == "Not a cite [2020, 2021]."


def test_sanitize_query():
    from app.services.search import sanitize_query
    assert sanitize_query("How does Spectrum‑RAG compare to single‑vector RAG?") == \
        "How does Spectrum-RAG compare to single-vector RAG"
    long = "what " * 60
    out = sanitize_query(long)
    assert len(out) <= 130 and not out.endswith(" ")
    assert sanitize_query("  spaced   out\nquery  ") == "spaced out query"
