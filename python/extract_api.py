"""Corpus — PDF ingestion + re-extraction endpoints.
Split from server.py on 2026-08-15.

Owns:
  * /api/extract              — upload one or more PDFs, canonicalise
                                slugs, write summary MDs
  * /api/paper/<slug>/re-extract — re-run the extract pipeline on an
                                existing paper (and rename if the
                                resolved canonical slug now differs)
  * /api/scan                 — prefill any PDF in papers/ that
                                doesn't yet have a summary
  * `_resolve_slug_collision` — same-DOI overwrite vs -1/-2 suffix
  * `_kick_enrichment` +
    `_prefetch_enrichment_for_slug` — background OA-cache warming
                                after a fresh extract

Wired in server.py via `app.register_blueprint(extract_bp)`.
"""
from __future__ import annotations

import json
import logging
import threading
import time as _time
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from _api_common import require_corpus_or_abort
import progress

from _api_http import normalize_doi
from _paths import inbox_dir, papers_dir, summaries_dir
from slug_migration import differs_only_by_suffix, migrate_paper_slug

logger = logging.getLogger("corpus.extract_api")


extract_bp = Blueprint("extract", __name__)

# One import at a time. The progress channel holds one job, and two
# imports also race over the same inbox files.
_BUSY = {"error": "busy",
         "description": "An import is already running — try again when it finishes."}


# ---------- Slug collisions -----------------------------------------

def _resolve_slug_collision(canon: str, doi: str) -> str:
    """If summaries/<canon>.md exists with a DIFFERENT DOI, return
    <canon>-1 (or -2, etc.). If it's the same paper (same DOI), return
    canon and let the caller overwrite. If canon is unused, return it.

    Identity is decided by `normalize_doi`, the single source of truth
    the citation index and every matcher already use. This used to
    compare `.strip().lower()` on both sides, which was wrong three
    ways (all three verified by probe, 2026-09-17):

      * `doi: unknown` on both sides compared EQUAL, so two different
        papers with no DOI by the same first author in the same year
        resolved to the same slug and the second silently OVERWROTE the
        first — the PDF and the summary. `normalize_doi` maps "unknown"
        to "", which correctly reads as "no identity".
      * `https://doi.org/10.1000/a` and `10.1000/a` are the same paper
        but compared unequal, so re-importing produced a spurious
        `-1` duplicate instead of updating in place.
      * `10.1037//0096-3445.130.1.59` (a real double-slash DOI in this
        corpus) versus its single-slash form, same problem.

    The last two are how duplicate-DOI pairs get created, which is a
    known open issue.
    """
    from _fm import parse_frontmatter
    existing = summaries_dir() / f"{canon}.md"
    if not existing.exists():
        return canon
    want = normalize_doi(doi)
    try:
        fm, _ = parse_frontmatter(existing.read_text(encoding="utf-8"))
        have = normalize_doi(fm.get("doi"))
        if want and have and want == have:
            return canon  # same paper, safe to overwrite
    except Exception:
        pass
    for i in range(1, 100):
        cand = f"{canon}-{i}"
        if not (summaries_dir() / f"{cand}.md").exists():
            return cand
    return canon  # give up after 99 collisions (astronomically unlikely)


# ---------- Background enrichment prefetch --------------------------

def _prefetch_enrichment_for_slug(slug: str) -> None:
    """Walk a freshly-written summary's frontmatter, pick out every
    ORCID / ROR / ISSN it references, and warm the OA-enrichment cache
    for each entity that isn't already cached. Called in a background
    thread from /api/extract, /api/scan, and /api/paper/<slug>/re-extract
    so first-click on the corresponding author/institution/journal
    detail page is instant instead of blocking on an OA fetch.

    Silent on failure — enrichment is a nice-to-have, not a hard
    dependency. If OA is down, entities still load lazily on click.
    Throttled: OA polite pool is ~10 req/s and one paper can easily
    have 30+ entities.
    """
    try:
        from _fm import parse_frontmatter
        from oa_enrichment import (enrich_author_by_orcid,
                                    enrich_institution_by_ror,
                                    enrich_journal_by_issn)
        md = summaries_dir() / f"{slug}.md"
        if not md.exists():
            return
        fm, _ = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
        # Journal by ISSN (first ISSN wins — same rule as _aggregate_journals).
        issns = fm.get("issn") or []
        if isinstance(issns, str): issns = [issns]
        for i in issns[:1]:
            if str(i).strip():
                enrich_journal_by_issn(str(i).strip())
                _time.sleep(0.15)
                break
        # Authors + institutions from oa_authors JSON block.
        raw = fm.get("oa_authors") or []
        if isinstance(raw, str) and raw.strip().startswith("["):
            try: raw = json.loads(raw)
            except Exception: raw = []
        seen_orcid = set(); seen_ror = set()
        for a in raw if isinstance(raw, list) else []:
            orcid = (a.get("orcid") or "").strip() if isinstance(a, dict) else ""
            if orcid and orcid not in seen_orcid:
                seen_orcid.add(orcid)
                enrich_author_by_orcid(orcid)
                _time.sleep(0.15)
            for inst in (a.get("institutions") or []) if isinstance(a, dict) else []:
                if not isinstance(inst, dict): continue
                ror = (inst.get("ror") or "").strip()
                if ror and ror not in seen_ror:
                    seen_ror.add(ror)
                    enrich_institution_by_ror(ror)
                    _time.sleep(0.15)
    except Exception:
        # Background best-effort; UI still works via lazy load. Logged
        # so a persistent enrichment failure is at least visible during
        # dev instead of vanishing into the daemon thread.
        logger.warning("enrichment_prefetch_failed slug=%s", slug, exc_info=True)


