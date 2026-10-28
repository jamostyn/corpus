#!/usr/bin/env python3
"""References for a paper — API-only (Crossref).

v0.1 policy (per Jack, 2026-08-07): no PDF text parsing. References come
exclusively from Crossref's `/works/{DOI}` response, `message.reference[]`.

When Crossref has the refs (deposited by the publisher during metadata
submission), each entry can be a mix of:
  - fully structured: `article-title`, `author`, `year`, `DOI`, `journal-title`
  - partially structured: any subset of the above
  - unstructured: only an `unstructured` string (raw citation text)

When Crossref DOESN'T have refs (publisher didn't deposit them — common
for older articles, non-Elsevier / non-Springer works, most books,
theses), this returns []. In that case the summary MD is written with
zero refs and `refs_source: none`. Later phases (Semantic Scholar,
OpenAlex integrations) will fill some of those gaps.

Library module — no CLI entry point. Called from
`prefill_summary.render_summary` during the extract pipeline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Reference:
    """Corpus reference — a single cited work.

    Fields tracked separately so `to_md_line()` can format the schema
    line consistently, and downstream tools can access structured
    metadata without re-parsing the markdown line."""
    author_block: str = ""         # first-author surname, or full list if we have it
    year:         int | None = None
    title:        str = ""
    doi:          str = ""
    doi_source:   str = ""         # "" (no DOI) | "structured" (Crossref DOI field)
                                    # | "text-scan" (regex-extracted from unstructured)
    kind:         str = ""         # "book" | "chapter" | "series" | "" (unknown/article)
    unstructured: bool = False     # True → `title` holds a raw citation string,
                                    #        not a real title (rendered differently)

    def short_authors(self) -> str:
        """Render the authors piece of the display line.

        For Crossref-sourced refs the `author` field is usually just a
        single surname (Crossref's convention when publishers don't
        deposit full author lists per ref). We surface it as-is; if
        empty, show `[unparsed authors]` to signal what's missing."""
        block = (self.author_block or "").strip().rstrip(",")
        if not block:
            return "[unparsed authors]"
        return block

    def to_md_line(self) -> str:
        """Schema line. Trailing metadata is one of:
          - ` — DOI: <doi>`             when a DOI came from the structured field
          - ` — DOI: <doi> (extracted)` when a DOI was regex-fished from unstructured text
          - ` — <kind>`                 when no DOI but we know the kind (book/chapter/series)
          - ` — no DOI`                 when no DOI and no kind

        Body shapes:
          - full:              `- **[<author> <year> <title>]** <trail>`
          - title, no author:  `- **[<title>]** <trail>`
          - author, no title:  `- **[<author> <year>]** <trail>`
          - DOI only:          `- <trail>`   (publisher deposited nothing else)
          - unstructured:      `- <raw citation> <trail>`
        """
        doi = (self.doi or "").strip() or "unknown"
        if doi != "unknown":
            trail = f" — DOI: {doi}"
            if self.doi_source == "text-scan":
                trail += " (extracted)"
        elif self.kind:
            trail = f" — {self.kind}"
        else:
            trail = " — no DOI"

        if self.unstructured:
            body = self.title.strip().rstrip(".")
            return f"- {body}{trail}"

        author = (self.author_block or "").strip().rstrip(",")
        title  = self.title.strip().rstrip(".")
        year   = f" {self.year}" if self.year else ""

        if author and title:
            return f"- **[{author}{year} {title}]**{trail}"
        if title:
            return f"- **[{title}]**{trail}"
        if author:
            return f"- **[{author}{year}]**{trail}"
        # Nothing structured beyond the DOI itself.
        return f"-{trail}"


# ---------- Reference-line parsing (inverse of to_md_line) ----------
#
# `to_md_line()` above is the ONLY writer of the reference-line format,
# and `parse_ref_line()` below is the ONLY reader. They live in the same
# file deliberately: the format is one fact, and a change to either
# without the other is caught by the round-trip test in
# tests/test_ref_line_roundtrip.py.
#
# Before 2026-08-25 a second parser existed in JS (`parseRefs` in
# src/paper-detail.js) with its own copy of these regexes. It was
# removed — the server now parses once and hands structured refs to the
# frontend.

_REFS_HEADING = "## References"

