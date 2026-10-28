"""Intra-corpus citation links — paper A cites paper B, both in corpus.

## Why links are DERIVED, never stored

A link is a fact about the corpus as a whole, not about either paper.
Whether `smith-2023`'s 40th reference points at a paper you own depends
on which papers you own *right now* — add one PDF and links appear in
summaries you never touched.

So nothing here writes to summary files. Storing an `in_corpus: true`
flag next to each reference would mean every existing summary goes
stale the moment a paper is added, and something would have to sweep
the corpus to repair them. The index below is rebuilt from what is on
disk instead, which cannot go stale by construction.

## What links are matched on

DOI, exclusively. Reference DOIs survive `Reference.to_md_line()`
verbatim, so links resolve against summaries that are already on disk —
no re-extraction needed.

Title/author matching is deliberately NOT done here. Reference author
blocks are usually a bare surname (Crossref's convention) and titles
are frequently absent, so fuzzy matching would produce false links,
which are worse than missing ones for connection analysis.

## The index uses API references only — PDF references are display-only

`resolve_references` folds PDF-read references in for DISPLAY, but
`build_index` reads only what is in the summary files. That asymmetry
is deliberate: PDF references live in a per-paper cache that is
populated when a paper is viewed, so indexing them would make the graph
depend on which papers happened to be opened. Links that appear only
after you click something are worse than links that are consistently
absent.

Measured cost of the omission (57-paper corpus, 2026-08-25): 3 edges,
22 vs 25. Closing it needs a "read every PDF" pass so the cache is
complete before the index runs — tracked in ROADMAP.md.

## Cost

One pass over `summaries/`, parsing each `## References` section. That
is the same shape as the entity aggregators in `entities_api.py`, which
already walk every summary per request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from _api_common import _walk_summaries
from _paths import summaries_dir
from _api_http import normalize_doi
from extract_references import parse_references_section
from pdf_refs_merge import build_pdf_lookup, enrich, pdf_only

logger = logging.getLogger("corpus.citations")

# `normalize_doi` is re-exported (not redefined) so that a paper's
# frontmatter DOI and a reference's DOI are folded by the exact same
# rules. It lives in _api_http.py; see the note there.
__all__ = ["CitationIndex", "build_index", "normalize_doi",
           "resolve_references"]


@dataclass
class CitationIndex:
    """Whole-corpus citation graph.

    Attributes:
      doi_to_slugs  — every corpus paper keyed by its normalized DOI.
                      A list, not a scalar: two summaries CAN carry the
                      same DOI (duplicate imports under different
                      slugs), and silently picking one would drop real
                      links. Exposed via `duplicate_dois` so the
                      condition is visible rather than hidden.
      outgoing      — slug -> sorted slugs it cites (inside the corpus)
      incoming      — slug -> sorted slugs that cite it
      ref_counts    — slug -> {total, with_doi, linked}
    """
    doi_to_slugs: dict[str, list[str]] = field(default_factory=dict)
    outgoing:     dict[str, list[str]] = field(default_factory=dict)
    incoming:     dict[str, list[str]] = field(default_factory=dict)
    ref_counts:   dict[str, dict]      = field(default_factory=dict)
    # slug -> {"author","year","title"} for every indexed paper. Used to
    # label a reference that resolves INTO the corpus: publishers
    # routinely deposit a reference as a bare DOI with no author or
    # title, and for those we already hold the real metadata in the
    # cited paper's own summary. Exact, free, and better than anything
    # parsed off a page.
    paper_meta:   dict[str, dict]      = field(default_factory=dict)

    @property
    def duplicate_dois(self) -> dict[str, list[str]]:
        """DOIs claimed by more than one summary. A data-quality signal
        for the user, not an error — surfaced by /api/citations."""
        return {d: s for d, s in self.doi_to_slugs.items() if len(s) > 1}

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Every (citing, cited) pair, sorted. The form connection
        analysis wants."""
        return sorted((src, dst)
                      for src, dsts in self.outgoing.items()
                      for dst in dsts)

    def links_for(self, slug: str) -> dict:
        """Both directions for one paper, plus its reference counts."""
        return {
            "cites":      list(self.outgoing.get(slug, [])),
            "cited_by":   list(self.incoming.get(slug, [])),
            "ref_counts": self.ref_counts.get(
                slug, {"total": 0, "with_doi": 0, "linked": 0}),
        }


