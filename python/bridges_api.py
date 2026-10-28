"""Corpus — /api/bridges blueprint. Added 2026-09-17.

Owns the network side of citation bridges: resolving the corpus to
OpenAlex, reading each paper's citers (from the per-paper store written
by `citers.py`, fetching only what is missing), and caching the result. The
graph logic itself is in `python/bridges.py` and touches neither Flask
nor the network.

ON DEMAND, NOT ON LOAD
----------------------
Computing bridges is ~70 OpenAlex requests and ~22s for a 56-paper
corpus (measured 2026-09-17). That is far too slow to sit in
`/api/paper/<slug>`, which is on the path of every click in the
sidebar, and it would make the whole app depend on a network round
trip. So it is a button: `POST /api/bridges/compute` does the work and
writes a cache, and everything else reads the cache.

`GET /api/bridges` therefore never touches the network and never
blocks. With no cache it returns `computed_at: null`, which the panel
renders as "not computed yet" rather than "no connections" — those mean
very different things, and conflating them is the bug this file is
written to avoid.

Wired in server.py via `app.register_blueprint(bridges_bp)`.
"""
from __future__ import annotations

import json
import logging
import time

from flask import Blueprint, jsonify

import progress

from _api_common import require_corpus_or_abort, _walk_summaries
from _api_http import normalize_doi
from _paths import bridges_dir
from bridges import (BRIDGE_CACHE_VERSION, Bridge, find_bridges,
                     bridges_for)
import citers as citers_store
from citations import _corpus_fingerprint, build_index
from openalex_client import (oa_short_id, openalex_citers_of,
                             openalex_works_by)

logger = logging.getLogger("corpus.bridges_api")

bridges_bp = Blueprint("bridges", __name__)

_CACHE_NAME = "index.json"
# Derived from the per-paper citer stores; see `citers.citer_ids_for`.
CITER_IDS_INDEX = "citer_ids.json"

# Metadata is fetched for the middle papers so the panel can show a
# title rather than an opaque "W2043...". Capped: a full corpus run can
# surface thousands of distinct middles, and each batch of 50 is a
# request.
MAX_MIDDLE_META = 400


def _cache_path():
    return bridges_dir() / _CACHE_NAME


def _read_cache() -> dict | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("bridge_cache_unreadable", exc_info=True)
        return None
    if not isinstance(data, dict) or data.get("version") != BRIDGE_CACHE_VERSION:
        # A cache written by an older shape is discarded rather than
        # partially trusted.
        return None
    return data


def _corpus_openalex_map() -> tuple[dict, dict, dict, int]:
    """(slug -> OpenAlex id, slug -> forward set, slug -> year, lookup_failures).

    One bulk request per 50 papers. Papers without a usable DOI cannot
    be resolved and are simply absent — they can have no bridges, the
    same way they can have no direct links (matching is DOI-based).

    `lookup_failures` counts papers lost to a failed request rather than
    to OpenAlex not having them. The two were conflated until
    2026-09-21, when a dropped chunk silently built a bridge graph on
    80% of the corpus.
    """
    by_doi: dict[str, str] = {}
    years: dict[str, int | None] = {}
    for slug, fm, _body in _walk_summaries():
        doi = normalize_doi(fm.get("doi"))
        if doi:
            by_doi[doi] = slug
        y = str(fm.get("year") or "").strip()
        years[slug] = int(y) if y.isdigit() else None

    works, lookup_failures = openalex_works_by(
        "doi", list(by_doi),
        "id,doi,publication_year,referenced_works")

    ids: dict[str, str] = {}
    forward: dict[str, set[str]] = {}
    for w in works:
        doi = normalize_doi(w.get("doi"))
        slug = by_doi.get(doi)
        if not slug:
            continue
        ids[slug] = oa_short_id(w.get("id"))
        forward[slug] = {oa_short_id(x) for x in (w.get("referenced_works") or [])}
        if years.get(slug) is None:
            years[slug] = w.get("publication_year")
    return ids, forward, years, lookup_failures


