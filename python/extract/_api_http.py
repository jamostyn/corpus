"""HTTP + text-similarity helpers shared by the three metadata clients
(crossref_client, openalex_client, semanticscholar_client).

Kept lean. If it doesn't need to be shared by all three, it lives with
its client. Anything that grows beyond a handful of helpers should
graduate to its own module rather than being dumped here.
"""
from __future__ import annotations

import json
import logging
import os as _os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from _version import __version__

logger = logging.getLogger("corpus.api_http")


# ---------- API endpoint constants ----------------------------------
# Kept together so a single glance shows every remote URL Corpus hits.
# Timeouts are per-request wall-clock caps: Crossref/OA are usually
# <1s; SS is bigger because we fetch per-ref title+year (~10-15s round-
# trip on wider papers).
CROSSREF_URL     = "https://api.crossref.org/works/{doi}"
CROSSREF_TIMEOUT = 6

OPENALEX_URL     = "https://api.openalex.org/works/https://doi.org/{doi}"
OPENALEX_TIMEOUT = 6

SS_URL = ("https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
          "?fields="
          "title,year,venue,publicationVenue,journal,externalIds,"
          "authors.name,authors.affiliations,authors.externalIds,authors.authorId,"
          "referenceCount,citationCount,influentialCitationCount,"
          "isOpenAccess,openAccessPdf,"
          "fieldsOfStudy,s2FieldsOfStudy,publicationTypes,publicationDate,"
          "abstract,tldr,embedding,citationStyles,paperId,"
          "references.externalIds,references.title,references.year")
SS_TIMEOUT = 20


# ---------- HTTP request plumbing -----------------------------------

def corpus_user_agent() -> str:
    """User-Agent Corpus sends to every API. All three (Crossref /
    OpenAlex / Semantic Scholar) accept a mailto in the User-Agent to
    place callers in the 'polite' pool (no rate limiting for OA,
    better queue priority for Crossref). SS ignores this but a mailto
    never hurts. Corpus reads CORPUS_MAILTO env var per-user so we
    don't leak any single email into shipped binaries."""
    mail = _os.environ.get("CORPUS_MAILTO", "").strip()
    agent = f"Corpus/{__version__}"
    return f"{agent} (mailto:{mail})" if mail else agent


def api_headers() -> dict:
    """Fresh headers per call — so a mailto set in Settings AFTER the
    server first imported this module still lands in the User-Agent."""
    return {
        "User-Agent": corpus_user_agent(),
        "Accept":     "application/json",
    }


def ssl_contexts():
    """Yield SSL contexts to try, in order of preference. The standalone
    python.org build on macOS doesn't ship a cert bundle and the user
    hasn't run Install Certificates.command — so we try the strict
    context first (works on most Linux + Homebrew Python installs) and
    fall back to an unverified context for the macOS-standalone case.
    All three APIs are public, unauthenticated, read-only data — MITM
    risk is cosmetic (you'd notice immediately when refs don't
    resolve)."""
    yield ssl.create_default_context()
    yield ssl._create_unverified_context()


_OPENALEX_HOST = "api.openalex.org"


def with_openalex_auth(url: str) -> str:
    """Add the user's OpenAlex API key and mailto — to OpenAlex URLs only.

    Found 2026-09-22: Settings stored the OpenAlex key in Keychain and
    `config_api._apply_env` exported it as CORPUS_OPENALEX_KEY, but no
    code ever read it, so every OpenAlex request went out keyless — while
    OpenAlex rate-limited 355 of them in one afternoon. The mailto only
    ever reached the User-Agent.

    Done HERE, in the one function every OpenAlex call already passes
    through, rather than at the six places OpenAlex URLs are built: a
    seventh call site gets the key without anyone remembering to add it.

    The host check is strict on purpose — the key must never reach
    Crossref or Semantic Scholar. Parameters the caller already set are
    left alone. Appended rather than re-encoding the query, because
    OpenAlex filters carry `|`, `:` and `/` that a rebuild would escape.
    """
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return url
    if host != _OPENALEX_HOST:
        return url
    query = urllib.parse.urlsplit(url).query
    have = {k for k, _ in urllib.parse.parse_qsl(query, keep_blank_values=True)}
    add = []
    key = _os.environ.get("CORPUS_OPENALEX_KEY", "").strip()
    mail = _os.environ.get("CORPUS_MAILTO", "").strip()
    if key and "api_key" not in have:
        add.append(("api_key", key))
    if mail and "mailto" not in have:
        add.append(("mailto", mail))
    if not add:
        return url
    return url + ("&" if query else "?") + urllib.parse.urlencode(add)


