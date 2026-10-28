"""Fold PDF-read references into the API-derived reference list.

## The rule: PDF is additive, never authoritative

Crossref and Semantic Scholar are deposited metadata — a publisher
asserting what a paper cites. The PDF is the printed page. When they
disagree the API wins, because the API value is what the rest of Corpus
(DOIs, links, provenance badges) is keyed on.

So this module only ever does two things:

  1. **Fills holes.** A Crossref reference carrying a DOI and nothing
     else gets its author/title from the PDF entry with the same DOI.
     726 of 2929 reference lines in the reference corpus were bare DOIs
     (2026-08-25) — unreadable in the UI until filled.
  2. **Appends.** A PDF reference matching no API reference is added at
     the end, marked `pdf`, never merged into an API entry.

It never overwrites a non-empty API field, and never deletes an API
reference the PDF happened to miss.

## Why merged at read time rather than written into the summary

Same reason citation links are derived (see `citations.py`): the merge
depends on both sides, and rewriting the stored reference list would
destroy the distinction between "Crossref said this" and "we read this
off the page". Provenance is the whole point of the badges.

## Matching

DOI when both sides have one. Otherwise first-author surname + year,
which is enough to align two renderings of the SAME reference list —
a far weaker claim than identifying an arbitrary paper, since both
lists describe the same page.
"""
from __future__ import annotations

import re

from _api_http import normalize_doi

# Author+year alignment is only safe because both lists describe one
# paper's bibliography. Two DIFFERENT works by one author in one year
# are disambiguated by Crossref's "2019a"/"2019b" suffixes, which this
# ignores — the cost is picking the wrong one of a pair, which affects
# a displayed title, not a link.
_SURNAME = re.compile(r"[A-Za-z'’\-]{2,}")


def _key(surname: str, year) -> tuple:
    return ((surname or "").lower(), year)


def build_pdf_lookup(pdf_refs) -> tuple[dict, dict]:
    """Index PDF references by DOI and by (surname, year)."""
    by_doi: dict[str, dict] = {}
    by_ay: dict[tuple, dict] = {}
    for r in pdf_refs or []:
        doi = normalize_doi(r.get("doi"))
        if doi and doi not in by_doi:
            by_doi[doi] = r
        k = _key(r.get("author"), r.get("year"))
        if k[0] and k[1] and k not in by_ay:
            by_ay[k] = r
    return by_doi, by_ay


def enrich(api_ref: dict, by_doi: dict, by_ay: dict) -> dict:
    """Fill blank fields on ONE API reference from its PDF counterpart.

    Returns the reference with `text` filled in where it was empty and
    `sources` extended with "pdf". Never replaces existing text — a
    Crossref-supplied title outranks one parsed off a page."""
    ref = dict(api_ref)
    ref.setdefault("sources", [])
    doi = normalize_doi(ref.get("doi"))
    match = by_doi.get(doi) if doi else None
    if match is None:
        # No DOI to join on (or the PDF entry printed none). Fall back to
        # author+year, which is safe within a single bibliography.
        m = re.match(r"\s*([A-Za-z'’\-]{2,})", str(ref.get("text") or ""))
        yr = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(ref.get("text") or ""))
        if m and yr:
            match = by_ay.get(_key(m.group(1), int(yr.group(1))))
    if match is None:
        return ref

    if "pdf" not in ref["sources"]:
        ref["sources"] = list(ref["sources"]) + ["pdf"]
    # Only fill what is actually missing.
    if not (ref.get("text") or "").strip():
        parts = [p for p in (match.get("author"),
                             str(match.get("year")) if match.get("year") else "",
                             match.get("title")) if p]
        ref["text"] = " ".join(parts).strip()
    if not normalize_doi(ref.get("doi")) and normalize_doi(match.get("doi")):
        # The PDF printed a DOI the API never deposited. This is new
        # information, not a contradiction.
        ref["doi"] = normalize_doi(match.get("doi"))
        ref["doi_from_pdf"] = True
    return ref


def pdf_only(pdf_refs, api_refs) -> list[dict]:
    """PDF references that no API reference accounts for.

    Appended to the list rather than merged, so the user can always see
    which entries exist only because the page was read."""
    seen_doi = {normalize_doi(r.get("doi")) for r in api_refs if normalize_doi(r.get("doi"))}
    seen_ay = set()
    for r in api_refs:
        m = re.match(r"\s*([A-Za-z'’\-]{2,})", str(r.get("text") or ""))
        yr = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(r.get("text") or ""))
        if m and yr:
            seen_ay.add(_key(m.group(1), int(yr.group(1))))
    out = []
    for r in pdf_refs or []:
        doi = normalize_doi(r.get("doi"))
        if doi and doi in seen_doi:
            continue
        k = _key(r.get("author"), r.get("year"))
        if k[0] and k[1] and k in seen_ay:
            continue
        parts = [p for p in (r.get("author"),
                             str(r.get("year")) if r.get("year") else "",
                             r.get("title")) if p]
        text = " ".join(parts).strip()
        if not text:
            continue
        out.append({
            "text": text,
            "doi": doi,
            "kind": "",
            "extracted": False,
            "linked_slug": None,
            "sources": ["pdf"],
            "pdf_only": True,
        })
    return out


# ---------- Disk cache ----------
#
# Extraction costs ~176ms (median, 57-paper corpus), which is enough to
# be felt on every paper view. The cache turns repeat views into a file
# read. It is keyed on the PDF's mtime+size so replacing the PDF
# invalidates it automatically.

import json                                    # noqa: E402
import logging                                 # noqa: E402
from pathlib import Path                       # noqa: E402

logger = logging.getLogger("corpus.pdf_refs")

CACHE_VERSION = 1


def _stamp(pdf: Path) -> str:
    st = pdf.stat()
    return f"{CACHE_VERSION}:{int(st.st_mtime)}:{st.st_size}"


def load_or_extract(slug: str, pdf: Path, cache_dir: Path) -> tuple[list, str]:
    """(refs, status) for a paper, using the on-disk cache when valid.

    A cache MISS extracts and writes. A cache HIT with a stale stamp
    re-extracts. Any cache error falls through to a live extract —
    a corrupt cache file must never break the paper view."""
    if not pdf.exists():
        return [], "no_pdf"
    cache = Path(cache_dir) / f"{slug}.json"
    try:
        stamp = _stamp(pdf)
    except OSError:
        return [], "no_pdf"
    try:
        if cache.exists():
            blob = json.loads(cache.read_text(encoding="utf-8"))
            if blob.get("stamp") == stamp:
                return blob.get("refs") or [], blob.get("status") or "ok"
    except Exception:
        logger.info("pdf_refs_cache_unreadable slug=%s", slug, exc_info=True)

    from extract_references_pdf import extract_references_from_pdf
    refs, status = extract_references_from_pdf(pdf)
    try:
        cache.write_text(json.dumps(
            {"stamp": stamp, "status": status, "refs": refs},
            ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.info("pdf_refs_cache_write_failed slug=%s", slug, exc_info=True)
    logger.info("pdf_refs_extracted slug=%s status=%s count=%d",
                slug, status, len(refs))
    return refs, status
