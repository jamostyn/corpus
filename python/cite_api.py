"""Citation data: a paper's summary as CSL-JSON, for formatting citations.

Requirement (2026-10-29): see how a paper is cited in several styles, in
the text and in a reference list, on its info page; export the references
of every paper in a project. Formatting is done by citeproc-js with the
official CSL style files (src/cite.js); this module only says WHAT the
paper is, in the shape CSL expects — one mapping for both the paper page
and the project export.

Title case. Papers store titles as published, often Title Case; APA,
Vancouver and IEEE want sentence case, and no CSL engine can lower-case a
title safely (it cannot tell "United States" from "United Results"). So
each item also carries `title-sentence`, made here: lower-case every word
except the first, the first after a colon, acronyms, mixed-case words,
words with digits, and words the paper's own ABSTRACT capitalises
mid-sentence — the abstract is ordinary prose, so a capital there is a
proper noun ("Bayesian", "Parkinson's", "Stroop").

  GET /api/paper/<slug>/csl   -> {item}
  GET /api/project/<pid>/csl  -> {title, items: [...]}  (paper members)
"""
from __future__ import annotations

import logging
import re

from flask import Blueprint, abort, jsonify

from _api_common import require_corpus_or_abort
from _paths import summaries_dir

logger = logging.getLogger("corpus.cite")

cite_bp = Blueprint("cite", __name__)

# Summary `kind` -> CSL item type.
CSL_TYPES = {
    "article": "article-journal", "preprint": "article", "proceedings": "paper-conference",
    "chapter": "chapter", "book": "book", "thesis": "thesis", "report": "report",
}

_UNK = {"", "unknown", "none", "null"}


def _val(fm: dict, key: str) -> str:
    v = fm.get(key)
    v = "" if v is None else str(v).strip()
    return "" if v.lower() in _UNK else v


# ---------- title case ----------

_WORD_RE = re.compile(r"[A-Za-z][\w'’\-]*")


def proper_words(abstract: str) -> set:
    """Words the abstract capitalises when they are not opening a sentence."""
    out = set()
    for sentence in re.split(r"(?<=[.!?])\s+", abstract or ""):
        words = _WORD_RE.findall(sentence)
        for w in words[1:]:
            if w[0].isupper():
                out.add(w.lower())
    return out


def _keep_case(word: str, proper: set) -> bool:
    core = word.strip("\"'“”‘’()[]")
    if not core:
        return True
    letters = [c for c in core if c.isalpha()]
    if len(letters) >= 2 and all(c.isupper() for c in letters):      # ALCOVE, fMRI? (all caps)
        return True
    if any(c.isupper() for c in core[1:]):                             # McGill, iPhone, fMRI
        return True
    if any(c.isdigit() for c in core):                                 # COVID-19, 3D
        return True
    return core.lower() in proper


def sentence_case(title: str, abstract: str = "") -> str:
    """`title` in sentence case, keeping proper nouns (see module doc).

    A title already in sentence case comes back unchanged."""
    if not title:
        return title
    proper = proper_words(abstract)
    out, start = [], True
    for tok in re.split(r"(\s+)", title):
        if not tok or tok.isspace():
            out.append(tok)
            continue
        # Each part of a hyphenated word is judged on its own:
        # "fMRI-Measured" -> "fMRI-measured", "Self-Report" -> "Self-report".
        parts = tok.split("-")
        for i, part in enumerate(parts):
            if (start and i == 0) or _keep_case(part, proper):
                continue
            parts[i] = part[:1].lower() + part[1:] if part[:1].isupper() else part
        out.append("-".join(parts))
        start = tok.endswith((":", "?", "!", "—", "–")) or tok in ("-", "–", "—")
    return "".join(out)


# ---------- the CSL item ----------

def _authors(fm: dict) -> list:
    detailed = fm.get("authors_detailed")
    if isinstance(detailed, list) and detailed and all(isinstance(a, dict) for a in detailed):
        out = []
        for a in detailed:
            fam, giv = str(a.get("family") or "").strip(), str(a.get("given") or "").strip()
            if fam and fam.lower() not in _UNK:
                out.append({"family": fam, **({"given": giv} if giv and giv.lower() not in _UNK else {})})
        if out:
            return out
    out = []
    for s in fm.get("authors_full") or []:
        # "Abir Y." / "Baldassano C.A." -> family + initials
        parts = str(s).strip().rsplit(" ", 1)
        if len(parts) == 2 and re.fullmatch(r"(?:[A-Z]\.?-?)+", parts[1]):
            initials = ".".join(c for c in parts[1] if c.isalpha()) + "."
            out.append({"family": parts[0], "given": initials})
        elif parts[0]:
            out.append({"literal": str(s).strip()})
    return out


def csl_item(slug: str, fm: dict) -> dict:
    """One paper as a CSL-JSON item. Unknown fields are left out, never
    printed as "unknown"."""
    item = {"id": slug, "type": CSL_TYPES.get(_val(fm, "kind").lower(), "article-journal")}
    title = _val(fm, "title")
    if title:
        item["title"] = title
        item["title-sentence"] = sentence_case(title, _val(fm, "abstract"))
    authors = _authors(fm)
    if authors:
        item["author"] = authors
    year = _val(fm, "year")
    if re.fullmatch(r"\d{4}", year):
        item["issued"] = {"date-parts": [[int(year)]]}
    container = _val(fm, "publisher")
    if container:
        item["container-title"] = container
        # A chapter's container is a BOOK title, which sentence-case
        # styles also lower-case (APA: "In … (Eds.), Formal approaches in
        # categorization"); a journal name never is.
        if item["type"] == "chapter":
            item["container-title-sentence"] = sentence_case(container)
    for src, dst in (("volume", "volume"), ("issue", "issue")):
        v = _val(fm, src)
        if v:
            item[dst] = v
    pages = _val(fm, "pages")
    if re.search(r"\d\s*[-–]\s*\d", pages):
        item["page"] = re.sub(r"\s*[-–]\s*", "-", pages)
    else:
        number = _val(fm, "article_number") or pages
        if number:
            item["number"] = number
    doi = _val(fm, "doi")
    if doi:
        item["DOI"] = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    org = _val(fm, "publisher_org")
    if org and item["type"] in ("book", "chapter", "report", "thesis"):
        item["publisher"] = org
    return item


def _read(slug: str):
    from papers_api import _read_summary
    md = summaries_dir() / f"{slug}.md"
    if not md.exists():
        return None
    got = _read_summary(md)
    return got[0] if got else None


@cite_bp.route("/api/paper/<slug>/csl")
def paper_csl(slug):
    require_corpus_or_abort()
    fm = _read(slug)
    if fm is None:
        abort(404)
    return jsonify({"item": csl_item(slug, fm)})


@cite_bp.route("/api/project/<pid>/csl")
def project_csl(pid):
    """Every paper in a project, as CSL items (notes and documents are
    not citable works and are left out)."""
    require_corpus_or_abort()
    from projects_api import _project_path_or_404, _read_project
    data = _read_project(_project_path_or_404(pid))
    if data is None:
        abort(404, description="project_missing")
    items = []
    for slug in data["members"].get("paper", []):
        fm = _read(slug)
        if fm is not None:
            items.append(csl_item(slug, fm))
    logger.info("project_csl pid=%s items=%d", pid, len(items))
    return jsonify({"title": data["title"], "items": items})