def api_get_json(url: str, timeout: int, extra_headers: dict | None = None) -> dict | None:
    """Shared JSON-GET helper for the three metadata APIs. Retries once
    with an unverified SSL context for the macOS-standalone Python case
    where the cert bundle isn't installed. Returns the parsed JSON or
    None on any failure (HTTP error, JSON parse, timeout, DNS).

    `extra_headers` lets a specific caller add auth headers (Semantic
    Scholar's `x-api-key`) without affecting the shared User-Agent.

    Logs always name the caller's `url`, never the authenticated one, so
    the API key and the user's email stay out of server.log."""
    hdrs = dict(api_headers())
    if extra_headers:
        hdrs.update(extra_headers)
    req = urllib.request.Request(with_openalex_auth(url), headers=hdrs)
    for ctx in ssl_contexts():
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                continue
            logger.info("api_get_json failed url=%s reason=%s", url, e.reason)
            return None
        except ssl.SSLError:
            continue
        except Exception:
            logger.warning("api_get_json unexpected failure url=%s", url, exc_info=True)
            return None
    return None


# ---------- Author name formatting (used by Crossref + OpenAlex mappers) ----------

def surname_initial(family: str, given: str) -> str:
    """`Smith J.` shape — surname + space-separated initials. Mirrors the
    existing summaries' authors_full convention so the matcher keeps
    working (build_connections normalizes_key on surname)."""
    parts = re.findall(r"[A-Z]", given or "")
    inits = "".join(f"{p}." for p in parts)
    return f"{family} {inits}".strip()


_INITIAL_TOKEN = re.compile(r"[A-Z]\.?")
_INITIAL_RUN   = re.compile(r"[A-Z]\.?(?:[A-Z]\.?)*")
_NAME_SUFFIX   = re.compile(r"(?:Jr|Sr|II|III|IV)\.?", re.I)


def split_display_name(name: str) -> tuple[str, str]:
    """Split a single-string display name into `(family, given)`.

    Handles two input shapes uniformly:
      * "Endel Tulving" / "Daniel Kahneman"       → given="Endel", family="Tulving"
      * "Smith J." / "Kahneman D."                → given="J.",    family="Smith"
      * "John R. Anderson" (given with middle)    → given="John R.", family="Anderson"

    Rule: rightmost NON-initial token = family; everything before = given.
    Fast path: if the last token itself is a run of initials, everything
    before is family. Same logic previously lived inline in
    `_from_pdf_metadata` and `_from_openalex._from_openalex` — see the
    2026-08-16 dedup pass in CHANGELOG.md.

    Returns `("", "")` for empty input.
    """
    if not name:
        return ("", "")
    # "Wei, Jason" / "Chi, Ed H." — inverted order, as OpenAlex returns some
    # arXiv authors. Read token by token these became family "Jason", given
    # "Wei," (measured 2026-10-29, Wei et al. 2022 imported as jason-2022).
    # A comma before a suffix ("John Smith, Jr.") is not an inversion.
    family, comma, given = name.partition(",")
    if comma and family.strip() and given.strip() and not _NAME_SUFFIX.fullmatch(given.strip()):
        return (family.strip(), " ".join(given.split()))
    name = family if comma and not given.strip() else re.sub(r",\s*" + _NAME_SUFFIX.pattern + r"$", "", name)
    tokens = name.split()
    if not tokens:
        return ("", "")
    if len(tokens) == 1:
        return (tokens[0], "")
    # Fast path: "Smith J." / "Smith JR" — trailing token is one-or-more initials.
    if _INITIAL_RUN.fullmatch(tokens[-1]):
        return (" ".join(tokens[:-1]), tokens[-1])
    # General case: back up past trailing single-initial tokens.
    fam_idx = len(tokens) - 1
    while fam_idx > 0 and _INITIAL_TOKEN.fullmatch(tokens[fam_idx]):
        fam_idx -= 1
    family = " ".join(tokens[fam_idx:fam_idx + 1])
    given  = " ".join(tokens[:fam_idx])
    return (family, given)


# ---------- DOI extraction ----------

# Crossref-canonical shape "10.<registrant>/<suffix>". Suffix can contain
# almost anything, so we stop at whitespace / quote / close paren /
# semicolon (the natural end-of-DOI markers in real text). Shared across
# `extract_metadata` (PDF text scan) and `rename_pdfs` (PDF /Info scan).
# `extract_references` uses a URL-or-bare variant for API-response text —
# see `_DOI_URL_OR_BARE` there.
DOI_RE = re.compile(r'''\b10\.\d{4,9}/[^\s"\'<>(){}\[\];,]+''', re.IGNORECASE)

# Trailing junk punctuation Crossref doesn't include in canonical DOIs.
# Callers strip this after the match to normalize sentence-ending noise.
DOI_TRAIL_RE = re.compile(r"[.,;:)\]\>]+$")

