"""Slug collisions on import — who wins, and who gets a suffix.

Jack, 2026-09-17: "is corpus prepared to handle slug collisions? or if
a slug is entered as name-year-2 when no 1 is present?" Asked with 25
papers staged in the inbox and 1108 queued behind them, 56 of which
carry a `-<year>-N` suffix.

Answer to the second half: yes. A `-2` with no `-1` correctly yields
`-1` — the resolver fills the gap rather than counting past it. Corpus
promises nothing about what the number MEANS (Paper Machine's
"-1 = published first" is that project's convention, not this one), so
filling gaps is fine and is pinned below.

The first half was NOT fine. `_resolve_slug_collision` compared
`.strip().lower()` on both sides instead of using `normalize_doi`, and
the literal string "unknown" therefore compared equal to itself — two
different papers with no DOI, same first author, same year, resolved to
the SAME slug and the second overwrote the first. Summary and PDF both.
"""
from __future__ import annotations

import pytest

from extract_api import _resolve_slug_collision


def _put(corpus_dir, slug: str, doi: str) -> None:
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        f"---\ntitle: T\nyear: 2020\nauthor: A, B.\ndoi: {doi}\n---\n",
        encoding="utf-8")


# ---------- the data-loss case ----------

def test_two_papers_with_no_doi_do_not_overwrite_each_other(corpus_dir):
    """Catches: comparing raw DOI strings instead of normalising.

    `doi: unknown` is what the extractor writes when it cannot resolve
    one. Compared literally, "unknown" == "unknown", so the resolver
    reported "same paper, safe to overwrite" for two papers that merely
    both lack a DOI. `normalize_doi` maps "unknown" to "", which reads
    correctly as "no identity, cannot be the same paper"."""
    _put(corpus_dir, "smith-2020", "unknown")
    assert _resolve_slug_collision("smith-2020", "unknown") == "smith-2020-1"


def test_an_empty_doi_never_counts_as_a_match(corpus_dir):
    """Catches: the same bug via the blank rather than the "unknown"
    spelling. Both mean "no DOI" and neither is an identity."""
    _put(corpus_dir, "smith-2020", "")
    assert _resolve_slug_collision("smith-2020", "") == "smith-2020-1"


# ---------- the same-paper case ----------

def test_the_same_paper_reimported_keeps_its_slug(corpus_dir):
    """Catches: breaking re-import.

    Re-extracting a paper must update it in place. If this returned a
    suffix, every re-extract would fork a new copy."""
    _put(corpus_dir, "smith-2020", "10.1000/a")
    assert _resolve_slug_collision("smith-2020", "10.1000/a") == "smith-2020"


def test_the_same_doi_in_url_form_is_recognised(corpus_dir):
    """Catches: treating `https://doi.org/10.1000/a` as different from
    `10.1000/a`.

    Different sources deposit different forms of the same DOI. Without
    normalisation a re-import produces a spurious `-1` — which is
    exactly how duplicate-DOI pairs (a known open issue) get created."""
    _put(corpus_dir, "smith-2020", "10.1000/a")
    assert _resolve_slug_collision(
        "smith-2020", "https://doi.org/10.1000/a") == "smith-2020"


def test_doi_matching_ignores_case(corpus_dir):
    """Catches: dropping case folding. DOIs are case-insensitive and
    publishers are inconsistent about it."""
    _put(corpus_dir, "smith-2020", "10.1000/ABC")
    assert _resolve_slug_collision("smith-2020", "10.1000/abc") == "smith-2020"


# ---------- genuinely different papers ----------

def test_a_different_doi_gets_a_suffix(corpus_dir):
    """Catches: overwriting a different paper that shares an
    author-year. This is the whole reason suffixes exist."""
    _put(corpus_dir, "smith-2020", "10.1000/a")
    assert _resolve_slug_collision("smith-2020", "10.1000/b") == "smith-2020-1"


def test_an_unused_slug_is_returned_unchanged(corpus_dir):
    """Catches: suffixing unconditionally, which would make every
    import `-1`."""
    assert _resolve_slug_collision("nobody-1999", "10.1000/a") == "nobody-1999"


# ---------- Jack's second question ----------

