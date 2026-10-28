"""References read from a PDF's own text — the THIRD reference source.

## Where this sits relative to the other sources

Corpus resolves references from Crossref and Semantic Scholar. Both are
API-only and both are frequently incomplete: publishers deposit partial
reference lists, or none at all. Measured on a 57-paper corpus,
2026-08-25: 8 papers had NO deposited references, and 726 of 2929
reference lines carried a DOI and nothing else — no author, no title.

This module reads the PDF's printed reference list. It is ADDITIVE and
never authoritative: nothing here overwrites a Crossref or SS value.
Callers merge it in to (a) supply references for papers the APIs have
none for, and (b) fill in author/title on entries the APIs left bare.
See `citations.resolve_references` for the merge.

This reverses the "v0.1 policy: API-only, no PDF text parsing" recorded
in `extract_references.py` and `prefill_summary.render_summary`. That
policy held while references were display-only; it stopped making sense
once references became citation links.

## Measured accuracy (57-paper corpus, 2026-08-25)

    49/57 PDFs parsed        7 no locatable reference section
                             1 unreadable (scanned image, no text layer)
    3066 entries extracted   0.1% missing an author or year
    91.5% recall vs Crossref reference lists

KNOWN DEFECT — titles. 10.4% of entries (320/3066) carry a title that
is a parse fragment ("2", "pp", "907-915"). Their author and year are
correct; only `_title()` is wrong, on styles that print the year at the
END of the citation rather than after the authors. The 0.1% figure
above counts missing author/year and does NOT catch this. Tracked in
ROADMAP.md with a fix sketch. Callers should treat `title` as
best-effort; `author`, `year` and `doi` are the reliable fields.

Sampled disagreements with Crossref were checked by hand: they were
real references Crossref had not deposited, not parse errors. All 7
"no_section" papers already have complete Crossref lists, so the gap
costs nothing today.

Known-weak cases, both verified by hand rather than assumed:
  * Science-style numbered notes bundling several citations into ONE
    numbered item (knowlton-1993). 20 entries come back, but each is a
    bundle, so authors and years attach to the wrong citation. Do not
    trust that paper's extracted references. Tracked in ROADMAP.md.
  * Scanned PDFs with no text layer return status "unreadable". They
    are reported, never guessed at.

Library module — no CLI entry point.
"""
from __future__ import annotations

import re
import unicodedata

_HEADER = re.compile(
    r"(?im)^[\s\d.]*(references|bibliography|literature\s+cited|works\s+cited)"
    r"\s*(and\s+notes)?\s*:?\s*$")
_END = re.compile(
    r"(?im)^\s*(appendix\b|supplementary\b|supporting information\b|author note\b|"
    r"acknowledg(e)?ments?\b|figure legends?\b|footnotes?\b)")

# An entry starts with a surname followed by initials, in either of the
# two dominant conventions:
#   APA        "Aha, D. W., & Goldstone, R. L. (1992)."   surname COMMA initial-period
#   Vancouver  "Ahn W, Busemeyer JR, Wagenmakers E"       surname SPACE capitals
# Optionally preceded by a numeric label: "1." / "[12]" / "(3)".
_ENTRY_START = re.compile(
    r"^\s*(?:\[\d{1,3}\]|\(\d{1,3}\)|\d{1,3}[.)])?\s*"
    r"(?:van\s+|von\s+|de\s+|del\s+|della\s+|der\s+)?"      # nobiliary particles
    r"([A-Z][A-Za-z'’\-]{1,30})"                        # surname
    r"(?:,\s*[A-Z]\.|,?\s+[A-Z]{1,3}\b)"                     # , A.   |   AB
)

# Initials-FIRST convention (Science, PNAS): "L. R. Squire, Annu. Rev."
# or "R. Golman, G. Loewenstein, Information gaps:".
_ENTRY_START_INITIALS = re.compile(
    r"^\s*(?:\[\d{1,3}\]|\(\d{1,3}\)|\d{1,3}[.)])?\s*"
    r"(?:[A-Z]\.\s*){1,3}([A-Z][A-Za-z'’\-]{1,30})\b")