def _middle_meta(middle_ids: list[str]) -> dict:
    """Display fields for the connecting papers."""
    if not middle_ids:
        return {}
    works, _failed = openalex_works_by(
        "openalex", middle_ids[:MAX_MIDDLE_META],
        "id,title,publication_year,cited_by_count,doi")
    out = {}
    for w in works:
        out[oa_short_id(w.get("id"))] = {
            "title": (w.get("title") or "").strip() or "Untitled",
            "year": w.get("publication_year"),
            "cited_by": w.get("cited_by_count"),
            "doi": normalize_doi(w.get("doi")),
        }
    return out


@bridges_bp.route("/api/bridges", methods=["GET"])
def get_bridges():
    """Serve the cached result. Never hits the network."""
    require_corpus_or_abort()
    cache = _read_cache()
    if cache is None:
        return jsonify({"computed_at": None, "stale": False,
                        "bridges": [], "middles": {}, "totals": {}})
    cache = dict(cache)
    # `stale` is advisory: the corpus changed since this was computed,
    # so the answer may be incomplete. Deliberately NOT auto-recomputed
    # — that would put a 22s network call behind a page load.
    cache["stale"] = (cache.get("fingerprint") != list(_corpus_fingerprint()))
    return jsonify(cache)


# The phases a bridge search moves through, in order. Declared so the
# UI can say "step 2 of 4" before step 2 begins, and so the names come
# from one place rather than being retyped at each `progress.step`.
BRIDGE_PHASES = ["Resolving papers", "Gathering citers",
                 "Finding bridges", "Naming connecting papers"]