def test_a_gap_in_the_numbering_is_filled_not_skipped(corpus_dir):
    """Catches: counting past an existing suffix instead of finding the
    first free one.

    Jack's case: `-2` exists with no `-1`. The corpus already contains
    slugs like this (`pan-2025-1` with no `-2`), and 56 of the 1108
    queued imports carry a suffix. `-1` is free, so `-1` is correct —
    Corpus attaches no meaning to the number, so a gap is just a gap."""
    _put(corpus_dir, "smith-2020", "10.1000/a")
    _put(corpus_dir, "smith-2020-2", "10.1000/c")
    assert _resolve_slug_collision("smith-2020", "10.1000/d") == "smith-2020-1"


def test_suffixes_keep_climbing_when_every_number_is_taken(corpus_dir):
    """Catches: returning an occupied slug once the low numbers are
    used. Three genuinely different papers by one author in one year is
    unusual but not rare."""
    _put(corpus_dir, "smith-2020", "10.1000/a")
    _put(corpus_dir, "smith-2020-1", "10.1000/b")
    _put(corpus_dir, "smith-2020-2", "10.1000/c")
    assert _resolve_slug_collision("smith-2020", "10.1000/d") == "smith-2020-3"


def test_an_unreadable_existing_summary_is_treated_as_different(corpus_dir):
    """Catches: a parse failure being read as "same paper".

    A corrupt or hand-edited summary must never license an overwrite —
    that is the one outcome that loses data irreversibly."""
    (corpus_dir / "summaries" / "smith-2020.md").write_text(
        "this is not frontmatter", encoding="utf-8")
    assert _resolve_slug_collision("smith-2020", "10.1000/a") == "smith-2020-1"


# ---------- the fallback path ----------

def test_the_filename_fallback_also_resolves_collisions():
    """Catches: the `canon or temp_slug` branch skipping the resolver.

    When metadata is too thin for a canonical slug, the inbox FILENAME
    becomes the slug. That branch used to bypass
    `_resolve_slug_collision` entirely, so a filename matching an
    existing summary overwrote it. The filename is deliberately never
    an input to `canonical_slug_for`, but it is the last resort here,
    and a last resort still needs the guard.

    Source-level: the surrounding function runs a full PDF metadata
    extraction, which the suite must not do."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "python" / "extract_api.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    fn = body[body.index("def _process_inbox_pdf("):body.index("def scan(")]
    assert re.search(r"_resolve_slug_collision\(\s*canon or temp_slug", fn), (
        "the filename-fallback path must go through the collision resolver")
    assert not re.search(r"final_slug\s*=\s*canon or temp_slug\s*$", fn, re.M), (
        "the unguarded fallback assignment is back")


def test_a_stored_doi_in_url_form_is_recognised(corpus_dir):
    """Catches: normalising only the INCOMING doi, not the stored one.

    The mirror of the url-form test above, and it survived the first
    mutation run because every fixture wrote an already-clean DOI into
    the summary. Real summaries are written by several different
    sources — Crossref, OpenAlex, PDF /Info, a hand edit — and not all
    of them store the bare form. If only one side is normalised, a
    re-import of a paper whose stored DOI is a URL forks a duplicate."""
    (corpus_dir / "summaries" / "smith-2020.md").write_text(
        "---\ntitle: T\nyear: 2020\nauthor: A, B.\n"
        "doi: https://doi.org/10.1000/a\n---\n", encoding="utf-8")
    assert _resolve_slug_collision("smith-2020", "10.1000/a") == "smith-2020"


def test_an_undecodable_summary_never_licenses_an_overwrite(corpus_dir):
    """Catches: `except: return canon` on a read failure.

    The earlier corrupt-file test wrote plain text, which
    `parse_frontmatter` handles without raising — so the except branch
    was never exercised and a mutation that overwrote on failure
    survived. Invalid UTF-8 makes `read_text` actually throw.

    Failing open here means a file Corpus cannot read gets silently
    replaced, which is the one outcome with no recovery."""
    p = corpus_dir / "summaries" / "smith-2020.md"
    p.write_bytes(b"---\ntitle: \xff\xfe bad bytes\ndoi: 10.1000/a\n---\n")
    with pytest.raises(UnicodeDecodeError):
        p.read_text(encoding="utf-8")      # fixture check: it really throws
    assert _resolve_slug_collision("smith-2020", "10.1000/a") == "smith-2020-1"