_DOI = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
_YEAR_PAREN = re.compile(r"\((\d{4})[a-z]?\)")
_YEAR_ANY = re.compile(r"\b(1[89]\d{2}|20\d{2})[a-z]?\b")
_TRAILING_NOISE = re.compile(
    r"\s*(\[PubMed:[^\]]*\]|PMID:\s*\d+|PMCID:\s*\S+)\s*", re.IGNORECASE)


def _fix_text(t: str) -> str:
    """Undo PDF text-extraction artifacts that break matching."""
    # Soft hyphens and zero-width characters are invisible but split
    # words and DOIs. eLife PDFs are full of both.
    # Strip every Unicode "format" (Cf) codepoint: soft hyphens,
    # zero-width spaces/joiners, BOM, and the bidi overrides some
    # producers wrap around every line (mirea-2024 has \u202d/\u202c on
    # each one, which stops "^References$" from ever matching).
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    t = t.replace("\u00ad", "")
    t = unicodedata.normalize("NFKC", t)
    # Orphaned combining diacritics ("Blo¨te"). We need these strings to
    # MATCH, not to render perfectly.
    t = re.sub(r"[¨ˆ˜´`]", "", t)
    return t


def _dehyphenate(t: str) -> str:
    """'ben-\\nefits' -> 'benefits'. Only when the continuation is
    lowercase, so 'top-\\ndown' survives as 'top-down'."""
    return re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", t)


def _pick_pattern(seg: str):
    """Choose ONE entry pattern per document.

    Mixing conventions is worse than picking the wrong one: a document
    parsed with two patterns splits mid-entry wherever the loser
    happens to match, producing fragments that look like real refs.
    Whichever pattern matches more line-starts wins."""
    lines = [ln.strip() for ln in seg.split("\n") if ln.strip()]
    a = sum(1 for ln in lines if _ENTRY_START.match(ln))
    b = sum(1 for ln in lines if _ENTRY_START_INITIALS.match(ln))
    return _ENTRY_START_INITIALS if b > a else _ENTRY_START


def _find_by_content(text: str) -> str:
    """Locate a reference list with no heading.

    Nature and Science frequently omit the word entirely. Falls back to
    the densest run of author-shaped lines in the last 60% of the
    document — reference lists are the only place that shape repeats
    dozens of times in a row."""
    lines = text.split("\n")
    start_at = int(len(lines) * 0.4)
    best_start, best_run, run, run_start = -1, 0, 0, -1
    for i in range(start_at, len(lines)):
        ln = lines[i].strip()
        hit = bool(_ENTRY_START.match(ln) or _ENTRY_START_INITIALS.match(ln))
        if hit:
            if run == 0:
                run_start = i
            run += 1
            if run > best_run:
                best_run, best_start = run, run_start
        elif run and not ln:
            pass                      # blank lines don't break a run
        elif run:
            run = max(0, run - 1)     # tolerate wrapped continuation lines
    # Ten consecutive author-shaped lines is far past coincidence.
    if best_run < 10 or best_start < 0:
        return ""
    return "\n".join(lines[best_start:])


def find_references_section(text: str) -> str:
    text = _fix_text(text)
    hits = list(_HEADER.finditer(text))
    if not hits:
        return _find_by_content(text)
    # Prefer the last header that leaves a substantial tail — papers
    # sometimes print "References" in a running footer on later pages.
    best = ""
    for h in hits:
        seg = text[h.end():]
        end = _END.search(seg)
        if end and end.start() > 400:
            seg = seg[:end.start()]
        if len(seg) > len(best):
            best = seg
    # A header was found but the tail is too short to be a real list —
    # usually a running footer. Fall back to content detection.
    if len(best) < 400:
        return _find_by_content(text) or best
    return best


def split_entries(seg: str, pattern=None) -> list[str]:
    seg = _dehyphenate(seg)
    pattern = pattern or _pick_pattern(seg)
    entries, cur = [], []
    for ln in seg.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if pattern.match(s):
            if cur:
                entries.append(" ".join(cur))
            cur = [s]
        elif cur:
            cur.append(s)
    if cur:
        entries.append(" ".join(cur))

    # Every real reference carries a year. A fragment without one is a
    # wrapped continuation that the author-shape pattern mis-split (a
    # line beginning "Frank MJ. ..." looks like an entry start), so fold
    # it back into the previous entry instead of emitting a bogus ref.
    merged: list[str] = []
    for e in entries:
        e = re.sub(r"\s+", " ", e).strip()
        if merged and not _YEAR_ANY.search(e):
            merged[-1] = merged[-1] + " " + e
        else:
            merged.append(e)
    return [e for e in merged if len(e) >= 25]


