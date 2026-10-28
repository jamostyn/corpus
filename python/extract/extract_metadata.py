#!/usr/bin/env python3
"""
extract_metadata.py

Metadata orchestrator. Runs the resolution flow:
  1. PDF /Info stream — grab title / DOI if the typesetter set them.
  2. Text-scan for DOI-shaped tokens if /Info didn't hand one over.
  3. Title-search (Crossref, OpenAlex, Semantic Scholar) if step 2 also
     failed — including works that have no DOI at all.
  4. Slug fallback for everything still missing.

Each successful step feeds a triple lookup (Crossref + OpenAlex +
Semantic Scholar) whose results are merge_with_provenance()'d into a
single dict tagged with per-field origin.

Owns:
  * DOI extraction + ranking (regex, candidate scoring, cross-check).
  * PDF text fallbacks (font-cluster title, /Info stream, slug parse).
  * Merger + provenance tracker.
  * The extract_metadata() entry point + its CLI (`main`).

Delegates:
  * API client work (lookup + payload → dict) to crossref_client,
    openalex_client, semanticscholar_client.
  * Shared HTTP + text-similarity helpers to _api_http.

Usage:
  python3 extract_metadata.py papers/whittington-2020.pdf
  python3 extract_metadata.py papers/whittington-2020.pdf --json
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF not found. Run: python3 -m pip install pymupdf")

from crossref_client import (
    crossref_lookup,
    crossref_search_by_title,
    _from_crossref,
)
from openalex_client import openalex_lookup, openalex_search_by_title, _from_openalex
from _api_http import (
    DOI_RE,
    DOI_TRAIL_RE,
    split_display_name,
    surname_initial,
    title_worth_searching,
)
from semanticscholar_client import (
    semanticscholar_lookup,
    semanticscholar_lookup_id,
    semanticscholar_match_title,
    semanticscholar_author_batch,   # noqa: F401 — re-export for back-compat
    _from_semanticscholar,
)


# DOI capture — shared with rename_pdfs.py; canonical Crossref shape.
# Definitions moved to `_api_http.py` on 2026-08-16. Aliased at module
# scope so downstream code (`_DOI_RE.finditer(...)`) keeps compiling
# without a signature change.
_DOI_RE    = DOI_RE
_DOI_TRAIL = DOI_TRAIL_RE

# Year capture — anything in [1800, 2099] standing alone in the first page.
_YEAR_RE = re.compile(r'\b(1[89]\d{2}|20\d{2})\b')


# ---------- DOI extraction ----------

def extract_pdf_text(pdf: Path, max_pages: int = 3) -> str:
    """First-N-pages text. 3 is enough for masthead + abstract on almost
    every journal layout; book-style PDFs may need page 1 only."""
    doc = fitz.open(pdf)
    try:
        n = min(max_pages, doc.page_count)
        return "\n".join(doc[i].get_text() for i in range(n))
    finally:
        doc.close()


def _extract_doi_candidates(text: str) -> list[tuple[str, int]]:
    """Return every DOI-shaped substring found in `text` as (doi, pos)
    tuples. Deduplicates while preserving first-occurrence position for
    each unique DOI (used by scoring to weight earlier candidates).

    Normalizes Crossref's `/-/…` supplement suffix — e.g.,
    `10.1073/pnas.1912330117/-/DCSupplemental.y` collapses to
    `10.1073/pnas.1912330117`, so a supplement DOI and the paper DOI
    it hangs off dedupe to one entry. Does NOT drop prefix-truncations
    from line-breaks — that heuristic can't tell truncated-real from
    figure-doi-versus-paper-doi apart (they have identical structure).
    The extract flow handles ambiguity by trying multiple candidates
    and checking the resolved Crossref `type` field."""
    seen: dict[str, int] = {}
    for m in _DOI_RE.finditer(text):
        doi = _DOI_TRAIL.sub("", m.group(0)).lower()
        supp = doi.find("/-/")
        if supp > 0:
            doi = doi[:supp]
        # APA's supplement DOIs are the paper's DOI plus ".supp". Printed
        # in the PDF next to the paper's own, it won on 2026-09-25 and
        # Taatgen 2013 imported as "Supplemental Material for The Nature
        # and Transfer of Cognitive Skills" (10.1037/a0033138.supp).
        doi = re.sub(r"\.supp$", "", doi)
        if doi and doi not in seen:
            seen[doi] = m.start()
    return sorted(seen.items(), key=lambda x: x[1])


# Crossref `type` values that indicate a resource which is NOT itself
# a paper — datasets, figures, tables, supplementary materials, grants,
# posted-content headers. When a DOI resolves to one of these, we
# reject it and try the next candidate.
_NON_PAPER_TYPES = frozenset({
    "component",       # PLoS uses this for figures/tables (.g001, .t001)
    "dataset",         # NIMH Data Archive etc.
    "grant",
    "reference-entry", # dictionary/encyclopedia entry — rarely what we want
    "peer-review",
    "standard",
})


_FRONT_MATTER_RE = re.compile(
    # Only phrases no research title ends on. "index", "cover" and
    # "contents" are deliberately absent — "... a new memory index" is a
    # paper.
    r"(?:^|[:\s])(editors?|editorial board|masthead|front matter|back matter|"
    r"issue information|table of contents|"
    r"information for authors|instructions to authors)\.?\s*$",
    re.IGNORECASE)


# Supplements are titled after their paper — "Supplemental Material for
# <the paper's title>" — so they are caught by how the title STARTS.
_SUPPLEMENT_RE = re.compile(
    r"^\s*(supplementa(l|ry)\s+(material|materials|information|data|online\s+material)|"
    r"online\s+supplement)\b", re.IGNORECASE)


def _is_front_matter(title: str) -> bool:
    """True for a record that belongs to a paper but is not the paper: a
    journal's editors page, table of contents, or a supplement.

    Front matter is matched on how the title ENDS ("…: Editors."), so a
    paper merely mentioning editors is not caught; supplements on how it
    STARTS ("Supplemental Material for …", Taatgen 2013, 2026-09-25)."""
    t = (title or "").strip()
    return bool(_FRONT_MATTER_RE.search(t) or _SUPPLEMENT_RE.search(t))


def find_doi(text: str) -> str | None:
    """Backwards-compat single-DOI accessor: returns the highest-scoring
    candidate's DOI, or None. Kept for callers that don't want the slug
    cross-check; the full extract_metadata() flow uses
    _select_best_doi() with slug hints so it can catch and reject
    citation-DOIs that shadow the paper's own."""
    ranked = _rank_dois(text)
    return ranked[0][0] if ranked else None


