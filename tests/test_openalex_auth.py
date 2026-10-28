"""OpenAlex requests carry the user's API key and mailto — and nothing
else does.

Found 2026-09-22: the OpenAlex key was saved in Keychain and exported as
CORPUS_OPENALEX_KEY, but no code read it, so every request went out
keyless while OpenAlex rate-limited 355 of them in an afternoon. The fix
lives in `_api_http.api_get_json`, the one function every OpenAlex call
passes through. These run with urlopen stubbed — nothing hits the net.
"""
from __future__ import annotations

import logging
import urllib.error
from pathlib import Path

import pytest

import _api_http


@pytest.fixture
def captured(monkeypatch):
    """Record the URL each request would have gone to."""
    seen = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def fake_urlopen(req, timeout=None, context=None):
        seen.append(req.full_url)
        return _Resp()

    monkeypatch.setattr(_api_http.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("CORPUS_OPENALEX_KEY", "SECRETKEY123")
    monkeypatch.setenv("CORPUS_MAILTO", "someone@example.edu")
    return seen


def test_openalex_requests_carry_the_key_and_mailto(captured):
    """Catches the reported bug: a configured key that is never sent."""
    _api_http.api_get_json("https://api.openalex.org/works?filter=doi:10.1/x", 5)
    url = captured[0]
    assert "api_key=SECRETKEY123" in url
    assert "mailto=someone%40example.edu" in url
    assert url.startswith("https://api.openalex.org/works?filter=doi:10.1/x&")


def test_a_path_only_openalex_url_gets_a_query_string(captured):
    """Catches appending with '&' to a URL that has no '?' yet, which
    turns the key into part of the DOI in the path."""
    _api_http.api_get_json("https://api.openalex.org/works/https://doi.org/10.1/x", 5)
    assert "/10.1/x?api_key=" in captured[0]


def test_the_key_never_goes_to_other_apis(captured):
    """Catches a loose host check leaking the OpenAlex key to Crossref or
    Semantic Scholar."""
    _api_http.api_get_json("https://api.crossref.org/works/10.1/x", 5)
    _api_http.api_get_json("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1/x", 5)
    _api_http.api_get_json("https://api.openalex.org.evil.example/works", 5)
    assert all("SECRETKEY123" not in u for u in captured)


def test_filter_punctuation_is_not_re_encoded(captured):
    """Catches rebuilding the query: OpenAlex batch filters use '|' and a
    re-encoded filter silently matches nothing."""
    _api_http.api_get_json("https://api.openalex.org/works?filter=doi:10.1/a|10.2/b", 5)
    assert "filter=doi:10.1/a|10.2/b" in captured[0]


def test_a_caller_supplied_mailto_is_left_alone(captured):
    """Catches sending two mailto parameters."""
    _api_http.api_get_json("https://api.openalex.org/works?mailto=other@x.org", 5)
    assert captured[0].count("mailto=") == 1


def test_nothing_is_added_when_nothing_is_configured(monkeypatch, captured):
    """Catches appending empty `api_key=` for users with no key set."""
    monkeypatch.delenv("CORPUS_OPENALEX_KEY")
    monkeypatch.delenv("CORPUS_MAILTO")
    _api_http.api_get_json("https://api.openalex.org/works?filter=x", 5)
    assert captured[0] == "https://api.openalex.org/works?filter=x"


def test_a_failure_log_never_contains_the_key_or_email(monkeypatch, caplog):
    """Catches logging the authenticated URL: server.log would then hold
    the API key and the user's email on every failed request."""
    monkeypatch.setenv("CORPUS_OPENALEX_KEY", "SECRETKEY123")
    monkeypatch.setenv("CORPUS_MAILTO", "someone@example.edu")

    def boom(req, timeout=None, context=None):
        raise urllib.error.URLError("Too Many Requests")

    monkeypatch.setattr(_api_http.urllib.request, "urlopen", boom)
    with caplog.at_level(logging.INFO, logger="corpus.api_http"):
        _api_http.api_get_json("https://api.openalex.org/works?filter=x", 5)
    assert "api_get_json failed" in caplog.text
    assert "SECRETKEY123" not in caplog.text
    assert "someone@example.edu" not in caplog.text


def test_no_openalex_url_hard_codes_a_mailto():
    """Catches re-adding a literal mailto (oa_enrichment once sent the
    fake `mailto=x`, which would also block the real one)."""
    extract = Path(__file__).resolve().parent.parent / "python" / "extract"
    for f in extract.glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if "api.openalex.org" in line:
                assert "mailto=" not in line, f"{f.name}: {line.strip()}"