# Trailing ` — DOI: <doi>` / ` — DOI: <doi> (extracted)`.
_TRAIL_DOI = re.compile(r"(?:^|—\s*)DOI:\s*(\S+?)(\s*\(extracted\))?\s*$", re.IGNORECASE)
# Trailing ` — book` / ` — chapter` / ` — series` / ` — article` / ` — no DOI`.
_TRAIL_KIND = re.compile(r"—\s*(book|chapter|series|article|no DOI)\s*$", re.IGNORECASE)
# A structured body is wrapped in **[ ... ]**.
_STRUCTURED_BODY = re.compile(r"^\*\*\[(.*)\]\*\*$", re.DOTALL)
# Year anchor inside a structured body: `<author> <year> <title>`.
_YEAR_SPLIT = re.compile(r"^(.*?)\s*\b((?:19|20)\d{2})\b\s*(.*)$", re.DOTALL)


def parse_ref_line(line: str) -> Reference | None:
    """Parse one rendered reference line back into a `Reference`.

    Exact inverse of `Reference.to_md_line()` for everything that
    survives rendering. What does NOT survive, and why that's fine:

      * `unstructured` refs that also carried a DOI render identically
        to a DOI-only structured ref with no author/title, so the flag
        is reconstructed from the presence of the `**[...]**` wrapper
        rather than from the original object.
      * A structured ref whose author contains a 4-digit year would
        split at the wrong place. Crossref author blocks are surnames,
        so this does not occur in practice — but it is why title/author
        matching is not used for corpus linking (DOI is).

    Returns None for a line that isn't a reference bullet."""
    raw = (line or "").strip()
    if not raw.startswith("-"):
        return None
    rest = raw[1:].strip()
    if not rest:
        return None

    doi, doi_source, kind = "", "", ""
    m = _TRAIL_DOI.search(rest)
    if m:
        doi = _norm_doi(m.group(1))
        doi_source = "text-scan" if m.group(2) else "structured"
        rest = rest[:m.start()].strip().rstrip("—-").strip()
    else:
        m = _TRAIL_KIND.search(rest)
        if m:
            tag = m.group(1).lower()
            if tag != "no doi":
                kind = tag
            rest = rest[:m.start()].strip().rstrip("—-").strip()

    body = _STRUCTURED_BODY.match(rest)
    if not body:
        # Unstructured (raw citation text), or a DOI-only line whose
        # body is empty.
        text = rest.strip()
        if not text and not doi:
            return None
        return Reference(title=text, doi=doi, doi_source=doi_source,
                         kind=kind, unstructured=bool(text))

    inner = body.group(1).strip()
    author, year, title = "", None, ""
    ym = _YEAR_SPLIT.match(inner)
    if ym:
        author = ym.group(1).strip()
        year = int(ym.group(2))
        title = ym.group(3).strip()
    else:
        # No year anchor: `**[<title>]**` (title-only) is the shape
        # to_md_line emits when there is no author. We cannot tell a
        # bare author from a bare title, and to_md_line only omits the
        # year for author-only refs, so treat it as a title.
        title = inner
    return Reference(author_block=author, year=year, title=title,
                     doi=doi, doi_source=doi_source, kind=kind,
                     unstructured=False)


def parse_references_section(body: str) -> list[Reference]:
    """Every reference in a summary MD body's `## References` section.

    Takes the markdown BODY (frontmatter already stripped, as returned
    by `_fm.parse_frontmatter`). Returns [] when the section is absent
    or empty — a paper whose publisher deposited no references is a
    normal state, not an error."""
    if not body:
        return []
    idx = body.find(_REFS_HEADING)
    if idx == -1:
        return []
    out: list[Reference] = []
    for line in body[idx + len(_REFS_HEADING):].split("\n"):
        ref = parse_ref_line(line)
        if ref is not None:
            out.append(ref)
    return out


# ---------- Crossref reference extraction ----------

# DOI normalization is shared with the citation index (citations.py) and
# every API client — it lives in _api_http as the single source of truth.
# A second normalizer here that disagreed by one rule would silently
# break intra-corpus citation matching.
from _api_http import _UNICODE_HYPHENS, normalize_doi as _norm_doi  # noqa: E402


# DOI embedded in raw unstructured text — Crossref sometimes leaves
# `https://doi.org/10.xxxx/yyyy` inside an entry's `unstructured` field
# without also filling the structured `DOI` slot. Grabbing it here is
# parsing an API response, not PDF text (which is banned per v0.1 policy).
#
# DOI syntax per Crossref: starts with `10.<registrant>/<suffix>`; the
# suffix is usually [-._;()/:A-Z0-9]+ in practice. Trailing sentence
# punctuation (. , ; ) ]) is stripped after the match.
_DOI_URL_OR_BARE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?"
    r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
    re.IGNORECASE,
)


