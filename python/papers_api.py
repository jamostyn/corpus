"""Corpus — /api/papers, /api/paper/<slug>, /pdf/<slug>, highlights,
reveal-in-Finder blueprint.

Extracted from server.py on 2026-08-16 (Wave-3 blueprint split).

Owns:
  * `_paper_row` — sidebar-row shape for /api/papers.
  * `_paper_link_keys` — canonical deep-link keys attached to every
    /api/paper/<slug> response so the frontend never has to guess.
  * Six routes:
      GET /api/papers                        — sidebar list
      GET /api/paper/<slug>                  — full paper detail + link_keys
      GET /pdf/<slug>                        — serve the PDF file
      GET /api/paper/<slug>/highlights       — user highlights (JSON)
      POST /api/paper/<slug>/highlights      — replace highlights
      POST /api/paper/<slug>/reveal[/<kind>] — open OS file manager to the file

Uses the canonical key helpers from `entities_api` so paper-detail
deep-links point to the same keys the aggregators produce.

Wired in server.py via `app.register_blueprint(papers_bp)`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_from_directory

from _api_common import (
    _fm_dict,
    _parse_json_block,
    _read_summary,
    _strip_quotes,
    _walk_summaries,
    require_corpus_or_abort,
    summary_paths,
)
from _paths import highlights_dir, papers_dir, pdf_refs_dir, summaries_dir
from bridges_api import bridges_for_slug
from citations import build_index, normalize_doi, resolve_references
from citers import citers_path
from highlights_store import clean_highlights, load_highlights
from highlights_store import save_highlights as save_highlights_file
from pdf_refs_merge import load_or_extract
from entities_api import _author_key, _institution_key, _journal_key

logger = logging.getLogger("corpus.papers_api")

papers_bp = Blueprint("papers", __name__)


def _paper_row(md: Path) -> dict:
    fm = _fm_dict(md)
    return {
        "slug":      md.stem,
        "author":    fm.get("author") or "unknown",
        "year":      fm.get("year") or "unknown",
        "title":     fm.get("title") or "unknown",
        "doi":       fm.get("doi") or "unknown",
        "publisher": fm.get("publisher") or "unknown",
        "kind":      fm.get("kind") or "unknown",
        "status":    fm.get("status") or "unknown",
        # ISO timestamp string from prefill; sortable lexicographically.
        # Sidebar "Sort by → Date added" reads this.
        "added_at":  fm.get("added_at") or "",
        # Extraction pipeline sets `needs_doi: true` when no DOI could be
        # resolved (no /Info DOI, no text-scan DOI, no title-search hit).
        # Sidebar renders a "no DOI" chip so these papers are visually
        # distinct from ones that resolved cleanly.
        "needs_doi": bool(fm.get("needs_doi")),
    }


@papers_bp.route("/api/citations")
def citation_graph():
    """Whole-corpus citation graph — the substrate for connection
    analysis.

        {
          "nodes":  [{"slug","title","year","doi","cites_n","cited_by_n"}],
          "edges":  [["citing-slug", "cited-slug"], ...],
          "totals": {"papers","papers_with_doi","edges","refs_total",
                     "refs_with_doi","refs_linked"},
          "duplicate_dois": {"<doi>": ["slug-a","slug-b"]}
        }

    Edges are directed: `[A, B]` means A's reference list cites B.

    `duplicate_dois` is surfaced rather than silently resolved. Two
    summaries sharing a DOI means the same paper was imported twice
    under different slugs, which inflates link counts — the user needs
    to see it to fix it.
    """
    require_corpus_or_abort()
    index = build_index()
    nodes = []
    totals_refs = totals_doi = totals_linked = 0
    for slug, fm, _body in _walk_summaries():
        counts = index.ref_counts.get(slug, {})
        totals_refs   += counts.get("total", 0)
        totals_doi    += counts.get("with_doi", 0)
        totals_linked += counts.get("linked", 0)
        nodes.append({
            "slug":       slug,
            "title":      str(fm.get("title") or "").strip(),
            "year":       str(fm.get("year") or "").strip(),
            "doi":        normalize_doi(fm.get("doi")),
            "cites_n":    len(index.outgoing.get(slug, [])),
            "cited_by_n": len(index.incoming.get(slug, [])),
        })
    edges = [[src, dst] for src, dst in index.edges]
    logger.info("citation_graph_served papers=%d edges=%d", len(nodes), len(edges))
    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "totals": {
            "papers":          len(nodes),
            "papers_with_doi": sum(1 for n in nodes if n["doi"]),
            "edges":           len(edges),
            "refs_total":      totals_refs,
            "refs_with_doi":   totals_doi,
            "refs_linked":     totals_linked,
        },
        "duplicate_dois": index.duplicate_dois,
    })


@papers_bp.route("/api/papers")
def list_papers():
    require_corpus_or_abort()
    rows = [_paper_row(md) for md in summary_paths()]
    # Sort: author then year (year strings sort correctly for 4-digit years).
    rows.sort(key=lambda r: (str(r["author"]).lower(), str(r["year"])))
    return jsonify(rows)


# Per-paper data kept OUTSIDE frontmatter, reported to the panel as
# `stores: {name: bool}`. The Coverage table reads these through
# "STORE:<name>" cells — frontmatter alone cannot say a citer list is
# stored, which is how that row kept reading "deliberately not
# collected" after citers started being stored.
PAPER_STORES = {
    "citers": lambda slug: citers_path(slug).exists(),
}


@papers_bp.route("/api/paper/<slug>")
def paper_detail(slug):
    require_corpus_or_abort()
    md = summaries_dir() / f"{slug}.md"
    if not md.exists():
        abort(404)
    # Through the shared cache: the list endpoints have almost always
    # read this file already, so opening a paper costs a stat rather
    # than a re-parse. Was a raw read_text + parse_frontmatter, which
    # was the third independent way this codebase read a summary.
    got = _read_summary(md)
    if got is None:
        abort(404)
    fm, body = got
    # References are parsed SERVER-side and handed over structured.
    # The frontend used to re-parse the markdown itself, which meant two
    # implementations of the reference-line format that had to agree
    # forever with nothing enforcing it. `citations.resolve_references`
    # is now the only reader; `Reference.to_md_line` the only writer.
    index = build_index()
    links = index.links_for(slug)
    # PDF-read references are a THIRD source, folded in read-time. They
    # only fill blanks on API references and append ones the APIs
    # missed — see python/pdf_refs_merge.py. Cached per PDF, so this
    # costs a file read after the first view.
    pdf_refs, pdf_status = load_or_extract(
        slug, papers_dir() / f"{slug}.pdf", pdf_refs_dir())
    return jsonify({
        "slug":        slug,
        "frontmatter": fm,
        "body":        body,
        "references":  resolve_references(
            body, index, self_slug=slug, pdf_refs=pdf_refs,
            ss_confirmed_dois=fm.get("ss_confirmed_dois")),
        # Why the PDF contributed nothing, when it didn't. "unreadable"
        # means a scanned PDF with no text layer — the user can act on
        # that (re-download, OCR); silence would look like a bug.
        "pdf_refs_status": pdf_status,
        # Intra-corpus citation links, both directions. Derived from
        # what is on disk right now — never stored, so adding a paper
        # updates every affected summary's links with no repair pass.
        "cites":       links["cites"],
        "cited_by":    links["cited_by"],
        "ref_counts":  links["ref_counts"],
        # Cache-only; never triggers the ~22s network computation. An
        # uncomputed cache yields computed: False so the panel can say
        # "not computed yet" rather than "no connections".
        "bridges":     bridges_for_slug(slug),
        "pdf_url":     f"/pdf/{slug}" if (papers_dir() / f"{slug}.pdf").exists() else None,
        # Canonical deep-link keys — computed here using the exact same
        # helpers the aggregators use, so the frontend never has to guess.
        # (An earlier attempt to compute these client-side drifted on
        # some publisher shapes and 404'd on click.)
        "link_keys": _paper_link_keys(fm),
        "stores":    {name: has(slug) for name, has in PAPER_STORES.items()},
    })


def _paper_link_keys(fm: dict) -> dict:
    """Compute the deep-link keys for every entity referenced by a paper's
    frontmatter, using the same helpers the aggregators use. Result:

        {
          "journal":              str,   # "" if publisher unknown
          "authors_detailed":     [str, ...],   # parallel to fm.authors_detailed
          "authors_detailed_insts": [[str, ...], ...],   # per-author insts
          "oa_authors":           [str, ...],   # parallel to fm.oa_authors
          "oa_authors_insts":     [[str, ...], ...],
        }
    """
    # Journal key from publisher + ISSN, matching _aggregate_journals.
    pub = str(fm.get("publisher") or "").strip()
    journal = ""
    if pub and pub.lower() != "unknown":
        issns_raw = fm.get("issn") or []
        if isinstance(issns_raw, str): issns_raw = [issns_raw]
        issns = [_strip_quotes(x).upper() for x in issns_raw if _strip_quotes(x)]
        journal = _journal_key(pub, issns)

    def _author_keys(entries, has_ror):
        author_ks, insts_ks = [], []
        for a in entries:
            if not isinstance(a, dict):
                author_ks.append("")
                insts_ks.append([])
                continue
            author_ks.append(_author_key(a.get("family", ""), a.get("given", "")))
            insts = a.get("institutions") or []
            row = []
            for i in insts:
                if isinstance(i, dict) and has_ror:
                    row.append(_institution_key(i.get("name", ""), i.get("ror", "")))
                elif isinstance(i, str):
                    row.append(_institution_key(i, ""))
                else:
                    row.append("")
            insts_ks.append(row)
        return author_ks, insts_ks

    ad = fm.get("authors_detailed") or []
    if not isinstance(ad, list): ad = []
    oa = _parse_json_block(fm.get("oa_authors"))
    ad_k, ad_i = _author_keys(ad, has_ror=False)
    oa_k, oa_i = _author_keys(oa, has_ror=True)

    return {
        "journal":                journal,
        "authors_detailed":       ad_k,
        "authors_detailed_insts": ad_i,
        "oa_authors":             oa_k,
        "oa_authors_insts":       oa_i,
    }


@papers_bp.route("/pdf/<slug>")
def serve_pdf(slug):
    require_corpus_or_abort()
    p = papers_dir() / f"{slug}.pdf"
    if not p.exists():
        abort(404)
    return send_from_directory(papers_dir(), f"{slug}.pdf")


@papers_bp.route("/api/paper/<slug>/highlights", methods=["GET"])
def get_highlights(slug):
    """Return the paper's saved highlights. Stored at
    <corpus>/highlights/<slug>.json — outside summaries/ so re-extract
    can't wipe them. Empty list when file doesn't exist yet."""
    require_corpus_or_abort()
    return jsonify(load_highlights(highlights_dir() / f"{slug}.json"))


@papers_bp.route("/api/paper/<slug>/highlights", methods=["POST"])
def save_highlights(slug):
    """Replace this paper's highlight list. Frontend is the source of
    truth during a session — it mutates locally and POSTs the full
    state after each highlight add/change/delete (debounced ~200ms)."""
    require_corpus_or_abort()
    data = request.get_json(silent=True) or {}
    hls = data.get("highlights") or []
    if not isinstance(hls, list):
        return jsonify({"error": "highlights must be a list"}), 400
    # Same cleaning as a document's — see highlights_store.
    clean = clean_highlights(hls)
    save_highlights_file(highlights_dir() / f"{slug}.json", clean)
    logger.info("highlights_saved slug=%s count=%d", slug, len(clean))
    return jsonify({"ok": True, "count": len(clean)})


@papers_bp.route("/api/paper/<slug>/reveal", methods=["POST"])
@papers_bp.route("/api/paper/<slug>/reveal/<kind>", methods=["POST"])
def reveal_in_finder(slug, kind: str = "pdf"):
    """Open Finder / File Explorer with this paper's PDF or summary MD
    selected. `kind` is 'pdf' (default) or 'summary'. Cross-platform:
    `open -R` on macOS, `explorer /select,` on Windows, `xdg-open` on
    the parent dir on Linux (no per-file selection). Safe because
    Corpus binds to 127.0.0.1 only — this can't be called from a
    remote client."""
    require_corpus_or_abort()
    if kind == "summary":
        target = summaries_dir() / f"{slug}.md"
        missing_code = "summary_missing"
    else:
        target = papers_dir() / f"{slug}.pdf"
        missing_code = "pdf_missing"
    if not target.exists():
        abort(404, description=missing_code)
    import subprocess
    import sys as _sys
    try:
        if _sys.platform == "darwin":
            subprocess.run(["open", "-R", str(target)], check=False)
        elif _sys.platform.startswith("win"):
            subprocess.run(["explorer", f"/select,{target}"], check=False)
        else:
            subprocess.run(["xdg-open", str(target.parent)], check=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
