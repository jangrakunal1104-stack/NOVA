"""
Tests for core.tavily_search.TavilySearch. Deliberately does NOT require a
real TAVILY_API_KEY or make network calls -- it verifies the wrapper
degrades gracefully (no crash) when the key or the `tavily` package isn't
available, and that format_for_prompt() always produces a usable block.

If you DO have TAVILY_API_KEY set when running pytest, this still passes:
these tests only exercise the no-key/no-crash path deliberately by
clearing the env var for the duration of the test.
"""
import os
import pytest

from core.tavily_search import TavilySearch


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


def test_search_without_api_key_does_not_crash(no_key):
    results = TavilySearch().search("what's the latest AI news")
    assert isinstance(results, list)
    assert len(results) == 1
    assert "content" in results[0]


def test_format_for_prompt_on_empty_results():
    assert TavilySearch().format_for_prompt([]) == "No web search results available."


def test_format_for_prompt_includes_markers_and_sources():
    results = [
        {"title": "Direct Answer", "content": "Some answer text"},
        {"title": "A source", "url": "https://example.com", "content": "snippet"},
    ]
    block = TavilySearch().format_for_prompt(results)
    assert "LIVE WEB SEARCH RESULTS" in block
    assert "Some answer text" in block
    assert "https://example.com" in block
    assert "END SEARCH RESULTS" in block