# Memoised index + the corpus fingerprint it was built from.
#
# Measured 2026-09-17 on a 590-summary corpus: with frontmatter parsing
# already cached, `parse_ref_line` became the top cost — 31,870
# reference lines re-parsed on EVERY request, because every call
# rebuilt the whole index from the summary bodies.
#
# The links themselves are still DERIVED and never written to disk (see
# the module docstring — that property has its own test). This only
# avoids recomputing an identical answer from unchanged inputs.
_CACHED: tuple[tuple, "CitationIndex"] | None = None


def _corpus_fingerprint() -> tuple:
    """Cheap stand-in for "have any summaries changed?".

    (file count, newest mtime, total size) — stats only, no reads. Any
    edit bumps the file's mtime to now, which becomes the newest; any
    add or delete changes the count. Rebuilding on a fingerprint miss
    is always correct, so the only risk is a MISSED change, and no
    single edit can leave all three values identical.
    """
    n = 0
    newest = 0
    total = 0
    for md in summaries_dir().glob("*.md"):
        try:
            st = md.stat()
        except OSError:
            continue
        n += 1
        total += st.st_size
        if st.st_mtime_ns > newest:
            newest = st.st_mtime_ns
    return (n, newest, total)


def clear_index_cache() -> None:
    """Drop the memoised index. For tests, and for any caller that
    rewrites summaries behind the walker's back."""
    global _CACHED
    _CACHED = None


def build_index() -> CitationIndex:
    """Read every summary ONCE, then resolve reference DOIs to slugs.

    Two passes over the parsed data, not over the disk: the DOI ->
    slug map must be complete before any reference can be resolved
    against it (paper 1 may cite paper 57), but re-walking the
    filesystem to get there would read every file twice.

    Memoised on `_corpus_fingerprint()`; adding, editing or removing
    any summary rebuilds it."""
    global _CACHED
    fp = _corpus_fingerprint()
    if _CACHED is not None and _CACHED[0] == fp:
        return _CACHED[1]
    idx = _build_index_uncached()
    _CACHED = (fp, idx)
    return idx


def _build_index_uncached() -> CitationIndex:
    idx = CitationIndex()
    parsed: list[tuple[str, list]] = []

    for slug, fm, body in _walk_summaries():
        doi = normalize_doi(fm.get("doi"))
        if doi:
            idx.doi_to_slugs.setdefault(doi, []).append(slug)
        idx.paper_meta[slug] = {
            "author": str(fm.get("author") or "").strip(),
            "year":   str(fm.get("year") or "").strip(),
            "title":  str(fm.get("title") or "").strip(),
        }
        parsed.append((slug, parse_references_section(body)))
    for slugs in idx.doi_to_slugs.values():
        slugs.sort()

    for slug, refs in parsed:
        with_doi = 0
        cited: set[str] = set()
        for ref in refs:
            rdoi = normalize_doi(ref.doi)
            if not rdoi:
                continue
            with_doi += 1
            for target in idx.doi_to_slugs.get(rdoi, ()):
                # A paper "citing itself" is a duplicate-DOI artifact,
                # not a real edge. Drop it rather than drawing a
                # self-loop.
                if target != slug:
                    cited.add(target)
        idx.outgoing[slug] = sorted(cited)
        idx.ref_counts[slug] = {
            "total": len(refs), "with_doi": with_doi, "linked": len(cited),
        }
        for target in cited:
            idx.incoming.setdefault(target, []).append(slug)

    for slug in idx.incoming:
        idx.incoming[slug] = sorted(set(idx.incoming[slug]))

    dupes = idx.duplicate_dois
    if dupes:
        logger.info("citation_index_duplicate_dois count=%d dois=%s",
                    len(dupes), sorted(dupes))
    logger.info("citation_index_built papers=%d edges=%d",
                len(idx.outgoing), len(idx.edges))
    return idx