# Score weights — chosen so masthead context comfortably outranks
# reference-list context, and repeats outrank single occurrences.
_SCORE_HTTPS_PREFIX     = 60    # "https://doi.org/..." — canonical publisher URL
_SCORE_UPPER_DOI_PREFIX = 50    # "DOI 10..." / "DOI: 10..." (masthead style)
_SCORE_LOWER_DOI_PREFIX = 15    # "doi:10..." (weaker — used in both mastheads and refs)
_SCORE_CITATION_PENALTY = -80   # preceded by "Author et al., YYYY" pattern
_SCORE_YEAR_PAREN_PEN   = -40   # preceded by "(YYYY)." — inline citation punctuation
_SCORE_MASTHEAD_ZONE    = 40    # in the first ~800 chars (usually title/header block)
_SCORE_REPEAT_BONUS     = 30    # +30 per additional occurrence in the text
_SCORE_REFS_ZONE        = -25   # after the word "References" first appears


def _score_doi(doi: str, first_pos: int, text: str) -> int:
    """Assign a heuristic score to a DOI candidate. Higher = more likely
    to be the paper's own DOI (as opposed to a citation)."""
    score = 0
    # Context immediately before the DOI (~40 chars is enough to see the
    # prefix + a bit of surrounding punctuation).
    lo = max(0, first_pos - 40)
    ctx = text[lo:first_pos]
    if "https://doi.org/" in ctx or "http://dx.doi.org/" in ctx or "dx.doi.org/" in ctx:
        score += _SCORE_HTTPS_PREFIX
    # "DOI " / "DOI:" (case-sensitive — uppercase DOI is more common in
    # publisher mastheads; lowercase "doi:" is common in reference lists).
    if re.search(r"DOI[:\s]$", ctx):
        score += _SCORE_UPPER_DOI_PREFIX
    elif re.search(r"doi:\s*$", ctx):
        score += _SCORE_LOWER_DOI_PREFIX
    # Position bonus: masthead / title-block area (first ~800 chars of
    # the first page in most journal layouts).
    if first_pos < 800:
        score += _SCORE_MASTHEAD_ZONE
    # Penalty: appearance inside or after the references block. Not
    # perfect — some papers embed refs mid-body — but on the common
    # case this cleanly separates masthead from bibliography.
    m_refs = re.search(r"\n\s*(References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*\n", text)
    if m_refs and first_pos > m_refs.end():
        score += _SCORE_REFS_ZONE
    # Penalty: preceded by "et al." or "(YYYY)." — strong citation
    # signals even when the DOI itself is preceded by "doi:".
    if re.search(r"et al\.[^.\n]{0,40}$", ctx):
        score += _SCORE_CITATION_PENALTY
    if re.search(r"\(\d{4}\)\s*\.?\s*$", ctx):
        score += _SCORE_YEAR_PAREN_PEN
    # Bonus: same DOI mentioned multiple times (papers often repeat
    # their own DOI in header + footer + citation-suggestion box).
    occurrences = len(re.findall(re.escape(doi), text, re.IGNORECASE))
    if occurrences > 1:
        score += _SCORE_REPEAT_BONUS * (occurrences - 1)
    return score


def _rank_dois(text: str) -> list[tuple[str, int]]:
    """Return DOI candidates sorted by descending score.
    Each entry is (doi, score). Ties broken by earlier position."""
    cands = _extract_doi_candidates(text)
    if not cands:
        return []
    scored: list[tuple[str, int, int]] = []
    for doi, pos in cands:
        scored.append((doi, _score_doi(doi, pos, text), pos))
    # Sort: highest score first, then earliest position for ties.
    scored.sort(key=lambda x: (-x[1], x[2]))
    return [(d, s) for d, s, _ in scored]


