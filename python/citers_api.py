"""/api/paper/<slug>/citers — read (cache-only) and fetch (on demand).

GET never touches the network: it serves the stored list, split into
in-corpus and elsewhere at read time, with the elsewhere half paged —
the largest paper has ~105k citers and the panel needs 50 at a time.

POST /fetch does the OpenAlex work under the shared progress channel, so
the banner shows it like any other long job.

GET /api/note/<id>/shared-citers (experimental) reads the stored lists of
every paper a note links and returns the works citing two or more of
them (`shared_citers.py`). The lists are read from disk; the one network
use is the citation counts of the rows sent, remembered per server run.

Wired in server.py via `app.register_blueprint(citers_bp)`.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

import logging
import time

import progress
from _api_common import _fm_dict, require_corpus_or_abort
from _paths import summaries_dir
from citations import build_index
from citers import FIELDS, fetch_and_store, read_citers, split_by_corpus
from notes_api import linked_paper_slugs, read_note
from shared_citers import add_counts, paper_status, shared_citers

citers_bp = Blueprint("citers", __name__)
logger = logging.getLogger("corpus.citers_api")

PAGE_DEFAULT = 50
PAGE_MAX = 500
# Shared citers outside the corpus sent per request. Two much-cited
# papers can share thousands; the in-corpus ones are always sent whole.
SHARED_PAGE_DEFAULT = 100
# OpenAlex citation counts of shared citers, by OpenAlex id, for the life
# of the server: reopening the dialog or paging back costs no requests.
_SHARED_COUNTS: dict = {}
CITER_PHASES = ["Resolving paper", "Fetching citers"]


def _row_dict(r: list) -> dict:
    return dict(zip(FIELDS, r))


def _summary_or_404(slug: str) -> dict:
    md = summaries_dir() / f"{slug}.md"
    if not md.exists():
        abort(404, description="paper_missing")
    return _fm_dict(md)


@citers_bp.route("/api/paper/<slug>/citers", methods=["GET"])
def get_citers(slug):
    require_corpus_or_abort()
    fm = _summary_or_404(slug)
    data = read_citers(slug)
    if data is None:
        # Frontmatter hands numbers back as strings ("3"); the panel does
        # arithmetic on this to warn about big fetches.
        raw = str(fm.get("citation_count") or "").strip()
        return jsonify({"status": "not_fetched",
                        "citation_count": int(raw) if raw.isdigit() else None})
    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = min(PAGE_MAX, max(1, int(request.args.get("limit", PAGE_DEFAULT))))
    except ValueError:
        abort(400, description="bad_paging")

    inside, outside = split_by_corpus(data.get("rows") or [],
                                      build_index().doi_to_slugs, slug)
    return jsonify({
        "status": "ok",
        "source": data.get("source"),
        "fetched_at": data.get("fetched_at"),
        "reported_count": data.get("reported_count"),
        "stored_count": len(data.get("rows") or []),
        "complete": bool(data.get("complete")),
        # In-corpus citers are always sent whole: they are the few that
        # matter most, and they are what the distinction is FOR.
        "in_corpus": [dict(_row_dict(x["row"]), slug=x["slug"]) for x in inside],
        "elsewhere": [_row_dict(r) for r in outside[offset:offset + limit]],
        "elsewhere_total": len(outside),
        "offset": offset,
    })


@citers_bp.route("/api/paper/<slug>/citers/fetch", methods=["POST"])
def fetch_citers(slug):
    require_corpus_or_abort()
    fm = _summary_or_404(slug)
    doi = str(fm.get("doi") or "").strip()
    if not doi or doi.lower() == "unknown":
        abort(400, description="no_doi")

    # The progress channel holds one job. Starting while an import or a
    # backfill is running used to be ignored, and this fetch then wrote
    # its steps INTO that job — the import's banner suddenly showing one
    # paper's citer pages. Refuse instead; the import fetches citers for
    # what it adds anyway.
    job = progress.start(f"Finding citers of {slug}", CITER_PHASES)
    if job is None:
        return jsonify({"error": "busy",
                        "description": "Another job is running — try again when it finishes."}), 409
    job.step(CITER_PHASES[0], "looking the paper up on OpenAlex")
    try:
        payload = fetch_and_store(
            slug, doi,
            on_progress=lambda done, total: job.step(
                CITER_PHASES[1], f"{done} of {total}", done, total))
    except ValueError:
        job.finish("no DOI")
        abort(400, description="no_doi")
    except LookupError as e:
        job.finish(str(e))
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        job.finish(f"{type(e).__name__}: {e}")
        raise
    job.finish()
    return jsonify({"status": "ok", "stored_count": len(payload["rows"]),
                    "complete": payload["complete"],
                    "reported_count": payload["reported_count"]})


@citers_bp.route("/api/citers/fetch-all", methods=["POST"])
def fetch_all_citers():
    """Fetch citers for every paper that has none stored. Returns at once.

    Roughly 3,000 OpenAlex requests at 742 papers, so it runs in
    a background thread under its own progress job, and is resumable —
    papers already stored are skipped, so an interrupted run continues.
    """
    import threading

    import citers

    require_corpus_or_abort()
    job = progress.start("Fetching citers for the corpus", [citers.PHASE])
    if job is None:
        return jsonify({"error": "busy",
                        "description": "Another job is running — try again when it finishes."}), 409

    def _run():
        try:
            counts = citers.backfill(None, on_step=job.step)
            job.finish()
            return counts
        except Exception as e:
            job.finish(f"{type(e).__name__}: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"}), 202


@citers_bp.route("/api/note/<nid>/shared-citers", methods=["GET"])
def note_shared_citers(nid):
    """Works citing two or more of the papers a note links, from the
    stored citer lists, each with its OpenAlex citation count (None when
    the lookup failed; `counts_failed` says how many). `papers` says which
    linked papers had a list to contribute, so a short answer can be
    told apart from a missing one."""
    require_corpus_or_abort()
    t0 = time.monotonic()
    note = read_note(nid)
    index = build_index()
    papers, payloads = [], {}
    for slug in linked_paper_slugs(note.get("body_html") or ""):
        md = summaries_dir() / f"{slug}.md"
        if not md.exists():
            continue                                  # a link to a removed paper
        fm = _fm_dict(md)
        doi = str(fm.get("doi") or "").strip()
        data = read_citers(slug)
        status = paper_status(data, bool(doi) and doi.lower() != "unknown")
        papers.append({"slug": slug, "title": fm.get("title") or slug, "status": status})
        if data is not None:
            payloads[slug] = data

    try:
        limit = min(PAGE_MAX, max(1, int(request.args.get("limit", SHARED_PAGE_DEFAULT))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        abort(400, description="bad_paging")
    found = shared_citers(payloads, index.doi_to_slugs)
    inside = [c for c in found if c["slug"]]
    outside = [c for c in found if not c["slug"]]
    page = outside[offset:offset + limit]
    # Only the rows sent are counted (~50 per OpenAlex request); the
    # in-corpus ones are cached after the first page, so paging is cheap.
    from openalex_client import openalex_works_by
    counts_failed = add_counts(inside + page, _SHARED_COUNTS, openalex_works_by)
    logger.info("shared_citers_found note=%s papers=%d with_lists=%d in_corpus=%d elsewhere=%d "
                "counts_failed=%d elapsed=%.2f", nid, len(papers), len(payloads), len(inside),
                len(outside), counts_failed, time.monotonic() - t0)
    return jsonify({
        "papers": papers,
        "in_corpus": inside,
        "elsewhere": page,
        "elsewhere_total": len(outside),
        "offset": offset,
        "counts_failed": counts_failed,
    })
