"""Tests for the scholar / OpenAlex academic paper search feature."""
import pytest

from app.services.search import ScholarSearchProvider, reconstruct_abstract


# -- Unit tests for reconstruct_abstract --

def test_reconstruct_abstract_simple():
    inverted = {"hello": [0], "world": [1], "test": [2]}
    assert reconstruct_abstract(inverted) == "hello world test"


def test_reconstruct_abstract_out_of_order():
    inverted = {"world": [1], "hello": [0], "again": [2]}
    assert reconstruct_abstract(inverted) == "hello world again"


def test_reconstruct_abstract_multi_position():
    """A word appearing at multiple positions should appear in each."""
    inverted = {"the": [0, 3], "cat": [1], "sat": [2], "mat": [4]}
    assert reconstruct_abstract(inverted) == "the cat sat the mat"


def test_reconstruct_abstract_none():
    assert reconstruct_abstract(None) is None


def test_reconstruct_abstract_empty():
    assert reconstruct_abstract({}) is None


# -- Integration tests (hit live OpenAlex API) --

@pytest.mark.asyncio
async def test_scholar_search_returns_results():
    """Integration: basic academic query returns results with expected fields."""
    provider = ScholarSearchProvider()
    results = await provider.search("transformer attention mechanism", k=3)
    assert len(results) >= 1
    for r in results:
        assert r.title
        assert r.url
        assert r.snippet


@pytest.mark.asyncio
async def test_scholar_search_empty_query():
    """Empty query should return a list (possibly empty), not crash."""
    provider = ScholarSearchProvider()
    results = await provider.search("", k=3)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_scholar_search_has_doi_urls():
    """Most academic papers should have DOI links."""
    provider = ScholarSearchProvider()
    results = await provider.search("large language models", k=5)
    assert len(results) >= 2
    doi_count = sum(1 for r in results if "doi.org" in (r.url or ""))
    assert doi_count >= 1, "Expected at least one result with a DOI link"