def _select_best_doi(text: str, expected_surname: str = "",
                     expected_year: int | None = None,
                     max_candidates: int = 3) -> str | None:
    """Rank DOI candidates, then verify the top-N against the slug's
    expected (surname, year) via a Crossref lookup. Return the first
    DOI whose Crossref record matches. If none matches, return None so
    the caller can fall through to the title-search fallback.

    Cross-check rules:
      - Surname (family name of first author) matches, case-insensitive
        on the first token — so "Anderson, J." matches "Anderson" and
        also "Anderson-Roberts".
      - Year within ±1 of expected (handles online-first vs print-year
        discrepancies).
      - If expected_surname is empty, we can't cross-check → accept the
        top-scored DOI unchanged.

    This is what fixes the "first DOI in text is actually a citation to
    a different paper" bug: candidates that would return a paper with a
    different surname/year are rejected in favor of later candidates."""
    ranked = _rank_dois(text)
    if not ranked:
        return None
    # No expected surname → skip cross-check (behaves like old find_doi).
    if not expected_surname:
        return ranked[0][0]
    exp_surname = expected_surname.strip().lower().split()[0] if expected_surname else ""
    for doi, _score in ranked[:max_candidates]:
        msg = crossref_lookup(doi)
        if not msg:
            continue
        # Extract first-author family name + year from the Crossref msg.
        authors = msg.get("author") or []
        got_surname = ""
        if authors:
            got_surname = (authors[0].get("family") or "").strip().lower().split()[0]
        got_year = None
        for k in ("published-print", "published-online", "issued", "created"):
            dp = (msg.get(k) or {}).get("date-parts") or []
            if dp and dp[0]:
                try:
                    got_year = int(dp[0][0])
                    break
                except (TypeError, ValueError):
                    continue
        if got_surname != exp_surname:
            continue
        if expected_year is not None and got_year is not None:
            if abs(got_year - expected_year) > 1:
                continue
        return doi
    return None


# ---------- Author/institution merging ----------

def _author_institutions(a: dict) -> list[str]:
    """Return the institutions list from an author dict, tolerating
    both the modern `institutions: [...]` and legacy `institution: "X"`
    shapes."""
    lst = a.get("institutions")
    if isinstance(lst, list):
        return [str(s).strip() for s in lst if str(s).strip()]
    single = (a.get("institution") or "").strip()
    return [single] if single else []


def _merge_author_institutions(base: dict, enrich: dict) -> None:
    """UNION merge enrich's institutions[] into base's institutions[]
    per author (family-name matched). Preserves order: base's existing
    entries stay first, enrich's new-to-base entries append. Multi-affil
    authors get ALL their institutions from any API that returned them.
    `base` is mutated in place.
    """
    b_det = base.get("authors_detailed") or []
    e_det = enrich.get("authors_detailed") or []
    if not b_det or not e_det:
        return
    def _fam_key(fam: str) -> str:
        return (fam or "").strip().lower().split()[0] if fam else ""
    e_index: dict[str, list[str]] = {}
    for e in e_det:
        key = _fam_key(e.get("family", ""))
        insts = _author_institutions(e)
        if key and insts and key not in e_index:
            e_index[key] = insts
    for b in b_det:
        key = _fam_key(b.get("family", ""))
        if not key or key not in e_index:
            continue
        # Ensure the base entry uses the plural key going forward.
        current = _author_institutions(b)
        for new_i in e_index[key]:
            if new_i not in current:
                current.append(new_i)
        b["institutions"] = current
        # Legacy singular key stays out of new writes; drop if present.
        b.pop("institution", None)



# ---------- PDF /Info + text-based fallbacks ----------

def _looks_like_real_title(s: str) -> bool:
    """True if the string is plausible as a paper title. PDF /Info often
    contains junk like the LaTeX source filename ("chan_koop_SSVAR_final.dvi"),
    a publisher address ("Oxford University Press, Walton Street, ..."), or
    a single character. Reject those so we don't seed the summary with garbage.
    """
    s = s.strip()
    if len(s) < 8:
        return False
    if re.search(r"\.(dvi|tex|pdf|doc|docx|fm|indd)$", s, re.IGNORECASE):
        return False
    if "_" in s and " " not in s:           # CamelCase_underscore_filename
        return False
    if re.search(r"\b(Press|University Press|Avenue|Street|Walton|Madison)\b.*\d", s):
        return False
    if s.lower() == s and len(s) < 40:      # all-lowercase short string — usually a slug
        return False
    return True


_CONTAINER_TITLE_PATTERNS = re.compile(
    r"^(?:the\s+)?(?:"
    r"proceedings\b"
    r"|journal\s+of\b"
    r"|(?:the\s+)?annual\s+meeting\b"
    r"|annual\s+review\b"
    r"|current\s+(?:opinion|directions)\b"
    r"|trends\s+in\b"
    r"|(?:international|american|british|european|australian|canadian)\s+journal\b"
    r"|frontiers\s+in\b"
    r"|ieee\s+(?:transactions|journal|access)\b"
    r"|acm\s+transactions\b"
    r"|nature\s+[a-z]"
    r"|plos\s+(?:one|biology|computational|medicine|genetics)"
    r"|neural\s+computation\b"
    r"|psychological\s+(?:review|bulletin|science)\b"
    r"|scientific\s+reports\b"
    r"|cognitive\s+(?:science|psychology|systems)\b"
    r"|behavioral\s+and\s+brain\s+sciences\b"
    r"|attention,?\s+perception,?\s+(?:&|and)\s+psychophysics\b"
    r"|elife\b"
    r"|cell\s+reports\b"
    r"|neuroimage\b"
    r"|brain\s+and\s+cognition\b"
    r")",
    re.IGNORECASE,
)

# Words that show up in title pages of institutional-repository copies
# (eScholarship, ResearchGate, ProQuest, PsyArXiv landing pages) as
# standalone field labels. If a candidate is dominated by these, it's
# metadata-label soup, not the actual title.
_METADATA_LABEL_WORDS = frozenset({
    "title", "permalink", "journal", "authors", "author", "publication",
    "date", "copyright", "information", "abstract", "keywords", "doi",
    "issn", "volume", "issue", "pages", "citation", "download",
    "license", "reviewed", "peer", "affiliation", "affiliations",
    "correspondence", "acknowledgments", "acknowledgements",
})