def _first_surname(raw: str, pattern=None) -> str:
    for pat in ([pattern] if pattern else [_ENTRY_START, _ENTRY_START_INITIALS]):
        m = pat.match(raw)
        if m:
            return m.group(1)
    return ""


def _year(raw: str):
    m = _YEAR_PAREN.search(raw)
    if m:
        return int(m.group(1))
    # Vancouver / eLife put the year bare, after the author list. Take
    # the FIRST plausible year — later ones are volume/page noise.
    m = _YEAR_ANY.search(raw)
    return int(m.group(1)) if m else None


def _doi(raw: str) -> str:
    m = _DOI.search(raw)
    if not m:
        # DOIs are routinely split across a line break, leaving a space.
        m = _DOI.search(re.sub(r"\s+", "", raw))
    if not m:
        return ""
    return m.group(1).rstrip(".,;)]").lower()


def _title(raw: str, year) -> str:
    """Text between the year marker and the container (journal/book).

    Deliberately conservative: a wrong title is worse than a blank one
    because it would be shown to the user as fact."""
    body = _TRAILING_NOISE.sub(" ", raw)
    m = _YEAR_PAREN.search(body)
    if m:
        after = body[m.end():]
    elif year:
        m2 = re.search(rf"\b{year}[a-z]?\b\.?\s*", body)
        after = body[m2.end():] if m2 else ""
    else:
        return ""
    after = after.lstrip(" .;:").strip()
    # Title runs to the first sentence-ending period. Avoid splitting on
    # "J. Neurosci." style abbreviations by requiring the period to be
    # followed by whitespace + capital, and the piece to be long enough
    # to be a title rather than an initial.
    tm = re.match(r"(.{10,400}?)\.\s+(?=[A-Z“\"]|In\b)", after)
    title = (tm.group(1) if tm else after.split(". ")[0]).strip()
    title = re.sub(r"\s+", " ", title).strip(" .,;:")
    return title[:300]


def parse_entry(raw: str, pattern=None) -> dict:
    y = _year(raw)
    return {"raw": raw, "author": _first_surname(raw, pattern), "year": y,
            "title": _title(raw, y), "doi": _doi(raw)}


# Below this many extractable characters a PDF is treated as unreadable
# (scanned images, or a producer that embeds text as vectors). Real
# articles run tens of thousands. catrambone-1995 yields 12.
MIN_READABLE_CHARS = 600


def extract_from_text(text: str):
    """Extract references from a PDF's full text.

    Returns (refs, status). Status is one of:
        "ok"            refs were found
        "unreadable"    the PDF has essentially no extractable text
        "no_section"    text is fine, no reference list could be located

    The caller MUST distinguish these. "unreadable" means OCR is needed
    and nothing about this paper's references is known — silently
    returning an empty list would look identical to a paper that
    genuinely cites nothing."""
    if len((text or "").strip()) < MIN_READABLE_CHARS:
        return [], "unreadable"
    seg = find_references_section(text)
    if not seg:
        return [], "no_section"
    pattern = _pick_pattern(_dehyphenate(seg))
    refs = [parse_entry(e, pattern) for e in split_entries(seg, pattern)]
    return refs, ("ok" if refs else "no_section")


def pdf_text(pdf) -> str:
    """Full text of a PDF, or "" if it cannot be opened.

    Imports pymupdf under its modern name. `extract_metadata.py` still
    uses the legacy `fitz` alias, which PyMuPDF has deprecated — see the
    ROADMAP entry. New code uses `pymupdf` so it does not add to that
    debt."""
    try:
        import pymupdf
    except ImportError:                      # pragma: no cover
        try:
            import fitz as pymupdf           # older PyMuPDF
        except ImportError:
            return ""
    try:
        doc = pymupdf.open(pdf)
    except Exception:
        return ""
    try:
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        return ""
    finally:
        try:
            doc.close()
        except Exception:
            pass


def extract_references_from_pdf(pdf):
    """(refs, status) for a PDF path. See `extract_from_text` for the
    status values — callers must distinguish "unreadable" from an
    empty reference list."""
    return extract_from_text(pdf_text(pdf))