def _doi_in_unstructured(text: str) -> str:
    if not text:
        return ""
    # Normalize Unicode hyphens to ASCII FIRST — Crossref sometimes returns
    # DOIs with U+2010 (HYPHEN) etc. inside the raw text. If we don't
    # translate before regex, the [A-Za-z0-9-] character class stops at
    # the first fancy hyphen and truncates the DOI.
    text = text.translate(_UNICODE_HYPHENS)
    m = _DOI_URL_OR_BARE.search(text)
    if not m:
        return ""
    return _norm_doi(m.group(1).rstrip(".,;)]"))


def _year_from_entry(entry: dict) -> int | None:
    """Crossref exposes reference year as a top-level `year` string,
    or embedded in `issued` for the parent work — here we only look at
    the ref's own `year` field."""
    y = entry.get("year")
    if not y:
        return None
    m = re.search(r"(19|20)\d{2}", str(y))
    return int(m.group(0)) if m else None


def _title_from_entry(entry: dict) -> str:
    """Prefer the fully-structured `article-title` (or `volume-title` for
    book chapters). Fall back to `series-title` if that's all we have.
    Returns "" if no structured title is present."""
    for key in ("article-title", "volume-title", "series-title"):
        v = (entry.get(key) or "").strip()
        if v:
            return v
    return ""


def _detect_kind(entry: dict) -> str:
    """Detect the cited work's kind from Crossref's structured fields.

    Signals (checked in order):
      - `ISBN` field                       → book (definitive)
      - `ISSN` or `journal-title`          → article
      - `volume-title` + `article-title`   → chapter (chapter in a book)
      - `volume-title` alone               → book (title of the whole book)
      - `series-title` alone               → series

    Returns "" (unknown) for the common Wiley-style DOI-only entries —
    we'd need to resolve each DOI individually to know the type, and
    that's a whole separate enrichment step."""
    if entry.get("ISBN") or entry.get("isbn"):
        return "book"
    if entry.get("ISSN") or entry.get("issn") or entry.get("journal-title"):
        return "article"
    if entry.get("volume-title"):
        return "chapter" if entry.get("article-title") else "book"
    if entry.get("series-title") and not entry.get("article-title"):
        return "series"
    return ""


def _reference_from_entry(entry: dict) -> Reference | None:
    """Map one Crossref reference entry → Reference. Returns None only
    if the entry is completely empty (no DOI, no unstructured, no title)
    — should be rare."""
    doi          = _norm_doi(entry.get("DOI", ""))
    doi_source   = "structured" if doi else ""
    title        = _title_from_entry(entry)
    year         = _year_from_entry(entry)
    author       = (entry.get("author") or "").strip()
    kind         = _detect_kind(entry)
    unstructured = (entry.get("unstructured") or "").strip()

    # If Crossref didn't fill the structured DOI slot, look for a DOI
    # embedded in the unstructured text (common when a publisher deposited
    # the ref as raw text with a doi.org URL inside). Note the source so
    # the UI can badge the ref as regex-extracted rather than authoritative.
    if not doi and unstructured:
        doi = _doi_in_unstructured(unstructured)
        if doi:
            doi_source = "text-scan"

    if title or doi:
        return Reference(
            author_block=author,
            year=year,
            title=title,
            doi=doi,
            doi_source=doi_source,
            kind=kind,
            unstructured=False,
        )

    if unstructured:
        # Only raw text available. Store it as the title with the flag so
        # to_md_line() renders it plainly (no [...] bold wrapping).
        return Reference(
            author_block="",
            year=year,      # Crossref sometimes gives year even in unstructured entries
            title=unstructured,
            doi=doi,
            doi_source=doi_source,
            kind=kind,
            unstructured=True,
        )

    return None


def extract_references_from_crossref(doi: str) -> list[Reference]:
    """Fetch structured references for a paper by DOI. Returns [] if the
    Crossref lookup fails, the DOI isn't registered, or the publisher
    didn't deposit references."""
    if not doi:
        return []
    # Late import to avoid a circular ref at module load (extract_metadata
    # imports from us for the Reference type; we import back only for the
    # HTTP helper).
    from extract_metadata import crossref_lookup
    msg = crossref_lookup(doi)
    if not msg:
        return []
    raw_refs = msg.get("reference") or []
    out: list[Reference] = []
    for r in raw_refs:
        ref = _reference_from_entry(r)
        if ref is not None:
            out.append(ref)
    return out