def compute_bridges_now(job: "progress.Job | None" = None) -> dict | None:
    """Run a full bridge search and cache the result.

    Returns the payload, or None when no paper could be resolved.

    Split out of the Flask view so the import pipeline can call it
    directly — `/api/scan` runs this after adding papers, and a view
    function is not callable from there without faking a request.

    `job` is the caller's progress handle when the caller (the import)
    already owns the slot and this should report into it. Passing None
    means "start your own"; if the slot is busy the search still runs,
    reporting nowhere, rather than writing into someone else's banner.
    """
    t0 = time.monotonic()
    own_job = job is None
    if own_job:
        job = progress.start("Finding bridges", BRIDGE_PHASES) or progress.NULL

    job.step(BRIDGE_PHASES[0], "reading summaries and matching to OpenAlex")
    ids, forward, years, lookup_failures = _corpus_openalex_map()
    if not ids:
        logger.warning("bridge_compute_no_papers")
        if own_job:
            job.finish("no paper could be resolved to OpenAlex")
        return None

    # Used to be the slow phase by far: one paginated request per paper,
    # every run. Since 2026-09-23 the per-paper citer store answers it
    # instead, and only papers with nothing stored cost a request —
    # after an import that is none of them, because the import fetches
    # citers for what it added before this runs.
    #
    # Jack: "can you cache the results so it doesnt need to redo this
    # stuff every time?" This was the redo: ~935 requests and ~16
    # minutes per import for data already on disk.
    #
    # The store is a snapshot, so a paper cited since its fetch is
    # missing until that paper's citers are refetched. Stated because it
    # is a real limit: bridges are as fresh as the citer store, and
    # "Fetch citers" (per paper) or Fetching citers for the corpus is
    # what refreshes them.
    # Pass 1: everything the citer store already answers, via an index
    # that only re-reads stores which changed since the last run (see
    # `citers.citer_ids_for`). Progress counts only the stores actually
    # read — Jack, 2026-09-24: "even tho it has most citers stored, it
    # still loops through them".
    stored, stores_read = citers_store.citer_ids_for(
        list(ids), bridges_dir() / CITER_IDS_INDEX,
        on_read=lambda i, n, slug: job.step(BRIDGE_PHASES[1], f"reading {slug}", i, n))
    backward: dict[str, set[str]] = {s: stored[s] for s in ids if s in stored}
    from_store = len(backward)

    # Pass 2: the network, only for papers with nothing complete stored.
    missing = [(s, w) for s, w in ids.items() if s not in stored]
    failed = 0
    for i, (slug, wid) in enumerate(missing, 1):
        job.step(BRIDGE_PHASES[1], f"fetching citations of {slug}", i, len(missing))
        citers = openalex_citers_of(wid)
        if citers is None:
            failed += 1
            continue
        backward[slug] = set(citers)

    job.step(BRIDGE_PHASES[2], "intersecting references with citations")
    index = build_index()
    direct = {(a, b) for a, targets in index.outgoing.items() for b in targets}

    found = find_bridges(forward, backward, direct=direct, years=years)
    rows = [b.as_dict() for b in found]

    seen: list[str] = []
    for b in rows:
        for m in b["middles"]:
            if m not in seen:
                seen.append(m)
    job.step(BRIDGE_PHASES[3], f"{len(seen)} connecting papers", 0, len(seen))
    meta = _middle_meta(seen)

    payload = {
        "version": BRIDGE_CACHE_VERSION,
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fingerprint": list(_corpus_fingerprint()),
        "bridges": rows,
        "middles": meta,
        "totals": {
            "papers_resolved": len(ids),
            # Split deliberately. "Unresolved" now means OpenAlex has no
            # record (or the paper has no DOI); "lookup_failures" means
            # the request failed and the answer is INCOMPLETE. Reporting
            # one number for both is how a 20%-short graph looked fine.
            "papers_unresolved": max(0, len(years) - len(ids) - lookup_failures),
            "lookup_failures": lookup_failures,
            "citers_failed": failed,
            # How much of the backward map came off disk vs the network.
            # A run that silently stopped using the store would show up
            # here as a slow run with citers_from_store: 0.
            "citers_from_store": from_store,
            # How many stores had to be parsed this run. After an import
            # this should be about the number of papers added; near the
            # corpus size means the index stopped working.
            "citer_stores_read": stores_read,
            "complete": lookup_failures == 0 and failed == 0,
            "direct_links": len(direct),
            "bridges": len(rows),
            "middles_named": len(meta),
            "elapsed_s": round(time.monotonic() - t0, 1),
        },
    }
    _cache_path().write_text(json.dumps(payload, indent=1), encoding="utf-8")
    if lookup_failures or failed:
        logger.warning("bridges_incomplete lookup_failures=%d citers_failed=%d",
                       lookup_failures, failed)
    logger.info("bridges_computed papers=%d bridges=%d failed=%d stored=%d read=%d elapsed=%.1f",
                len(ids), len(rows), failed, from_store, stores_read, time.monotonic() - t0)
    payload["stale"] = False
    if own_job:
        job.finish()
    return payload


@bridges_bp.route("/api/bridges/compute", methods=["POST"])
def compute_bridges():
    """Do the work: resolve the corpus, fetch citers, intersect, cache.

    Reports `papers_unresolved` and `citers_failed` rather than
    silently returning fewer bridges — a partial network failure and a
    genuinely sparse corpus look identical in the output otherwise.
    """
    require_corpus_or_abort()
    payload = compute_bridges_now()
    if payload is None:
        return jsonify({"error": "no_resolvable_papers",
                        "description": "No paper in this corpus could be "
                                       "resolved to OpenAlex. Papers need a "
                                       "DOI to be bridged."}), 400
    return jsonify(payload)


def bridges_for_slug(slug: str) -> dict:
    """Bridge rows touching one paper, for `/api/paper/<slug>`.

    Cache-only and failure-tolerant: a missing or unreadable cache
    yields `computed: False`, never an exception, because this is
    called on the hot path of every paper click.
    """
    try:
        cache = _read_cache()
    except Exception:
        return {"computed": False, "rows": [], "middles": {}}
    if not cache:
        return {"computed": False, "rows": [], "middles": {}}
    rows = bridges_for(slug, cache.get("bridges") or [])
    used = {m for r in rows for m in (r.get("middles") or [])}
    middles = {k: v for k, v in (cache.get("middles") or {}).items() if k in used}
    return {"computed": True, "computed_at": cache.get("computed_at"),
            "rows": rows, "middles": middles}
