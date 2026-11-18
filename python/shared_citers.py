"""Shared citers — works that cite two or more of the papers a note links.

EXPERIMENTAL. A note that links several papers is usually about one
question; a work citing several of them is likely about it too. This
finds those works from the stored citer lists (`citers.py`), which are
already on disk for every imported paper with a DOI.

Pure: no Flask, no file reads, and no network of its own. The route in
`citers_api` gathers the stored payloads and the citation index's DOI
map and hands them here, so "in corpus" means what it means in every
other panel. Citation counts are not in the stored rows; `add_counts`
takes the lookup as an argument, so only the rows shown are looked up.

A citer is identified by its OpenAlex id — the one key every stored row
has (a citer's DOI can be blank). It is left out when it is itself one
of the note's papers, matched by DOI or by the OpenAlex id the paper's
own store was fetched for.
"""
from __future__ import annotations

from citers import FIELDS

# Fewer than this many linked papers cannot share a citer.
MIN_PAPERS = 2

_ID, _DOI, _YEAR, _TITLE = (FIELDS.index(k) for k in ("openalex_id", "doi", "year", "title"))


def paper_status(payload: dict | None, has_doi: bool) -> str:
    """How usable one note paper's citer list is: "stored", "partial"
    (an interrupted fetch — fewer citers than exist), "not_fetched",
    or "no_doi" (a list can never be fetched)."""
    if payload is None:
        return "not_fetched" if has_doi else "no_doi"
    return "stored" if payload.get("complete") else "partial"


def shared_citers(payloads: dict[str, dict], doi_to_slugs: dict[str, list[str]]) -> list[dict]:
    """Every citer of two or more papers in `payloads` (slug -> stored
    citer payload), excluding the note's own papers.

    Each result: the citer's fields, `cites` (the note papers it cites,
    sorted), and `slug` (its corpus slug, or None when not in the
    corpus). Ordered by how many note papers it cites, then newest
    first, then title — so the most connected works come first and the
    order is stable between runs.
    """
    note_slugs = set(payloads)
    own_ids = {p.get("openalex_id") for p in payloads.values() if p.get("openalex_id")}
    rows: dict[str, list] = {}
    cites: dict[str, set[str]] = {}
    for slug, payload in payloads.items():
        for r in payload.get("rows") or []:
            if len(r) <= _TITLE or not r[_ID]:
                continue
            rows.setdefault(r[_ID], r)
            cites.setdefault(r[_ID], set()).add(slug)

    out = []
    for wid, cited in cites.items():
        if len(cited) < MIN_PAPERS or wid in own_ids:
            continue
        r = rows[wid]
        slugs = doi_to_slugs.get(r[_DOI], []) if r[_DOI] else []
        if note_slugs.intersection(slugs):
            continue                                   # it is one of the note's papers
        out.append({**dict(zip(FIELDS, r)), "cites": sorted(cited),
                    "slug": slugs[0] if slugs else None})
    out.sort(key=lambda c: (-len(c["cites"]), -(c["year"] or 0), c["title"] or ""))
    return out


def add_counts(found: list[dict], cache: dict[str, int | None], lookup) -> int:
    """Set `cited_by_count` on each of `found` (OpenAlex's count, the
    same source for every row, so they compare), looking up only ids not
    already in `cache`. `lookup(field, values, select)` is
    `openalex_client.openalex_works_by`. Returns how many ids the lookup
    lost; those stay out of the cache, so the next open retries them,
    and their rows get None rather than a wrong 0."""
    from openalex_client import oa_short_id
    want = sorted({c["openalex_id"] for c in found} - set(cache))
    failed = 0
    if want:
        works, failed = lookup("openalex", want, "id,cited_by_count")
        for w in works:
            cache[oa_short_id(w.get("id"))] = w.get("cited_by_count")
    for c in found:
        c["cited_by_count"] = cache.get(c["openalex_id"])
    return failed

