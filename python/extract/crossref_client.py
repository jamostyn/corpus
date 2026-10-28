"""Crossref client — /works/{doi} lookups + /works?query title search +
mapping from Crossref's `message` shape into Corpus's frontmatter dict.

Split from extract_metadata.py on 2026-08-15.

Called by extract_metadata.extract_metadata() and by _select_best_doi()
for its per-candidate cross-check. `crossref_search_by_title` is also
called by scripts/backfill_dois.py.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from _api_http import (
    CROSSREF_URL,
    CROSSREF_TIMEOUT,
    api_get_json,
    corpus_user_agent,
    crossref_type_to_kind,
    ssl_contexts,
    surname_initial,
    title_similarity,
    title_worth_searching,
)


# ---------- Endpoints -------------------------------------------

def crossref_lookup(doi: str) -> dict | None:
    """Hit api.crossref.org/works/<doi>. Returns the `message` payload
    or None on any failure. Crossref asks for a mailto in User-Agent so
    they can reach out about abuse — using Jack's email per global config.
    """
    url = CROSSREF_URL.format(doi=urllib.parse.quote(doi, safe="/"))
    payload = api_get_json(url, CROSSREF_TIMEOUT)
    return payload.get("message") if payload else None


# ---------- Title-search fallback -------------------------------
# When the DOI regex fails on a PDF's first 3 pages, we fall back
# to a title+author+year search against Crossref. Same thresholds
# as scripts/backfill_dois.py — >=0.85 title similarity AND year
# off by <=1 — so a candidate accepted here matches what the
# backfill script would accept later.

def crossref_search_by_title(title: str, surname: str, year: int | None,
                             threshold: float = 0.85) -> str | None:
    """Query Crossref /works by title+author+year. Return best-match DOI
    (lowercase) if similarity >= threshold AND year-diff <= 1, else None.

    Prefill uses this ONLY when `find_doi` returned nothing — so the cost
    of one extra Crossref roundtrip is bounded to PDFs without a printed
    DOI on their first pages (the exact cases where we were losing DOIs).
    """
    # Word count, not character count: "Considerations" is 14 characters
    # and matched a chapter by that exact name (Bjork 1994 -> DeLucia-Waack
    # 2006, 2026-09-24). The rule lives in _api_http so all three title
    # searches refuse the same seeds.
    if not title_worth_searching(title or ""):
        return None
    params = {"query.title": title, "rows": "5"}
    if surname:
        params["query.author"] = surname
    if year:
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": corpus_user_agent(),
        "Accept":     "application/json",
    })
    for ctx in ssl_contexts():
        try:
            with urllib.request.urlopen(req, timeout=CROSSREF_TIMEOUT, context=ctx) as r:
                payload = json.loads(r.read().decode("utf-8"))
            items = payload.get("message", {}).get("items", []) or []
            best_doi, best_sim, best_ydiff = None, 0.0, None
            for c in items:
                ct = (c.get("title") or [""])[0]
                sim = title_similarity(title, ct)
                cy = None
                for k in ("issued", "published-print", "published-online"):
                    dp = (c.get(k) or {}).get("date-parts") or []
                    if dp and dp[0]:
                        cy = dp[0][0]
                        break
                ydiff = None if (year is None or cy is None) else abs(int(cy) - int(year))
                if sim > best_sim:
                    best_sim, best_doi, best_ydiff = sim, (c.get("DOI") or "").lower() or None, ydiff
            if not best_doi or best_sim < threshold:
                return None
            if best_ydiff is not None and best_ydiff > 1:
                return None
            return best_doi
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                continue
            return None
        except ssl.SSLError:
            continue
        except Exception:
            return None
    return None


# ---------- Mapping: Crossref message -> Corpus frontmatter dict ---

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    """Strip HTML/JATS tags from a text field (Crossref abstracts come
    wrapped in <jats:p>...</jats:p> or plain <p>). Also collapses
    whitespace runs and decodes common HTML entities so callers get
    clean plain text."""
    import html as _html
    s = _HTML_TAG_RE.sub("", s or "")
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _cr_position(sequence: str | None, idx: int, total: int) -> str:
    """Translate Crossref's `sequence` field (first/additional) into
    Corpus's position vocabulary (first / middle / last). Uses the
    index in the author list to distinguish middle from last."""
    if (sequence or "").lower() == "first":
        return "first"
    if idx == total - 1:
        return "last"
    return "middle"


def _from_crossref(msg: dict) -> dict:
    """Map Crossref's `message` shape to our frontmatter dict."""
    out: dict = {"source": "crossref"}
    # Title is an array — take the first non-empty entry.
    titles = msg.get("title") or []
    out["title"] = titles[0].strip() if titles else ""
    # Year — prefer published-print > published-online > issued > created.
    for key in ("published-print", "published-online", "issued", "created"):
        date = (msg.get(key) or {}).get("date-parts") or []
        if date and date[0] and date[0][0]:
            try:
                out["year"] = int(date[0][0])
                break
            except (TypeError, ValueError):
                continue
    # Authors — list of {family, given, affiliation: [{name, ...}]}.
    # Affiliation is Crossref's institutional metadata per author — we pull
    # the FIRST listed institution name when present. Crossref coverage is
    # uneven (some publishers strip it), so missing affiliation is normal;
    # we set it to "" rather than dropping the key, keeping schema shape stable.
    authors = msg.get("author") or []
    if authors:
        def _all_affs(a):
            """Return every affiliation Crossref lists for this author,
            deduplicated preserving order. Papers where the author is
            jointly at 2+ institutions get all of them captured, not
            just the first. Multi-affil authors are the norm for
            senior researchers with adjunct appointments, cross-listed
            centers, etc."""
            out_list: list[str] = []
            for aff in (a.get("affiliation") or []):
                name = (aff.get("name") or "").strip() if isinstance(aff, dict) else ""
                if name and name not in out_list:
                    out_list.append(name)
            return out_list
        out["authors_detailed"] = [
            {"family":       a.get("family", "").strip(),
             "given":        (a.get("given") or "").strip(),
             "institutions": _all_affs(a),
             # NEW: per-author ORCID + author-order position from Crossref
             # (author.sequence is "first" for the first author, "additional"
             # for the rest — we translate to first / middle / last so it
             # matches OA's author_position vocabulary).
             "orcid":        (a.get("ORCID") or a.get("orcid") or "").strip(),
             "position":     _cr_position(a.get("sequence"), i, len(authors))}
            for i, a in enumerate(authors) if a.get("family")
        ]
        out["authors_full"] = [
            surname_initial(a["family"], a["given"])
            for a in out["authors_detailed"]
        ]
        if out["authors_full"]:
            # `author` field in summary is "Surname, X." for the first author.
            first = out["authors_detailed"][0]
            init = ""
            if first["given"]:
                init = (first["given"].strip()[0] + ".") if first["given"] else ""
            out["author"] = f"{first['family']}, {init}".strip(", ").strip()
    # Container / publisher / journal.
    containers = msg.get("container-title") or []
    out["publisher"] = containers[0].strip() if containers else (msg.get("publisher") or "")
    # DOI + URL.
    out["doi"] = (msg.get("DOI") or "").lower()
    out["source_url"] = msg.get("URL") or (f"https://doi.org/{out['doi']}" if out["doi"] else "")
    # Pages.
    if msg.get("page"):
        out["pages"] = msg["page"]
    # Kind hint — Crossref `type` is e.g. journal-article / book-chapter / book.
    crossref_type = (msg.get("type") or "").lower()
    # Stash the raw Crossref type so the extract loop can filter out
    # non-paper resources (component/dataset/grant/...) — the mapped
    # `kind` below folds unknown types to 'article', which would hide
    # them from the type-check that decides whether to try the next
    # candidate DOI.
    out["_crossref_raw_type"] = crossref_type
    # `kind` mapping shared with OpenAlex client via `_api_http`. Default
    # is "article" for Crossref (mostly-articles corpus); OpenAlex leaves
    # unknown types unset instead of defaulting.
    out["kind"] = crossref_type_to_kind(crossref_type) or "article"

    # ---- Extended Crossref fields (added 2026-08-07) --------------------
    # Bibliographic identifiers
    if msg.get("volume"):
        out["volume"] = str(msg["volume"]).strip()
    if msg.get("issue"):
        out["issue"] = str(msg["issue"]).strip()
    if msg.get("article-number"):
        out["article_number"] = str(msg["article-number"]).strip()
    issn_list = [str(s).strip() for s in (msg.get("ISSN") or []) if str(s).strip()]
    if issn_list:
        out["issn"] = issn_list
    isbn_list = [str(s).strip() for s in (msg.get("ISBN") or []) if str(s).strip()]
    if isbn_list:
        out["isbn"] = isbn_list
    if msg.get("language"):
        out["language"] = str(msg["language"]).strip().lower()

    # Counts
    ref_by = msg.get("is-referenced-by-count")
    if isinstance(ref_by, int):
        out["citation_count"] = ref_by
    ref_count = msg.get("references-count")
    if isinstance(ref_count, int):
        out["references_count"] = ref_count

    # Abstract — strip JATS/HTML wrappers, collapse whitespace.
    abstract_raw = (msg.get("abstract") or "").strip()
    if abstract_raw:
        cleaned = _strip_html(abstract_raw)
        if cleaned:
            out["abstract"] = cleaned

    # Subject areas (free-form list)
    subjects = [str(s).strip() for s in (msg.get("subject") or []) if str(s).strip()]
    if subjects:
        out["subjects"] = subjects

    # Funders — each {name, DOI?, award[]}. Awards are grant IDs.
    funders = msg.get("funder") or []
    funder_out = []
    for f in funders:
        name = (f.get("name") or "").strip()
        if not name:
            continue
        funder_out.append({
            "name":   name,
            "doi":    (f.get("DOI") or "").strip().lower() or "unknown",
            "awards": [str(a).strip() for a in (f.get("award") or []) if str(a).strip()],
        })
    if funder_out:
        out["funder"] = funder_out

    # Licenses — each {URL, content-version (vor/am/tdm/unspecified), delay-in-days}
    licenses = msg.get("license") or []
    license_out = []
    for lic in licenses:
        url = (lic.get("URL") or "").strip()
        if not url:
            continue
        license_out.append({
            "url":        url,
            "type":       (lic.get("content-version") or "unspecified").strip(),
            "delay_days": int(lic.get("delay-in-days") or 0),
        })
    if license_out:
        out["license"] = license_out

    # Update-to (retractions / errata / corrections chain).
    updates = msg.get("update-to") or []
    update_out = []
    for u in updates:
        u_doi = (u.get("DOI") or "").strip().lower()
        if not u_doi:
            continue
        update_out.append({
            "doi":   u_doi,
            "type":  (u.get("type") or "").strip(),
            "label": (u.get("label") or "").strip(),
        })
    if update_out:
        out["update_to"] = update_out
        # Derive a simple boolean if any update points at a retraction.
        # This paper being cited as "retraction of" means IT was retracted.
        if any((u["type"] or "").lower() == "retraction" for u in update_out):
            out["retracted"] = True
    if msg.get("update-policy"):
        out["update_policy"] = str(msg["update-policy"]).strip()

    # Alternative IDs (publisher's PII, arXiv, PubMed, etc.)
    alt_ids = [str(a).strip() for a in (msg.get("alternative-id") or []) if str(a).strip()]
    if alt_ids:
        out["alternative_ids"] = alt_ids

    # Event (proceedings only — flatten to scalar fields for _fm.py's sake)
    event = msg.get("event")
    if isinstance(event, dict) and event.get("name"):
        out["event_name"] = (event.get("name") or "").strip()
        if event.get("acronym"):
            out["event_acronym"] = event["acronym"].strip()
        if event.get("location"):
            out["event_location"] = event["location"].strip()

    # ---- Extended Crossref fields (added 2026-08-08 per Jack's audit) ---

    # Edition / chapter / component numbers (for books / book chapters /
    # supplements). Only emit when the publisher actually deposited them.
    for f_src, f_dst in (("edition-number", "edition_number"),
                          ("chapter-number", "chapter_number"),
                          ("component-number", "component_number")):
        v = msg.get(f_src)
        if v:
            out[f_dst] = str(v).strip()

    # Journal issue publication date (different from paper's own date
    # when the issue was published on a schedule).
    ji = msg.get("journal-issue") or {}
    if isinstance(ji, dict):
        for key in ("published-print", "published-online", "published-other"):
            dp = ((ji.get(key) or {}).get("date-parts") or [])
            if dp and dp[0]:
                out["journal_issue_date"] = "-".join(str(x).zfill(2) for x in dp[0] if x)
                break

    # Deposited (when the metadata record was deposited to Crossref) and
    # indexed (when Crossref last re-indexed it). Both are ISO strings
    # that indicate metadata freshness — useful for spotting stale records.
    dep = ((msg.get("deposited") or {}).get("date-time") or "").strip()
    if dep:
        out["deposited_at"] = dep
    idx = ((msg.get("indexed") or {}).get("date-time") or "").strip()
    if idx:
        out["indexed_at"] = idx

    # Content assertions — publisher-declared statements about the
    # article (peer-review status, open-access declarations, funding
    # attestations, etc.). Each is {name, value, url?, group?}.
    assertions_raw = msg.get("assertion") or []
    assertions_out = []
    for a in assertions_raw:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or a.get("label") or "").strip()
        val  = (a.get("value") or "").strip()
        if not (name or val):
            continue
        entry: dict = {"name": name, "value": val}
        if a.get("url"):
            entry["url"] = str(a["url"]).strip()
        if a.get("group") and isinstance(a["group"], dict) and a["group"].get("label"):
            entry["group"] = str(a["group"]["label"]).strip()
        assertions_out.append(entry)
    if assertions_out:
        out["content_assertions"] = assertions_out

    return out