def _kick_enrichment(slug: str) -> None:
    """Fire the enrichment prefetch in a daemon thread so /api/extract
    can return immediately. Daemon = dies with the server, no zombies."""
    t = threading.Thread(target=_prefetch_enrichment_for_slug,
                          args=(slug,), daemon=True)
    t.start()


def _process_inbox_pdf(source_pdf: Path, original_name: str | None = None) -> dict:
    """Process one PDF sitting in the inbox: extract metadata,
    canonicalize its slug, move it to `papers/<slug>.pdf`, render the
    summary MD, kick enrichment. Returns a status dict in the same
    shape /api/extract already returned.

    Shared by /api/extract (which drops the upload into inbox first)
    and /api/scan (which sweeps whatever's sitting in inbox from a
    manual drag). Any exception falls through as `status: failed` so
    a bad PDF doesn't tank the whole batch."""
    from prefill_summary import render_summary, canonical_slug_for
    from extract_metadata import extract_metadata

    name = original_name or source_pdf.name
    temp_slug = source_pdf.stem
    try:
        meta  = extract_metadata(source_pdf)
        canon = canonical_slug_for(meta)
        # Metadata too thin for a canonical slug (no year, or no
        # surname): fall back to the inbox filename. That path used to
        # SKIP collision resolution, so a filename matching an existing
        # summary would overwrite it. The filename is never an input to
        # `canonical_slug_for` by design, but it is the last resort
        # here, and a last resort still needs the same guard.
        final_slug = _resolve_slug_collision(canon or temp_slug,
                                             meta.get("doi") or "")

        final_pdf = papers_dir() / f"{final_slug}.pdf"
        if final_pdf.exists() and final_pdf.resolve() != source_pdf.resolve():
            # Collision — canonical PDF already lives in papers/ but the
            # inbox one is a different file. Don't clobber; report so
            # the user can inspect.
            logger.warning("inbox_collision src=%s target=%s", source_pdf, final_pdf)
            return {"filename": name, "status": "collision", "slug": final_slug}

        if source_pdf.resolve() != final_pdf.resolve():
            source_pdf.rename(final_pdf)

        target_md = summaries_dir() / f"{final_slug}.md"
        body = render_summary(final_slug, final_pdf,
                                existing_target=target_md, meta=meta)
        target_md.write_text(body, encoding="utf-8")
        _kick_enrichment(final_slug)
        logger.info("inbox_processed src=%s slug=%s", name, final_slug)
        return {
            "filename": name,
            "status":   "extracted",
            "slug":     final_slug,
            "renamed":  final_slug != temp_slug,
        }
    except Exception as e:
        logger.warning("inbox_process_failed src=%s", name, exc_info=True)
        return {
            "filename": name,
            "status":   "failed",
            "error":    f"{type(e).__name__}: {e}",
        }


# ---------- After an import -----------------------------------------

from citers import PHASE as CITERS_PHASE  # noqa: E402  (one definition)


def import_phases(reading: list[str]) -> list[str]:
    """The whole sequence an import shows: its own reading phases, then
    the post-import work. ONE definition for Scan and Add PDFs — they had
    two hand-built lists, which is how one gains a phase and the other
    silently does not."""
    from bridges_api import BRIDGE_PHASES
    return list(reading) + [CITERS_PHASE] + list(BRIDGE_PHASES)