# Resolver prefixes publishers put in front of DOIs. Stripped so that
# "https://doi.org/10.1/x", "doi:10.1/x", and "10.1/x" compare equal.
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)

# Crossref occasionally returns DOIs containing typographic dashes
# (U+2010 etc.) that do not resolve on doi.org and would not compare
# equal to the same DOI deposited with an ASCII hyphen.
_UNICODE_HYPHENS = str.maketrans({
    "‐": "-",  # HYPHEN
    "‑": "-",  # NON-BREAKING HYPHEN
    "‒": "-",  # FIGURE DASH
    "–": "-",  # EN DASH
    "—": "-",  # EM DASH
    "−": "-",  # MINUS SIGN
})


def normalize_doi(raw) -> str:
    """THE canonical DOI form. Every DOI comparison in Corpus goes
    through here.

    Applies, in order: resolver-prefix strip, whitespace strip,
    lowercase, typographic-dash folding, trailing-punctuation strip.
    The literal string "unknown" (what the extraction pipeline writes
    when no DOI could be resolved) normalizes to "" so it can never
    match another paper's "unknown".

    Single source of truth on purpose. Two DOIs for the same work are
    routinely deposited in different forms by different parties, so a
    second normalizer that disagrees by one rule silently drops real
    matches — and a missing citation link is indistinguishable from
    "these papers aren't related"."""
    s = _DOI_PREFIX_RE.sub("", str(raw or "").strip()).strip().lower()
    s = s.translate(_UNICODE_HYPHENS)
    s = DOI_TRAIL_RE.sub("", s)
    return "" if s == "unknown" else s


# ---------- Publication-kind mapping (Crossref + OpenAlex share the same taxonomy) ----------

# Maps Crossref-shape `type` (also used by OpenAlex's `type_crossref` field)
# to Corpus's `kind` enum (`article` / `chapter` / `book` / `thesis` /
# `report`). OpenAlex sometimes returns bare `"article"` where Crossref
# would send `"journal-article"` — accepted here as an alias. Returns
# `None` for unknown types so callers can decide the default (Crossref
# defaults to "article"; OpenAlex leaves `kind` unset). Semantic Scholar
# uses a different tag-set derivation — see `semanticscholar_client`.
_CROSSREF_TYPE_TO_KIND = {
    "journal-article":     "article",
    "proceedings-article": "article",
    "article":             "article",
    "book-chapter":        "chapter",
    "book":                "book",
    "monograph":           "book",
    "edited-book":         "book",
    "dissertation":        "thesis",
    "report":              "report",
}


def crossref_type_to_kind(t: str) -> str | None:
    """Map a Crossref-shape `type` string to Corpus's `kind` enum.
    Returns None for unknown types."""
    return _CROSSREF_TYPE_TO_KIND.get((t or "").lower())


# ---------- Text similarity (used by Crossref title-search) ----------

_TITLE_NORM = re.compile(r"[^a-z0-9 ]+")


def norm_title(s: str) -> str:
    """Lower-case, strip non-alphanumerics, collapse whitespace. Used
    to make title strings comparable across the three APIs' different
    quoting/subtitle conventions."""
    return " ".join(_TITLE_NORM.sub(" ", (s or "").lower()).split())


def title_similarity(a: str, b: str) -> float:
    """0.0-1.0 SequenceMatcher ratio between two titles after
    normalization. 0.85 is the accept threshold used by the Crossref
    title-search fallback."""
    import difflib
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


# Floor for accepting an OpenAlex / Semantic Scholar record found BY
# TITLE. Stricter than Crossref's 0.85 because these two searches can
# return a confident-looking near-miss (measured 2026-08-26). One constant so both clients
# agree on what counts as the same paper.
TITLE_MATCH_FLOOR = 0.90

# A title-search seed shorter than this is not a title. On 2026-09-24 a
# first-page fragment reading just "Considerations" matched a chapter
# literally titled "Considerations" at similarity 1.0, and Bjork 1994
# imported as DeLucia-Waack 2006.
MIN_TITLE_WORDS = 3


# A seed made only of section words is a page layout, not a title. On
# 2026-10-29 "ABSTRACT 1 Introduction" (an Annual Review's first page)
# matched a Crossref record titled "Abstract introduction", and
# fleming-2024 imported as stelzner-2006.
SECTION_WORDS = frozenset(
    "abstract introduction keywords key words contents background method methods "
    "results discussion references summary highlights article info information "
    "research original review report paper".split())


def title_worth_searching(title: str) -> bool:
    words = norm_title(title).split()
    if len(words) < MIN_TITLE_WORDS:
        return False
    return not all(w in SECTION_WORDS or w.isdigit() for w in words)
