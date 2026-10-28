"""Stored citers — every known work citing a paper, from OpenAlex.

WHAT IS STORED
--------------
`<corpus>/citers/<slug>.json`, one per paper. Fetched three ways, all
through `fetch_and_store`: the info panel's button (one paper), every
import (the papers it just added), and
`backfill()` over the whole corpus. The corpus-wide run was ~3,000
OpenAlex requests at 742 papers, PRISMA alone ~530, which is why the
import only fetches what it added.

Rows are compact arrays under a declared `fields` list rather than one
object per citer. At ~105k rows for the largest paper, repeating four
key names per row would roughly double the file for nothing.

WHAT IS NOT STORED
------------------
Whether a citer is in the corpus. That is computed at read time from the
citation index's DOI map, because it changes every time a paper is
imported — a stored flag would be wrong the day after it was written.

NOT USED BY THE BRIDGE SEARCH (yet). `bridges_api` still fetches its own
capped citer ids. Pointing it at this store is the planned next step.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from _api_http import normalize_doi
from _paths import citers_dir

logger = logging.getLogger("corpus.citers")

CITERS_VERSION = 1
FIELDS = ["openalex_id", "doi", "year", "title"]
# The progress phase every citer fetch reports under. Imported by
# extract_api (the import sequence) and citers_api (the corpus backfill):
# the step counter matches phases by exact name, so a second spelling
# would silently show "step 0".
PHASE = "Fetching citers"

# Parsed files, keyed by path, validated on (mtime_ns, size) — the same
# rule as the summary cache. PRISMA's file is several MB; re-parsing it on
# every paper click would cost more than the rest of the panel together.
_CACHE: dict[str, tuple[int, int, dict]] = {}


def citers_path(slug: str) -> Path:
    return citers_dir() / f"{slug}.json"


def read_citers(slug: str) -> dict | None:
    """The stored payload, or None if never fetched / unreadable / old."""
    p = citers_path(slug)
    try:
        st = p.stat()
    except OSError:
        return None
    hit = _CACHE.get(str(p))
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("citers_unreadable slug=%s", slug, exc_info=True)
        return None
    if not isinstance(data, dict) or data.get("version") != CITERS_VERSION:
        return None
    _CACHE[str(p)] = (st.st_mtime_ns, st.st_size, data)
    return data


def _complete_ids(data: dict | None) -> list[str] | None:
    """Citing OpenAlex ids from one stored payload, or None if unusable.

    A PARTIAL store counts as unusable: an interrupted fetch holds some
    of the citers, and a bridge search that treated it as the whole list
    would quietly report fewer connections rather than admit it was
    short."""
    if not isinstance(data, dict) or data.get("version") != CITERS_VERSION:
        return None
    if not data.get("complete"):
        return None
    fields = data.get("fields") or []
    if "openalex_id" not in fields:
        return None
    i = fields.index("openalex_id")
    return sorted({r[i] for r in (data.get("rows") or []) if len(r) > i and r[i]})


# Derived index of citing ids, one file for the whole corpus:
# {"version": n, "papers": {slug: [mtime_ns, size, [ids...]]}}.
#
# Observed 2026-09-24: even with most citers stored, the bridge search
# looped through them. It parsed every paper's full store (ids, DOIs, years, titles) on every
# run, ~0.6s a paper measured on the live import, ~10 minutes at 1,038
# papers, to rebuild an answer that had changed for a handful of them.
#
# A cache, not a second source of truth: an entry is only trusted while
# the store file still has the mtime and size it was read at, so a
# refetched store is re-read automatically. Only COMPLETE stores are
# indexed, so a partial one keeps falling through to a network fetch.
IDS_INDEX_VERSION = 1


def citer_ids_for(slugs, index_path: Path,
                  on_read=None) -> tuple[dict[str, set[str]], int]:
    """Citing ids for every paper in `slugs` with a complete store.

    Returns `(slug -> ids, stores_read)`. Papers missing from the result
    have nothing usable stored and must be fetched. Only stores whose
    file changed since the last call are parsed; the rest cost a stat.

    `on_read(done, total, slug)` fires per store actually parsed, so a
    progress display counts real work — not a walk over 1,000 papers
    that were already known.
    """
    try:
        old = json.loads(index_path.read_text(encoding="utf-8"))
        if old.get("version") != IDS_INDEX_VERSION:
            old = {}
    except Exception:
        old = {}
    known = old.get("papers") or {}

    fresh: dict[str, list] = {}
    to_read: list[tuple[str, list]] = []
    for slug in slugs:
        try:
            st = citers_path(slug).stat()
        except OSError:
            continue                                   # never fetched
        key = [st.st_mtime_ns, st.st_size]
        hit = known.get(slug)
        if hit and hit[:2] == key:
            fresh[slug] = hit
        else:
            to_read.append((slug, key))

    for i, (slug, key) in enumerate(to_read, 1):
        if on_read:
            on_read(i, len(to_read), slug)
        try:
            # Parsed directly, NOT through read_citers: that caches the
            # whole payload in memory, and holding every paper's titles
            # for the life of the server is ~100MB spent on nothing.
            data = json.loads(citers_path(slug).read_text(encoding="utf-8"))
        except Exception:
            logger.warning("citers_unreadable slug=%s", slug, exc_info=True)
            continue
        ids = _complete_ids(data)
        if ids is not None:
            fresh[slug] = key + [ids]

    if to_read or set(known) != set(fresh):
        index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"version": IDS_INDEX_VERSION, "papers": fresh}),
                       encoding="utf-8")
        os.replace(tmp, index_path)
    return {slug: set(v[2]) for slug, v in fresh.items()}, len(to_read)


def _stored_for(slug: str, doi: str) -> bool:
    """True if a citer list is stored for `slug` AND was fetched for
    `doi` — the paper's DOI now.

    A store follows its slug through a rename, but a re-extract can also
    change the DOI, and then the stored citers belong to a different
    work. Taatgen 2013 (2026-09-25) had first resolved to its APA
    supplement; after the fix its store still held the supplement's
    citers, and existence alone read as "done". An unreadable store
    counts as not stored, so it is fetched again rather than trusted."""
    if not citers_path(slug).exists():
        return False
    data = read_citers(slug)
    return bool(data) and normalize_doi(data.get("doi")) == normalize_doi(doi)


def write_citers(slug: str, payload: dict) -> Path:
    """Atomic write: a crash mid-write must not leave half a JSON file
    that then reads as "never fetched" (or worse, fails to parse)."""
    p = citers_path(slug)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)
    _CACHE.pop(str(p), None)
    return p


def row_from_work(w: dict) -> list:
    """OpenAlex work -> one stored row, in FIELDS order."""
    from openalex_client import oa_short_id
    return [
        oa_short_id(w.get("id")),
        normalize_doi(w.get("doi")) or "",
        w.get("publication_year"),
        (w.get("display_name") or w.get("title") or "").strip(),
    ]


def split_by_corpus(rows: list, doi_to_slugs: dict, self_slug: str) -> tuple[list, list]:
    """(in_corpus, elsewhere). In-corpus rows gain the matching slug.

    DOI-matched, through the same normalised DOI map the references and
    the citation index use, so "in corpus" means the same thing in every
    panel. The paper itself is dropped if OpenAlex lists it as its own
    citer (it happens with preprint/published pairs).
    """
    doi_i = FIELDS.index("doi")
    inside, outside = [], []
    for r in rows:
        doi = r[doi_i] if len(r) > doi_i else ""
        slugs = [s for s in doi_to_slugs.get(doi, []) if s != self_slug] if doi else []
        if doi and doi_to_slugs.get(doi) and not slugs:
            continue                          # it is this paper
        if slugs:
            inside.append({"row": r, "slug": slugs[0]})
        else:
            outside.append(r)
    return inside, outside


def fetch_and_store(slug: str, doi: str, on_progress=None,
                    resolved: tuple | None = None) -> dict:
    """Resolve the paper on OpenAlex, page through every citer, store.

    `on_progress(done, total)` is called per page. Always writes a file
    when the paper resolves — a partial list is stored with
    `complete: false` so the panel can say it is partial.

    `resolved=(openalex_id, cited_by_count)` skips the lookup; `backfill`
    passes it after resolving 50 papers per request.
    """
    from openalex_client import (CiterFetchError, oa_short_id,
                                 openalex_citer_pages, openalex_works_by)

    ndoi = normalize_doi(doi)
    if not ndoi:
        raise ValueError("no_doi")
    if resolved:
        wid, reported = resolved
    else:
        works, failed = openalex_works_by("doi", [ndoi], "id,cited_by_count")
        if not works:
            raise LookupError("lookup_failed" if failed else "not_in_openalex")
        wid = oa_short_id(works[0].get("id"))
        reported = works[0].get("cited_by_count")

    rows: list = []
    seen: set = set()
    complete = True
    t0 = time.monotonic()
    try:
        for results, meta in openalex_citer_pages(wid):
            for w in results:
                r = row_from_work(w)
                if r[0] and r[0] not in seen:
                    seen.add(r[0])
                    rows.append(r)
            if on_progress:
                on_progress(len(rows), meta.get("count") or reported or 0)
    except CiterFetchError:
        complete = False
        logger.warning("citers_partial slug=%s stored=%d", slug, len(rows))

    payload = {
        "version": CITERS_VERSION,
        "slug": slug,
        "doi": ndoi,
        "openalex_id": wid,
        "source": "openalex",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reported_count": reported,
        "complete": complete,
        "fields": FIELDS,
        "rows": rows,
    }
    p = write_citers(slug, payload)
    logger.info("citers_stored slug=%s rows=%d reported=%s complete=%s bytes=%d elapsed=%.1f",
                slug, len(rows), reported, complete, p.stat().st_size,
                time.monotonic() - t0)
    return payload


def backfill(slugs: list[str] | None = None, on_step=None, force: bool = False) -> dict:
    """Fetch citers for many papers. Skips any already stored.

    Used for the corpus-wide fetch and for the post-import fetch.
    Both go through here: `slugs=None` means the whole corpus; the import
    passes just the papers it added.

    Lookups are batched — 50 DOIs per OpenAlex request — so a 742-paper
    backfill spends ~15 requests resolving instead of 742. Idempotent and
    resumable: a stored file (even a partial one) is skipped unless
    `force`, so an interrupted run picks up where it stopped. One paper
    failing never stops the rest.

    `on_step(phase, detail, done, total)` reports into whatever progress
    job the caller owns. Returns counts for the log and for tests.
    """
    from _api_common import _walk_summaries
    from openalex_client import oa_short_id, openalex_works_by

    wanted = set(slugs) if slugs is not None else None
    todo: list[tuple[str, str]] = []           # (slug, normalised doi)
    counts = {"stored": 0, "skipped": 0, "no_doi": 0, "not_found": 0,
              "failed": 0, "lookup_failed": 0}
    for slug, fm, _body in _walk_summaries():
        if wanted is not None and slug not in wanted:
            continue
        d = normalize_doi(fm.get("doi"))
        if not d:
            counts["no_doi"] += 1
            continue
        if not force and _stored_for(slug, d):
            counts["skipped"] += 1
            continue
        todo.append((slug, d))

    if on_step:
        on_step(PHASE, f"resolving {len(todo)} papers", 0, len(todo))
    works, lost = openalex_works_by("doi", [d for _, d in todo], "id,doi,cited_by_count")
    counts["lookup_failed"] = lost
    by_doi = {normalize_doi(w.get("doi")): (oa_short_id(w.get("id")), w.get("cited_by_count"))
              for w in works if w.get("id")}

    for i, (slug, d) in enumerate(todo, 1):
        if on_step:
            on_step(PHASE, f"citers of {slug}", i, len(todo))
        res = by_doi.get(d)
        if not res:
            counts["not_found"] += 1
            continue
        try:
            fetch_and_store(slug, d, resolved=res)
            counts["stored"] += 1
        except Exception:
            counts["failed"] += 1
            logger.warning("citers_backfill_failed slug=%s", slug, exc_info=True)

    logger.info("citers_backfill_done %s", " ".join(f"{k}={v}" for k, v in counts.items()))
    return counts