def _after_import(slugs: list[str], job: "progress.Job | None" = None) -> None:
    """Fetch citers for the papers just added, then recompute bridges.

    Citers first: fetching on import is the default. Only the ADDED
    papers are fetched — the whole corpus is ~3,000 requests. Citers come
    before the bridge search because the bridge search is next in line to
    use them; today it does not.

    Both steps report into the import's own progress job. A citer fetch
    that fails does not stop the bridge search, and neither makes the
    import look failed — the papers are already on disk.

    Recompute citation bridges once a batch of papers has landed.

    ONCE PER BATCH, never per paper. A 25-paper scan that recomputed
    after each file would spend 25 x ~21s on an answer thrown away 24
    times; the whole point is that the bridge search is a whole-corpus
    operation.

    Runs in a background thread so the scan request returns as soon as
    the papers exist — the user gets their list immediately and the
    bridges fill in behind it. The thread keeps writing to the SAME
    progress job the scan started, so the UI shows one continuous
    sequence rather than appearing to finish and then start again.

    Added 2026-09-17. It was previously declined because a silent ~40s
    network call hanging off Add PDFs is a bad trade; visible progress
    removes that objection.
    """
    slugs = [s for s in (slugs or []) if s]
    if not slugs:
        return
    job = job or progress.NULL

    def _run():
        try:
            import citers
            citers.backfill(slugs, on_step=job.step)
        except Exception:
            logger.warning("auto_citers_failed", exc_info=True)
        try:
            from bridges_api import compute_bridges_now
            compute_bridges_now(job=job)
            job.finish()
        except Exception as e:
            logger.warning("auto_bridges_failed", exc_info=True)
            # Failing here must not look like the import failed — the
            # papers are already safely on disk.
            job.finish(f"bridge search failed: {type(e).__name__}")

    threading.Thread(target=_run, daemon=True).start()
    logger.info("auto_bridges_kicked added=%d", len(slugs))


# ---------- Endpoints -----------------------------------------------

@extract_bp.route("/api/extract", methods=["POST"])
def extract():
    """Accept one or more PDF uploads. Each upload:
      1. Gets saved into `<corpus>/inbox/` under its uploaded filename.
      2. Is then processed by `_process_inbox_pdf`, which extracts
         metadata, canonicalizes the slug, moves the PDF into
         `<corpus>/papers/<slug>.pdf`, and writes the summary MD.

    Routing everything through `inbox/` means `/api/scan` (which also
    walks the inbox) uses the exact same downstream pipeline, and
    users can drag-drop PDFs into `inbox/` from Finder without losing
    them if they forget to click Add PDFs afterward.

    Original filename is preserved in the response so the client can
    show 'X.pdf → renamed to Y' if the canonical differs."""
    require_corpus_or_abort()
    inbox_dir().mkdir(parents=True, exist_ok=True)

    results = []
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no_files"}), 400
    job = progress.start("Adding papers", import_phases(["Reading PDFs"]))
    if job is None:
        return jsonify(_BUSY), 409
    for i, f in enumerate(files, 1):
        name = Path(f.filename or "unknown.pdf").name
        job.step("Reading PDFs", name, i, len(files))
        inbox_pdf = inbox_dir() / name

        # Same-name check — prevents accidental re-adds from silently
        # overwriting an inbox PDF that's already queued. User can
        # rename or Re-extract the existing paper if that's what they
        # meant.
        if inbox_pdf.exists():
            results.append({"filename": name, "status": "exists"})
            continue
        f.save(str(inbox_pdf))
        results.append(_process_inbox_pdf(inbox_pdf, original_name=name))
    added_slugs = [r["slug"] for r in results if r.get("status") == "extracted" and r.get("slug")]
    added = sum(1 for r in results if r.get("status") == "extracted")
    if added:
        _after_import(added_slugs, job)
    else:
        job.finish()
    return jsonify({"results": results, "added": added})