def _looks_like_container_title(s: str) -> bool:
    """True if the string looks like a journal / proceedings / masthead
    name rather than a paper title. Rejects the largest-font block on
    page 1 when it's the journal masthead — otherwise Crossref search
    happily matches a same-named record (e.g. some 2006 paper actually
    titled 'The Annual Meeting of the Cognitive Science Society'
    existing in an unrelated journal), producing wrong metadata."""
    s = s.strip()
    if not s:
        return False
    # Direct pattern match on common journal / proceedings prefixes.
    if _CONTAINER_TITLE_PATTERNS.match(s):
        return True
    # All-caps 2-6 word strings — masthead/running-head shape.
    words = s.split()
    if 2 <= len(words) <= 6 and s == s.upper():
        return True
    return False


def _looks_like_metadata_label_soup(s: str) -> bool:
    """True if the string is dominated by institutional-repository
    field labels (Title / Permalink / Journal / Authors / Publication
    Date / Copyright Information / ...). eScholarship, ProQuest, and
    other repositories arrange these labels at the same font size, so
    the font-cluster heuristic concatenates them into one useless
    candidate.

    Also rejects short candidates that are 100% label tokens ("Copyright
    Information", "Publication Date") — Crossref title-search will
    happily match those to unrelated records that happen to be titled
    that way (some IEEE conference paper is literally titled 'Copyright
    Information'), so the fallback must drop them BEFORE searching."""
    tokens = re.findall(r"[a-zA-Z]+", s.lower())
    if not tokens:
        return False
    label_hits = sum(1 for t in tokens if t in _METADATA_LABEL_WORDS)
    if not label_hits:
        return False
    # 100% labels — drop regardless of length. Short pure-label strings
    # ("Copyright Information") are the most dangerous: they're the
    # exact literal strings some real records use as their title.
    if label_hits == len(tokens):
        return True
    # Long dominated-by-labels strings — the eScholarship label-run case.
    return label_hits >= 4 and label_hits / len(tokens) >= 0.5



def _clean_candidate(s: str) -> str:
    """Post-process a raw candidate: collapse whitespace, strip common
    leading noise (Running head labels, page numbers, one-glyph
    prefixes). Returns "" if nothing usable remains."""
    s = re.sub(r"\s+", " ", s or "").strip()
    # Strip "Running head: XXX" prefix — APA-style running head that
    # appears above the title in preprint drafts.
    s = re.sub(r"^Running\s+head:\s*[^.]{0,80}?\s+", "", s, flags=re.IGNORECASE).strip()
    return s


def _line_scan_candidates(pdf: Path, max_candidates: int = 3) -> list[str]:
    """Line-based title fallback for uniform-font PDFs (APA-style
    preprints, older typewriter layouts) where font-size ranking
    can't distinguish the title from the body.

    Walks the first page's plain text top-to-bottom, skipping obvious
    non-title lines (page numbers, running heads, emails, URLs, short
    lone glyphs), and returns the first `max_candidates` that pass
    length + shape checks."""
    try:
        doc = fitz.open(pdf)
        try:
            text = doc[0].get_text("text") or ""
        finally:
            doc.close()
    except Exception:
        return []
    out: list[str] = []
    for raw in text.splitlines():
        line = _clean_candidate(raw)
        if len(line) < 20 or len(line) > 250:
            continue
        low = line.lower()
        if low.startswith(("running head", "running title", "in press", "in-press",
                           "correspondence", "corresponding author", "keywords",
                           "abstract", "introduction", "https://", "http://",
                           "www.", "doi:")):
            continue
        if "@" in line and len(line) < 80:              # author email line
            continue
        if re.fullmatch(r"[\d\W]+", line):              # only digits/punctuation
            continue
        if _looks_like_container_title(line):
            continue
        if _looks_like_metadata_label_soup(line):
            continue
        if not _looks_like_real_title(line):
            continue
        out.append(line)
        if len(out) >= max_candidates:
            break
    return out


def _join_spans(spans: list[dict], size: float) -> str:
    """One line's text from its spans, with a space wherever the page
    shows a gap.

    Some PDFs store no space characters at all — each word is its own
    span, positioned apart. Joining those bare gave
    "TheLearningofCategories:ParallelBrainSystems" (knowlton-1993,
    2026-09-24). Joining with " " instead would split small-caps words
    ("T" + "HE") that sit flush. So the page geometry decides: a gap
    wider than ~15% of the font size is a word break."""
    out = ""
    prev_x1 = None
    for s in spans:
        t = s.get("text") or ""
        x0, _y0, x1, _y1 = (s.get("bbox") or [0, 0, 0, 0])[:4]
        if (prev_x1 is not None and out and not out.endswith(" ") and not t.startswith(" ")
                and float(x0) - prev_x1 > 0.15 * size):
            out += " "
        out += t
        prev_x1 = float(x1)
    return out