def resolve_references(body: str, index: CitationIndex,
                       self_slug: str = "", pdf_refs=None,
                       ss_confirmed_dois=None) -> list[dict]:
    """Structured references for ONE paper, each tagged with the corpus
    paper it resolves to (if any).

    This is the single place reference lines become JSON for the
    frontend. Each entry:

        {
          "text":        display string (author/year/title or raw citation)
          "doi":         normalized DOI, "" when the ref has none
          "kind":        "book" | "chapter" | "series" | "article" | ""
          "extracted":   True when the DOI was regex-fished from raw text
          "linked_slug": corpus slug this ref points at, or None
          "sources":     which sources vouch for this reference, any of
                         "crossref", "semanticscholar", "pdf", "corpus"
                         ("corpus" = labelled from the cited paper's own
                         summary because the deposit had no metadata)
          "pdf_only":    True when the API list did not contain this ref
        }

    Pass `pdf_refs` (from `extract_references_pdf`) to fill blank
    author/title on API references and append ones the APIs missed.

    `linked_slug` is None for every reference to a paper outside the
    corpus — which is most of them, and is not a failure.
    """
    # Semantic Scholar confirmation is a per-reference source too. It
    # used to be recomputed in the frontend from frontmatter; keeping
    # every source in one server-side list means the UI renders what it
    # is given instead of re-deriving provenance.
    ss_set = {normalize_doi(d) for d in (ss_confirmed_dois or [])}
    ss_set.discard("")

    out: list[dict] = []
    for ref in parse_references_section(body):
        doi = normalize_doi(ref.doi)
        if ref.unstructured or not (ref.author_block or ref.title):
            text = ref.title
        else:
            parts = [p for p in (ref.author_block,
                                 str(ref.year) if ref.year else "",
                                 ref.title) if p]
            text = " ".join(parts)
        out.append({
            "text":        text,
            "doi":         doi,
            "kind":        ref.kind,
            "extracted":   ref.doi_source == "text-scan",
            "linked_slug": None,
            "sources":     (["crossref", "semanticscholar"]
                            if doi and doi in ss_set else ["crossref"]),
        })

    # PDF-read references are folded in AFTER the API list is built, so
    # they can only fill blanks and append — never displace a deposited
    # value. See python/pdf_refs_merge.py for the rule.
    if pdf_refs:
        by_doi, by_ay = build_pdf_lookup(pdf_refs)
        out = [enrich(r, by_doi, by_ay) for r in out]
        out.extend(pdf_only(pdf_refs, out))

    # Link resolution runs LAST so that references which only acquired a
    # DOI from the PDF still get matched against the corpus.
    for r in out:
        doi = normalize_doi(r.get("doi"))
        if not doi:
            continue
        for target in index.doi_to_slugs.get(doi, ()):
            if target != self_slug:
                r["linked_slug"] = target
                # A reference deposited as a bare DOI has no author or
                # title to show. When it points at a paper we hold, use
                # that paper's own metadata — exact by construction,
                # since the DOI matched. Without this the most
                # interesting references in the list (the ones the user
                # can actually open) are the ones rendered as a naked
                # DOI string.
                if not (r.get("text") or "").strip():
                    meta = index.paper_meta.get(target) or {}
                    parts = [p for p in (meta.get("author"), meta.get("year"),
                                         meta.get("title")) if p and p != "unknown"]
                    if parts:
                        r["text"] = " ".join(parts)
                        r["sources"] = list(r.get("sources") or []) + ["corpus"]
                break
    return out