@extract_bp.route("/api/paper/<slug>/re-extract", methods=["POST"])
def re_extract(slug):
    """Re-run the API-only extraction pipeline for one existing paper.
    Overwrites the summary MD, and — if the newly-resolved metadata now
    yields a canonical slug — RENAMES both the PDF and summary MD to
    match. Useful after the user adds a mailto/key in Settings, or when
    the paper's metadata resolved to `unknown` on first extract and
    might resolve now (e.g. after a title-search fallback improvement).

    Rename behaviour mirrors /api/extract: compute canonical slug from
    the resolved metadata; if it differs from the current slug AND the
    target isn't taken by a different paper, rename in place. Returns
    `slug` = the CURRENT (possibly renamed) slug so the client updates
    its selection accordingly."""
    require_corpus_or_abort()
    pdf = papers_dir() / f"{slug}.pdf"
    if not pdf.exists():
        abort(404, description="pdf_missing")
    from prefill_summary import render_summary, canonical_slug_for
    from extract_metadata import extract_metadata

    # Pre-extract metadata so we can compute the canonical slug BEFORE
    # writing the summary — same order /api/extract uses.
    meta = extract_metadata(pdf)
    canon = canonical_slug_for(meta)
    final_slug = slug
    renamed = False
    # Never rename for a collision suffix alone (`pan-2025-1` → `pan-2025`).
    # That is how a paper was wrongly renamed on 2026-09-21 — see
    # slug_migration.differs_only_by_suffix for why the suffix stays.
    if canon and canon != slug and not differs_only_by_suffix(canon, slug):
        candidate = _resolve_slug_collision(canon, meta.get("doi") or "")
        final_pdf = papers_dir() / f"{candidate}.pdf"
        final_md  = summaries_dir() / f"{candidate}.md"
        # Only rename if both target names are free. If the collision
        # resolver handed us back the SAME slug we're already at (because
        # existing summary has the same DOI), skip the rename — we're
        # already correctly canonical, just re-write in place.
        if candidate != slug and not final_pdf.exists() and not final_md.exists():
            pdf.rename(final_pdf)
            old_md = summaries_dir() / f"{slug}.md"
            if old_md.exists():
                old_md.unlink()
            pdf = final_pdf
            final_slug = candidate
            renamed = True
            # The PDF and summary are only two of the stores keyed by slug.
            # Highlights, cached refs, project membership and note links
            # move with them, or the paper loses all of them silently.
            migrate_paper_slug(slug, final_slug)

    target = summaries_dir() / f"{final_slug}.md"
    body = render_summary(final_slug, pdf, existing_target=target, meta=meta)
    target.write_text(body, encoding="utf-8")
    # Re-extract may have introduced new authors/institutions (e.g. if
    # the resolved DOI changed) — warm their enrichment cache too.
    _kick_enrichment(final_slug)
    return jsonify({"ok": True, "slug": final_slug, "renamed": renamed,
                    "previous_slug": slug if renamed else None})


@extract_bp.route("/api/scan", methods=["POST"])
def scan():
    """Two-pass sweep:
      1. Process every PDF sitting in `<corpus>/inbox/` — Finder-drops
         and manual copies land there. Same pipeline as /api/extract.
      2. Backfill: any PDF already in `<corpus>/papers/` that lacks a
         summary MD gets prefilled. Catches legacy PDFs that predate
         the inbox convention plus anything the user hand-dropped
         directly into papers/.
    """
    require_corpus_or_abort()
    from prefill_summary import render_summary

    inbox_dir().mkdir(parents=True, exist_ok=True)
    queued = sorted(inbox_dir().glob("*.pdf"))
    # The post-import phases are appended to the scan's own so the UI can
    # show the whole sequence up front — "step 2 of 7", not a scan that
    # finishes and then a surprise second job.
    job = progress.start("Importing papers",
                         import_phases(["Reading PDFs", "Backfilling summaries"]))
    if job is None:
        # 2026-09-22: a second Scan landing during an import made
        # the total alternate between the two inbox counts (100 and 98).
        # Both scans also raced over the same files. One at a time.
        return jsonify(_BUSY), 409

    # Pass 1 — process inbox drops.
    inbox_processed = []
    for i, pdf in enumerate(queued, 1):
        job.step("Reading PDFs", pdf.name, i, len(queued))
        inbox_processed.append(_process_inbox_pdf(pdf))

    # Pass 2 — backfill any papers/ PDF without a summary.
    pending = [p for p in sorted(papers_dir().glob("*.pdf"))
               if not (summaries_dir() / f"{p.stem}.md").exists()]
    new_slugs, skipped = [], 0
    skipped = sum(1 for _ in papers_dir().glob("*.pdf")) - len(pending)
    for i, pdf in enumerate(pending, 1):
        job.step("Backfilling summaries", pdf.stem, i, len(pending))
        try:
            body = render_summary(pdf.stem, pdf)
            md = summaries_dir() / f"{pdf.stem}.md"
            md.write_text(body, encoding="utf-8")
            new_slugs.append(pdf.stem)
            _kick_enrichment(pdf.stem)
        except Exception:
            logger.warning("scan_prefill_failed slug=%s", pdf.stem, exc_info=True)
    added = sum(1 for r in inbox_processed if r.get("status") == "extracted") + len(new_slugs)
    # Hands the progress job over to the bridge search, which keeps
    # reporting into it. When nothing was added there is no job to hand
    # over, so close it here.
    if added:
        _after_import([r["slug"] for r in inbox_processed
                       if r.get("status") == "extracted" and r.get("slug")] + new_slugs,
                      job)
    else:
        job.finish()
    return jsonify({
        "inbox_processed": inbox_processed,
        "extracted":       new_slugs,
        "skipped":         skipped,
        "added":           added,
    })