def _title_candidates_from_pdf_text(pdf: Path, max_candidates: int = 3) -> list[str]:
    """Scant title extractor — first-page font-size ranking with a
    line-scan fallback.

    Only used when /Info's title is empty AND DOI extraction failed.
    Each returned candidate is piped to `crossref_search_by_title`
    (0.85 similarity threshold) in order. Journal / masthead / metadata-
    label shapes are filtered out preemptively so a candidate that
    *would* Crossref-match a wrongly-titled record never gets sent.
    If nothing survives, we return an empty list and the paper falls
    through to `needs_doi: True` — better than storing garbage.

    Two stages, in order:
      1. Font-cluster: group spans by font size, join top-to-bottom
         within each cluster. Filter out journal/masthead candidates.
      2. Line-scan fallback for uniform-font PDFs (all one size on
         page 1, so font-clustering yields nothing usable): walk lines
         top-to-bottom, skip obvious non-title shapes.
    """
    try:
        doc = fitz.open(pdf)
        try:
            page_dict = doc[0].get_text("dict")
        finally:
            doc.close()
    except Exception:
        return []

    # Grouped by LINE, not by span. A title is often typeset in more than
    # one size: small caps ("THE LEARNING OF" with larger capitals), a
    # smaller "of"/"and", or two title lines at 17.1pt and 16.6pt. Keyed
    # by exact span size, each piece landed in its own bucket and the
    # candidate lost words — measured 2026-09-24: "A New Theory of Disuse
    # and an Old Theory of Stimulus Fluctuation" came out as "Theory
    # Disuse Theory and Stimulus Fluctuation", and 6 of 11 unresolved
    # papers failed title lookup for this reason alone. A line's size is
    # its largest span, and its text is all its spans in order.
    lines: list[tuple[float, float, float, str]] = []      # (size, y, x, text)
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
            if not spans:
                continue
            size = max(float(s.get("size") or 0.0) for s in spans)
            text = re.sub(r"\s+", " ", _join_spans(spans, size)).strip()
            x0, y0 = (line.get("bbox") or [0, 0, 0, 0])[:2]
            lines.append((size, float(y0), float(x0), text))

    # Size tiers: each tier takes every not-yet-claimed line within 12% of
    # its largest size, so a title's slightly smaller second line stays
    # with the first instead of forming a candidate of its own.
    tiers: list[list[tuple[float, float, str]]] = []
    remaining = sorted(lines, key=lambda l: -l[0])
    while remaining:
        top = remaining[0][0]
        tier = [l for l in remaining if l[0] >= top * 0.88]
        remaining = [l for l in remaining if l[0] < top * 0.88]
        tiers.append([(y, x, t) for _, y, x, t in tier])

    out: list[str] = []
    for tier in tiers:
        candidate = _clean_candidate(" ".join(t for _, _, t in sorted(tier)))
        if len(candidate) < 15 or len(candidate) > 250:
            continue
        if not _looks_like_real_title(candidate):
            continue
        if _looks_like_container_title(candidate):
            continue
        if _looks_like_metadata_label_soup(candidate):
            continue
        out.append(candidate)
        if len(out) >= max_candidates:
            break

    if out:
        return out
    return _line_scan_candidates(pdf, max_candidates=max_candidates)



def _from_pdf_metadata(pdf: Path) -> dict:
    """PDF /Info dict — often set by typesetting tools (Elsevier, Springer,
    APA Word templates). Author can be a comma- or semicolon-separated list."""
    doc = fitz.open(pdf)
    try:
        md = doc.metadata or {}
    finally:
        doc.close()
    out: dict = {"source": "pdf-metadata"}
    if md.get("title") and _looks_like_real_title(md["title"]):
        out["title"] = md["title"].strip()
    raw_author = (md.get("author") or "").strip()
    # PDF /Info `Author` is often the OS-account name of whoever last
    # exported the PDF ("rafal", "joey", first name only with no caps) —
    # not a real bibliographic author. Drop if it has no capital letter
    # in the first token (real names start capitalized).
    if raw_author and not re.match(r"^[A-Z]", raw_author.lstrip()):
        raw_author = ""
    if raw_author and len(re.sub(r"[^A-Za-z]", "", raw_author)) >= 2:
        # Try to split into a list of "Lastname F." entries.
        parts = re.split(r"\s*[;]\s*|\s+and\s+|,\s*(?=[A-Z][a-z])", raw_author)
        full: list[str] = []
        detailed: list[dict] = []
        for p in parts:
            p = p.strip(", ")
            if not p:
                continue
            # Split shared with `_from_openalex` — handles both
            # "Endel Tulving" and "Smith J." shapes; see split_display_name.
            family, given = split_display_name(p)
            if not family:
                continue
            detailed.append({"family": family, "given": given})
            full.append(surname_initial(family, given))
        if detailed:
            out["authors_detailed"] = detailed
            out["authors_full"] = full
            first = detailed[0]
            init = (first["given"].strip()[0] + ".") if first["given"] else ""
            out["author"] = f"{first['family']}, {init}".strip(", ").strip()
    return out


