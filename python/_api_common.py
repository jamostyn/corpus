"""Shared Flask + frontmatter helpers used by every blueprint.

Kept minimal — anything specific to one blueprint lives with that
blueprint. What lives here:

  * `require_corpus_or_abort` — the 400 gate every corpus-touching
    endpoint calls first.
  * `_fm_dict` + `_walk_summaries` — file-walk + parse helpers used
    by aggregators (entities_api) and per-paper reads (papers_api).
  * `_strip_quotes` + `_parse_json_block` — YAML quirk fixers used by
    aggregators + paper-detail link-key computation.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import abort

from _fm import parse_frontmatter
from _paths import corpus_root, summaries_dir


def require_corpus_or_abort() -> None:
    """400 the request when no corpus_dir is set. Every endpoint that
    reads or writes corpus contents should call this first — the UI
    treats 400 corpus_not_set specifically (empty-state prompt to pick
    a corpus dir), so returning something else would look like a bug."""
    try:
        corpus_root()
    except RuntimeError:
        abort(400, description="corpus_not_set")


# ---------- Parsed-summary cache --------------------------------------
#
# Every list endpoint reads and re-parses EVERY summary on EVERY
# request. Measured 2026-09-17 on a 590-summary corpus: `parse_frontmatter`
# was 76% of total server time across /api/citations, /api/institutions
# and /api/authors — 8730 parses for 9 requests, where 590 would do.
# `/api/citations` alone walked the corpus twice in one request.
#
# So parse each file once and re-use it until the file changes.
# Validated on (mtime_ns, size) rather than mtime alone: a same-size
# rewrite inside the clock's resolution would otherwise serve stale
# frontmatter after a re-extract.
#
# Keyed by absolute path, so tests pointed at different `tmp_path`
# corpora cannot see each other's entries.
_SUMMARY_CACHE: dict[str, tuple[int, int, dict, str]] = {}
# Serialises cache MISSES only; hits never take it. See _read_summary.
_READ_LOCK = threading.Lock()


def clear_summary_cache() -> None:
    """Drop every cached parse. For tests and for any caller that
    rewrites summaries behind the walker's back."""
    _SUMMARY_CACHE.clear()


def _read_summary(md: Path) -> tuple[dict, str] | None:
    """(fm, body) for one summary, parsing only when the file changed.

    Returns None when the file is missing, unreadable, or has no
    frontmatter — the three cases every caller already treats as "skip
    this file".

    The returned dict is a SHALLOW COPY. No caller mutates frontmatter
    today (verified by grep, 2026-09-17), but handing out the cached
    object would mean one that did could silently corrupt every later
    reader. A 40-key copy costs ~1µs against a ~640µs parse.
    """
    key = str(md)
    try:
        st = md.stat()
    except OSError:
        _SUMMARY_CACHE.pop(key, None)
        return None
    hit = _SUMMARY_CACHE.get(key)
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return dict(hit[2]), hit[3]
    # Miss path: one reader at a time, re-checking the cache after the
    # lock. Without this, concurrent cold requests each read every file.
    # 2026-09-21, after a restart: three /api/papers requests (main
    # window, a popped-out note, a reload) each walked ~620 cold summaries
    # at once and all finished together after 218-251s. The first read
    # of a file is slow because ~/Documents is iCloud-synced (File
    # Provider), so tripling the reads roughly tripled the wait.
    with _READ_LOCK:
        hit = _SUMMARY_CACHE.get(key)
        if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return dict(hit[2]), hit[3]
        return _read_summary_uncached(md, key, st)


def _read_summary_uncached(md: Path, key: str, st) -> tuple[dict, str] | None:
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
    except Exception:
        _SUMMARY_CACHE.pop(key, None)
        return None
    if not fm:
        _SUMMARY_CACHE.pop(key, None)
        return None
    _SUMMARY_CACHE[key] = (st.st_mtime_ns, st.st_size, fm, body or "")
    return dict(fm), body or ""


def summary_paths() -> list[Path]:
    """Every summary file, sorted — and the ONE place the parsed cache
    is pruned.

    Pruning has to hang off listing the directory rather than off any
    one walker: `/api/papers` globs for itself, so a prune living only
    inside `_walk_summaries` never ran for it and entries for deleted
    summaries survived for the life of the process. Slug
    canonicalisation renames files on re-extract, so deletions are
    routine, not rare.
    """
    paths = sorted(summaries_dir().glob("*.md"))
    seen = {str(p) for p in paths}
    root = str(summaries_dir())
    for stale in [k for k in _SUMMARY_CACHE
                  if k.startswith(root) and k not in seen]:
        _SUMMARY_CACHE.pop(stale, None)
    return paths


def _fm_dict(md: Path) -> dict:
    """Parse frontmatter for a summary MD, or return {} on failure.
    Failure includes: file missing, decode error, or malformed YAML.
    Callers that need to know parse failed should compare `bool(fm)`.

    Goes through the shared cache, so a paper detail view costs a stat
    rather than a parse when the list endpoints already read the file.
    """
    got = _read_summary(md)
    return got[0] if got else {}


def _walk_summaries():
    """Yield (slug, fm, body) for every parseable summary MD in the
    corpus, silently skipping unreadable / empty-frontmatter files.
    Used by the aggregators (entities_api) and the citation index
    (citations.py) so the file-walk skeleton lives in one place.

    The body is yielded even though the aggregators ignore it: the
    whole file is read to parse the frontmatter regardless, so handing
    back the remainder costs no extra I/O and saves the citation index
    a second walk over the same files."""
    for md in summary_paths():
        got = _read_summary(md)
        if got is None:
            continue
        yield md.stem, got[0], got[1]


def _strip_quotes(s) -> str:
    """`_fm.py` leaves YAML-quoted list items with their surrounding
    quotes attached (an ISSN written `["1041-6080"]` in frontmatter
    comes out as the literal string `"1041-6080"`). Strip a matched
    pair of leading/trailing double or single quotes so keys + display
    don't inherit them."""
    s = str(s).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1].strip()
    return s


def _parse_json_block(v):
    """Some fields (OA `oa_authors`, `x_concepts`) arrive as YAML block
    scalars containing JSON. Accept a list as-is or parse a JSON string;
    return [] on any failure."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            return json.loads(v)
        except Exception:
            return []
    return []
