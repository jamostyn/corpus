"""Carry everything keyed by a paper's slug across a rename.

WHY THIS EXISTS
---------------
2026-09-21, 16:18:46: Jack pressed Re-extract on `pan-2025-1`, his main
working paper. The resolved metadata said its canonical slug was
`pan-2025`, so `re_extract` moved the PDF and the summary — and nothing
else. Five other stores key a paper by its slug, and all of them were
left pointing at a name that no longer existed:

    highlights/<slug>.json      177 highlights, invisible
    citers/<slug>.json          stored citers (added 2026-09-22)
    pdf_refs/<slug>.json        cached reference list, orphaned
    projects/*.json             project membership, silently dropped
    notes/*.json                every `data-open-paper` link, now a 404
    bridges/index.json          cached bridge rows (self-heals on recompute)

The first sign was "none of the pdfs are loading here" from the note
workspace — the note's paper links all resolved to a missing slug.

A rename that moves the file but not its dependents is not a rename. This
module is the ONE list of what a slug owns, so the next store added gets
added here rather than rediscovered through another lost afternoon.

Nothing here raises on a missing store: a paper with no highlights and
no projects is the common case, and a half-finished migration is worse
than a slow one. Every step logs what it moved.
"""
from __future__ import annotations

import json
import logging
import re

from _paths import citers_dir, highlights_dir, notes_dir, pdf_refs_dir, projects_dir

logger = logging.getLogger("corpus.slug_migration")


def _note_link_re(slug: str) -> re.Pattern:
    """`data-open-paper` pointing at exactly this slug.

    Anchored on the closing quote so renaming `pan-2025` never touches a
    link to `pan-2025-1` — the exact pair that prompted this module.
    """
    return re.compile(r'(data-open-paper=)(["\'])' + re.escape(slug) + r"\2")


def migrate_paper_slug(old: str, new: str) -> dict:
    """Re-key every slug-owned store from `old` to `new`.

    The PDF and summary are the CALLER's job — they are renamed as part
    of extraction. This handles everything else. Returns counts, for the
    log and for tests.
    """
    counts = {"highlights": 0, "citers": 0, "pdf_refs": 0, "projects": 0, "notes": 0}
    if not old or not new or old == new:
        return counts

    # Highlights: move. Refuse to overwrite — if `new` already has
    # highlights, two papers' annotations would be merged or one lost.
    src = highlights_dir() / f"{old}.json"
    dst = highlights_dir() / f"{new}.json"
    if src.exists():
        if dst.exists():
            logger.warning("slug_migrate_highlights_conflict old=%s new=%s", old, new)
        else:
            src.rename(dst)
            counts["highlights"] = 1

    # Stored citers: expensive to rebuild (PRISMA alone is ~530 OpenAlex
    # requests), so moved, never dropped. Same no-overwrite rule.
    csrc = citers_dir() / f"{old}.json"
    cdst = citers_dir() / f"{new}.json"
    if csrc.exists():
        if cdst.exists():
            logger.warning("slug_migrate_citers_conflict old=%s new=%s", old, new)
        else:
            csrc.rename(cdst)
            counts["citers"] = 1

    # PDF references: a derived cache, regenerated on next open. Dropping
    # the old one is enough; moving it risks keeping a stale extraction.
    ref = pdf_refs_dir() / f"{old}.json"
    if ref.exists():
        ref.unlink()
        counts["pdf_refs"] = 1

    # Project membership lives on the project, so every project is read.
    for p in projects_dir().glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        papers = (data.get("members") or {}).get("paper")
        if not papers or old not in papers:
            continue
        data["members"]["paper"] = [new if x == old else x for x in papers
                                    if not (x == new and old in papers)]
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        counts["projects"] += 1

    # Note links.
    pat = _note_link_re(old)
    for p in notes_dir().glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        body = data.get("body_html") or ""
        new_body, n = pat.subn(lambda m: f"{m.group(1)}{m.group(2)}{new}{m.group(2)}", body)
        if n:
            data["body_html"] = new_body
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            counts["notes"] += 1

    logger.info("paper_slug_migrated old=%s new=%s highlights=%d pdf_refs=%d projects=%d notes=%d",
                old, new, counts["highlights"], counts["pdf_refs"],
                counts["projects"], counts["notes"])
    return counts


# A collision suffix is `-N` AFTER the four-digit year. A bare `-\d+$`
# also matches the year itself — `pan-2025` would strip to `pan` and
# compare unequal to `pan-2025-1`, which is exactly the rename this
# exists to prevent. (Same trap as the 2026-09-17 slug-collision probe.)
_SUFFIX = re.compile(r"(?<=-\d{4})-\d+$")


def differs_only_by_suffix(a: str, b: str) -> bool:
    """`pan-2025-1` vs `pan-2025`: the same paper under a collision suffix.

    Re-extract must not rename for this alone. The suffix records that a
    same-author-same-year paper existed at import time; dropping it later
    changes the paper's identity for a purely cosmetic reason, and it is
    how Jack's working paper was renamed out from under him.
    """
    return _SUFFIX.sub("", a) == _SUFFIX.sub("", b)