def _from_text_heuristic(text: str) -> dict:
    """Last-resort heuristic. Look for "Received N Month YYYY", "Accepted",
    "Published", "Copyright YYYY" — these are the strongest year signals,
    much more reliable than the first 4-digit number in the document
    (which is often a page number or a body-text year reference).
    Title/author are too unreliable to guess from text layout without
    a parser; we leave them blank for the LLM to fill in.
    """
    out: dict = {"source": "text-heuristic"}
    for pat in (
        r"(?:Received|Accepted|Published|Available\s+online|Revised)\s+[^\n]{0,40}?\b(1[89]\d{2}|20\d{2})\b",
        r"(?:Copyright|©)\s*\D{0,15}\b(1[89]\d{2}|20\d{2})\b",
        r"\b(?:Vol(?:ume)?\.?|Issue)\s*\d+[^\n]{0,80}?\b(1[89]\d{2}|20\d{2})\b",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            out["year"] = int(m.group(1))
            return out
    # No wild-card fallback — the slug already has the canonical year and
    # the first-4-digit-anywhere heuristic loses to body-text references
    # too often (see song-2014, where the RCEA boilerplate landed on 2007).
    return out


def _from_slug(pdf: Path) -> dict:
    """The canonical PDF filename `<surname>-<year>[-N].pdf` is the
    agreed-upon source of truth for surname + year (rename_pdfs.py
    guarantees this by the time prefill runs). Use it as a low-priority
    seed so Crossref / PDF-metadata can override, but old scanned PDFs
    with no other signal still get the right year + surname-derived
    author placeholder.

    Hyphenated slugs ("kahneman-frederick-2002") use only the FIRST
    surname token — that's the first author. The full slug as one family
    name would render as "Kahneman-frederick" which is wrong.
    """
    out: dict = {"source": "slug"}
    m = re.match(r"^([a-z][a-z\-]*?)-(\d{4})(?:-\d+)?$", pdf.stem)
    if not m:
        return out
    surname_compound, year = m.group(1), int(m.group(2))
    # First hyphenated token = first author surname.
    surname_lower = surname_compound.split("-")[0]
    family = surname_lower[0].upper() + surname_lower[1:]
    out["year"] = year
    out["author"] = f"{family}, "
    out["authors_full"] = [family]
    out["authors_detailed"] = [{"family": family, "given": ""}]
    return out



# ---------- Merger with per-field provenance ----------

def merge(*dicts: dict) -> dict:
    """Left-to-right merge — later dicts only fill in keys earlier ones
    missed. Lets us call merge(crossref, pdf_meta, heuristic) and get
    Crossref's authoritative values where present."""
    out: dict = {}
    for d in dicts:
        if not d:
            continue
        for k, v in d.items():
            if k in out and out[k] not in (None, "", [], {}):
                continue
            out[k] = v
    return out


# Fields whose provenance we track for the UI's per-field badges.
# Scalars get full [winner, ...verifiers] tracking. Lists (authors_full,
# authors_detailed) get single-winner-only tracking — cross-source list
# equality is fuzzy, so we don't try to compute verifiers, but we still
# expose which source produced the value.
PROVENANCE_FIELDS = (
    # Core bibliographic identifiers
    "doi", "title", "year", "publisher", "kind", "pages", "source_url",
    "authors_full", "authors_detailed",
    # Extended bibliographic
    "volume", "issue", "article_number", "language",
    "issn", "isbn", "alternative_ids",
    # Counts
    "citation_count", "references_count",
    "citation_count_ss", "influential_citation_count_ss",
    "citation_count_oa", "fwci",
    # Content
    "abstract", "subjects", "tldr",
    # Rich Crossref
    "funder", "license", "update_to",
    "retracted", "event_name",
    # SS-derived
    "s2_fields_of_study", "publication_types", "paper_type",
    "open_access_pdf_url", "bibtex", "ss_paper_id",
    # OA-derived
    "oa_status", "topics", "keywords", "oa_paper_id",
    "counts_by_year", "oa_locations", "oa_authors", "versions",
    "retraction_notice",
    # 2026-08-08 extensions
    # Crossref extras
    "content_assertions", "edition_number", "chapter_number",
    "component_number", "journal_issue_date",
    "deposited_at", "indexed_at",
    # SS extras
    "ss_venue_type", "ss_venue_url", "ss_venue_alternate_names",
    # OA extras
    "venue_type", "host_organization", "host_organization_lineage",
    "has_fulltext", "fulltext_origin", "is_paratext",
    "oa_created_date", "oa_updated_date",
)


def _norm_for_compare(v):
    """Normalize a scalar for cross-source equality checks. Strings get
    lowercased + trimmed; ints stay as-is."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


def merge_with_provenance(*dicts: dict) -> tuple[dict, dict]:
    """Like merge(), but also returns per-field provenance.

    Each input dict must carry a `source` key naming its origin
    (crossref / openalex / semanticscholar / pdf-metadata / slug).

    Returns (merged_dict, sources_dict) where sources_dict[field] is
    an ordered list [winner, ...verifiers]. A verifier is a source whose
    value equalled the winner's (after normalize) — meaningful cross-
    source confirmation of that field."""
    out: dict = {}
    sources: dict[str, list[str]] = {}
    for d in dicts:
        if not d:
            continue
        src = d.get("source", "?")
        for k, v in d.items():
            if k == "source" or v in (None, "", [], {}):
                continue
            if k not in out:
                out[k] = v
                sources[k] = [src]
                continue
            # Field already claimed by an earlier (higher-precedence)
            # source. If this source's value matches, it's a verifier.
            try:
                if _norm_for_compare(v) == _norm_for_compare(out[k]):
                    if src not in sources[k]:
                        sources[k].append(src)
            except Exception:
                # Un-normalizable (e.g. lists/dicts) → ignore.
                pass
    return out, sources



# ---------- Orchestrator + CLI ----------

def _collect_api_metadata(doi: str) -> tuple[dict, dict, dict]:
    """Fetch metadata for `doi`. Returns (crossref, openalex, semanticscholar)
    dicts, each empty {} when the API isn't called or returns nothing.

    v0.3 (2026-08-08): Crossref + Semantic Scholar + OpenAlex all wired.
    OA adds the structured institution hierarchy, cited-by count, topics
    hierarchy, FWCI, all-locations, corresponding-author flag, and
    versions — none of which the other two provide."""
    crossref: dict = {}
    openalex: dict = {}
    ss: dict = {}
    msg = crossref_lookup(doi)
    if msg:
        crossref = _from_crossref(msg)
    ss_work = semanticscholar_lookup(doi)
    if ss_work:
        ss = _from_semanticscholar(ss_work)
    oa_work = openalex_lookup(doi)
    if oa_work:
        openalex = _from_openalex(oa_work)
    return crossref, openalex, ss


def _merge_api_meta(crossref: dict, openalex: dict, ss: dict) -> dict:
    """Combine the three API-derived dicts into one canonical metadata
    dict. Precedence for shared fields:
      - title/year/publisher/kind/pages: Crossref > OA > SS
      - authors_detailed / authors_full / author: Crossref > OA > SS
      - authors_detailed[].institution: OA > Crossref > SS (OA has the
        best affiliation coverage — merged via _merge_author_institutions
        so the Crossref author LIST wins but OA's institutions ride in)
      - abstract: SS > OA (Crossref doesn't reliably provide one)
      - source_url: Crossref > OA (Crossref canonical DOI URL preferred)
    """
    api_meta = merge(crossref, openalex, ss)
    # OA (and SS as second fallback) enrich institutions on the winning
    # author list. Mutates api_meta in place.
    _merge_author_institutions(api_meta, openalex)
    _merge_author_institutions(api_meta, ss)
    # Abstract precedence: SS > OA. merge() above already put SS-if-
    # present-else-OA into api_meta['abstract'] because SS is later in
    # the merge chain and merge() is "first non-empty wins per key".
    # No further work needed for abstract.
    sources = [d.get("source") for d in (crossref, openalex, ss) if d.get("source")]
    if sources:
        api_meta["source"] = "+".join(sources)
    return api_meta


def _resolve_by_title(title: str) -> tuple[dict, dict, dict]:
    """(crossref, openalex, semanticscholar) dicts for the paper `title`
    names, or three empties.

    Order: Crossref search, then OpenAlex `title.search`, then S2
    `/search/match`. Whichever first yields a DOI hands off to the full
    three-source DOI lookup — a paper found by title then carries exactly
    what a paper found by DOI would.

    When OpenAlex / S2 recognise the work but it has NO DOI, their
    records are the result: title, authors, year, venue, counts, and the
    services' own ids (`oa_paper_id`, `ss_paper_id`). Crossref cannot
    represent such a work — its identifier IS the DOI.

    Measured 2026-09-24 on the 11 corpus papers whose DOI never resolved:
    with correct titles, OpenAlex found 10, S2 9, Crossref 8; 8 of them
    had a DOI the whole time, 2 exist only under the services' own ids.
    """
    if not title_worth_searching(title):
        return {}, {}, {}

    def usable(cr, oa, ss) -> bool:
        # Every path out of here is checked, not just one: on 2026-09-24
        # a masthead line ("Psychology, Public Policy, and Law") went in
        # as the title and Crossref's search returned that journal's
        # "…: Editors." page — the guard on the DOI-scan step never saw it.
        if not (cr or oa or ss):
            return False
        found_title = cr.get("title") or oa.get("title") or ss.get("title") or ""
        return not _is_front_matter(str(found_title))

    found = crossref_search_by_title(title, "", None)
    if found:
        cr, oa, ss = _collect_api_metadata(found)
        if usable(cr, oa, ss):
            return ({**cr, "source": "crossref-search"} if cr else {}), oa, ss

    oa_work = openalex_search_by_title(title)
    oa_doi = ((oa_work or {}).get("doi") or "").replace("https://doi.org/", "").strip().lower()
    if oa_doi:
        cr, oa, ss = _collect_api_metadata(oa_doi)
        if usable(cr, oa, ss):
            return cr, oa, ss

    ss_hit = semanticscholar_match_title(title)
    if ss_hit and ss_hit.get("doi"):
        cr, oa, ss = _collect_api_metadata(ss_hit["doi"])
        if usable(cr, oa, ss):
            return cr, oa, ss

    # No DOI anywhere: build from the services' own records.
    oa = _from_openalex(oa_work) if oa_work and not oa_doi else {}
    ss_work = (semanticscholar_lookup_id(ss_hit["paper_id"])
               if (ss_hit or {}).get("paper_id") and not ss_hit.get("doi") else None)
    ss = _from_semanticscholar(ss_work) if ss_work else {}
    return ({}, oa, ss) if usable({}, oa, ss) else ({}, {}, {})


def extract_metadata(pdf: Path) -> dict:
    """API-only extraction (Corpus v0.1 shipped scope).

    Resolution order (each layer only fills what earlier layers missed):
      1. PDF /Info stream (structured metadata the typesetting software
         embedded — NOT text parsing / OCR).
      2. If /Info has a DOI → Crossref (and OpenAlex + Semantic Scholar
         when the user has keys set) look-up on that DOI.
      3. If no DOI but /Info has a title → title search (Crossref, then
         OpenAlex, then Semantic Scholar — `_resolve_by_title`). If /Info
         has no title either → scan page 1 for the largest-font lines as
         title candidates and search with those. A DOI-less work found
         this way is recorded from the OpenAlex / S2 records themselves.
      4. Slug fallback (filename → surname + year) for anything still
         missing.
      5. Flag `needs_doi: True` if no DOI ever resolved — the UI can
         then prompt the user to paste one in and re-run.

    Returns a dict that also includes `_provenance: {field: [sources]}`
    — per-field origin tracking so the viewer can flag which source
    contributed each metadata value (and which other sources verified
    it by returning the same value).

    Deliberately does NOT do any PDF text scanning (was fragile / OCR-
    prone). If /Info is blank AND the slug/filename doesn't match a
    Crossref search, we fail loudly rather than guessing from body text.
    """
    # PDF /Info stream: read the structured metadata block the typesetting
    # software embedded (title, author, doi). Used ONLY as a lookup seed
    # — we take its DOI (if any) to query Crossref, or its title to run a
    # Crossref search fallback. /Info is deliberately NOT added to the
    # source_dicts below, so its values never enter the final metadata's
    # provenance chain. Crossref (and eventually OA/SS) is the sole
    # source of record; /Info's role is "here's what to look up."
    pdf_info = _from_pdf_metadata(pdf)

    # Filename is NEVER a metadata source either (see comment on the
    # earlier _from_slug removal). Corpus data only comes from APIs.
    source_dicts: list[dict] = []
    api_hit = False
    cr = oa = ss = {}

    doi = (pdf_info.get("doi") or "").strip()
    if doi:
        cr, oa, ss = _collect_api_metadata(doi)
        if cr or oa or ss:
            api_hit = True

    # PDF text fallback: /Info was empty (or its DOI was bogus). Many
    # journals — Nature, Nature Neuroscience, older PLoS, most
    # preprints — deposit empty /Info streams even though the DOI is
    # plainly printed on page 1. Scan the first 3 pages for DOI-shaped
    # tokens and score them against masthead context; try candidates
    # in rank order until one resolves to a paper (not a dataset,
    # figure, or other non-paper resource). This is text-layer
    # extraction, not OCR — clean on born-digital PDFs, no-op on
    # scanned images.
    #
    # Try up to 5 candidates before giving up. Two things can force
    # us past the top-ranked one:
    #  * The top hit might be a truncation of the real DOI (PDF line-
    #    break split it) that Crossref returns nothing for.
    #  * The top hit might resolve to a non-paper resource — a PLoS
    #    figure DOI (.g001), a NIMH dataset DOI, a supplement — in
    #    which case we skip via _NON_PAPER_TYPES and try the next.
    if not api_hit:
        try:
            head_text = extract_pdf_text(pdf, max_pages=3)
            ranked = _rank_dois(head_text)
            for text_doi, _score in ranked[:5]:
                # GATE on Crossref: Crossref is the authoritative DOI
                # registry and returns strict 404 for unregistered
                # DOIs. OpenAlex does LAX matching (returns "close
                # enough" records for truncated DOIs — e.g.
                # `10.1371/journal` gets you some random PLoS paper).
                # Only pass the DOI to _collect_api_metadata (which
                # queries all three sources) after Crossref validates it.
                validate = crossref_lookup(text_doi)
                if not validate:
                    continue
                # Type-check on the validated record: reject non-paper
                # resources (PLoS figure `.g001`, NIMH dataset, grant).
                cr_type = str(validate.get("type") or "").lower()
                if cr_type in _NON_PAPER_TYPES:
                    continue
                # Journal front matter carries its own DOI and is typed
                # like an article. Bundled into a PDF, it outranks the
                # paper: snow-1996 took "Psychology, Public Policy, and
                # Law: Editors." (10.1037//1076-8971.8.4.c2) on 2026-09-24
                # and was renamed noauthorshipindicated-2002.
                if _is_front_matter((validate.get("title") or [""])[0]):
                    continue
                # Passed both gates — do the full 3-source lookup.
                cr, oa, ss = _collect_api_metadata(text_doi)
                if cr or oa or ss:
                    api_hit = True
                    break
        except Exception:
            pass  # PDF unreadable / no text layer — fall through to title search

    # Title-search fallback: still no DOI. Seed with /Info's title; when
    # that is empty (common on older / preprint / repository-copy PDFs),
    # with the largest-font block(s) on page 1. Each seed goes to all
    # three services in turn — see _resolve_by_title.
    if not api_hit:
        # /Info first, then page 1 — ALWAYS both. Page 1 used to be tried
        # only when /Info had no title at all, so a plausible-looking but
        # wrong /Info title ("download", a repository label) was the only
        # seed ever searched. On 2026-09-24 that left Guadagnoli & Lee's
        # Challenge Point unresolved although page 1 printed its exact
        # title and all three services had it.
        seed_titles: list[str] = []
        info_title = (pdf_info.get("title") or "").strip()
        if info_title:
            seed_titles.append(info_title)
        try:
            seed_titles += [t for t in _title_candidates_from_pdf_text(pdf) if t not in seed_titles]
        except Exception:
            pass
        for seed_title in seed_titles:
            cr, oa, ss = _resolve_by_title(seed_title)
            if cr or oa or ss:
                api_hit = True
                break

    for d in (cr, oa, ss):  # NO pdf_info here — it was seed-only
        if d:
            source_dicts.append(d)

    out, provenance = merge_with_provenance(*source_dicts)

    # Institution enrichment still runs on the merged dict (OA / SS
    # often have better affiliation data than Crossref).
    _merge_author_institutions(out, oa)
    _merge_author_institutions(out, ss)

    # Overall sources list — the union of every source that contributed
    # anything. Kept for display + interop; the per-field `_provenance`
    # below is the real tracker.
    out["sources"] = [d["source"] for d in source_dicts if d.get("source")]
    out["_provenance"] = provenance
    out.pop("source", None)

    # Flag if we still don't have a real DOI — UI uses this to surface
    # a "paste a DOI" prompt for the paper.
    resolved_doi = (out.get("doi") or "").strip()
    if not resolved_doi or resolved_doi in ("unknown",):
        out["needs_doi"] = True

    return out



