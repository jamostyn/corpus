"""OpenAlex client — /works/https://doi.org/{doi} lookups + mapping
from the OA work payload into Corpus's frontmatter dict.

Split from extract_metadata.py on 2026-08-15.

OpenAlex's value-adds over Crossref: per-author institutional
affiliations (much better coverage than Crossref's), open-access URL
when available, structured topic/keyword hierarchy, per-year citation
counts, versions across sources, and OA-only fields (fwci, is_paratext,
retraction_notice text, etc.).
"""
from __future__ import annotations

import logging
import re
import urllib.parse

logger = logging.getLogger("corpus.openalex")

from _api_http import (
    OPENALEX_URL,
    OPENALEX_TIMEOUT,
    TITLE_MATCH_FLOOR,
    api_get_json,
    crossref_type_to_kind,
    split_display_name,
    surname_initial,
    title_similarity,
    title_worth_searching,
)


# ---------- Endpoint --------------------------------------------

def openalex_lookup(doi: str) -> dict | None:
    """Hit api.openalex.org/works/https://doi.org/<doi>. Returns the
    work payload or None. Key value-adds over Crossref: per-author
    institutional affiliations (much better coverage than Crossref's
    Crossref-metadata-uploaded affiliations) + open-access URL when
    the paper has one."""
    url = OPENALEX_URL.format(doi=urllib.parse.quote(doi, safe="/"))
    # OpenAlex encodes the leading https:// as %3A%2F%2F for the DOI —
    # quote(safe="/") preserves the / but drops : safely.
    return api_get_json(url, OPENALEX_TIMEOUT)


def openalex_search_by_title(title: str, year: int | None = None) -> dict | None:
    """Best OpenAlex work whose title matches `title`, or None.

    Uses `filter=title.search:`, never `search=`: free-text search ranks
    over the whole record and returns a confident hit even for a title
    OpenAlex does not have (measured 2026-08-26). The hit must
    still clear TITLE_MATCH_FLOOR against the query.

    Returns the FULL work payload, so `_from_openalex` can use it
    directly — which is what makes a DOI-less work (OpenAlex holds ~100M)
    recoverable at all: its own `W…` id is the only handle.
    """
    if not title_worth_searching(title):
        return None
    # In an OpenAlex filter "," separates filters and ":" splits key from
    # value, so either inside a title truncates the query silently.
    q = urllib.parse.quote(re.sub(r"[,:|]", " ", title).strip())
    for year_filter in ([f",publication_year:{year}"] if year else []) + [""]:
        data = api_get_json(
            f"https://api.openalex.org/works?filter=title.search:{q}{year_filter}&per-page=5",
            OPENALEX_TIMEOUT)
        best = max((data or {}).get("results") or [], default=None,
                   key=lambda w: title_similarity(title, w.get("title") or ""))
        if best and title_similarity(title, best.get("title") or "") >= TITLE_MATCH_FLOOR:
            return best
    return None


# ---------- Bulk / graph endpoints -------------------------------
#
# Added 2026-09-17 for citation bridges. Both are general OpenAlex
# helpers, kept here with the rest of the OpenAlex code rather than
# beside their first caller.
#
# Measured against the real corpus: 50 DOIs resolve in one ~500ms
# request with COMPLETE `referenced_works` inline (counts matched the
# reported totals exactly, no truncation). Semantic Scholar's
# /paper/batch was tried first and cannot serve this — it returned
# `referenceCount: 67` alongside an EMPTY references array, and 429'd
# even with a key set.

# OpenAlex caps an OR-joined filter list at 50 values.
OA_FILTER_MAX = 50
# `per-page` maximum for the works endpoint.
OA_PAGE_MAX = 200
# Stop paginating a single citer list here. A famous paper can have
# tens of thousands of citers; past a few thousand it is not a useful
# "bridge" signal anyway, and it would dominate the request budget.
OA_MAX_CITER_PAGES = 10


def _oa_filter_url(field: str, values: list[str], select: str,
                   page: int = 1) -> str:
    joined = "|".join(values)
    flt = urllib.parse.quote(f"{field}:{joined}", safe=":|/.")
    return (f"https://api.openalex.org/works?filter={flt}"
            f"&per-page={OA_PAGE_MAX}&page={page}&select={select}")


def oa_short_id(work_id: str) -> str:
    """'https://openalex.org/W123' -> 'W123'.

    Every id crossing a module boundary is SHORT. The API returns full
    URLs in `referenced_works` but expects bare ids in a filter, and
    mixing the two forms silently produces a malformed filter that
    matches nothing rather than erroring — which is exactly how the
    first prototype of this feature reported "no bridges found".
    """
    return str(work_id or "").rsplit("/", 1)[-1]


def openalex_works_by(field: str, values: list[str],
                      select: str) -> tuple[list[dict], int]:
    """Bulk-fetch works by `doi:` or `openalex:`, chunked to the filter cap.

    Returns `(results, failed_values)` — the second is how many INPUT
    values were lost to a chunk that did not come back, not how many
    chunks failed, because the caller cares about papers.

    Why a tuple instead of just the list: this used to swallow a failed
    chunk and return whatever else arrived. One dropped chunk is up to
    50 papers, and on 2026-09-21 exactly that happened — a bridge run
    over a 257-paper corpus resolved 206 and reported the other 51 as
    "unresolved", which reads as "OpenAlex doesn't have them". Re-running
    the identical lookup resolved all 256. The bridge graph was built on
    80% of the corpus and nothing said so.

    A silent partial result is worse than an error: the output looks
    plausible. So failures are counted and handed back, and callers must
    take the second element to get the first.

    Each chunk gets ONE retry before being counted as lost — the failure
    was transient, and a single retry costs one request against losing
    fifty papers.
    """
    vals = [str(v).strip() for v in values if str(v).strip()]
    out: list[dict] = []
    failed = 0
    for i in range(0, len(vals), OA_FILTER_MAX):
        chunk = vals[i:i + OA_FILTER_MAX]
        url = _oa_filter_url(field, chunk, select)
        data = api_get_json(url, OPENALEX_TIMEOUT)
        if data is None:
            data = api_get_json(url, OPENALEX_TIMEOUT)   # one retry
        if data is None:
            failed += len(chunk)
            logger.warning("openalex_chunk_failed field=%s n=%d", field, len(chunk))
            continue
        out.extend(data.get("results") or [])
    return out, failed


def openalex_citers_of(work_id: str) -> list[str] | None:
    """Short ids of every work citing `work_id`.

    This is the BACKWARD direction of the citation graph, and it is the
    cheaper one: median 24 citers per paper in the real corpus against
    58 references. Returns None on a network failure so callers can
    tell "nothing cites it" from "we could not find out" — the two mean
    very different things in a connections panel.
    """
    wid = oa_short_id(work_id)
    if not wid:
        return []
    found: list[str] = []
    seen: set[str] = set()
    any_ok = False
    for page in range(1, OA_MAX_CITER_PAGES + 1):
        data = api_get_json(_oa_filter_url("cites", [wid], "id", page=page),
                            OPENALEX_TIMEOUT)
        if data is None:
            return None if not any_ok else found
        any_ok = True
        results = data.get("results") or []
        for w in results:
            sid = oa_short_id(w.get("id"))
            if sid and sid not in seen:
                seen.add(sid)
                found.append(sid)
        if len(results) < OA_PAGE_MAX:
            break
    return found


def openalex_citer_pages(work_id: str, select: str = "id,doi,publication_year,display_name"):
    """Yield `(results, meta)` for EVERY page of works citing `work_id`.

    Cursor paging, not `page=`: OpenAlex refuses page-number paging past
    10,000 results, and the most-cited paper in the corpus has ~105,000
    citers. Unlike `openalex_citers_of` (which the bridge search uses and
    caps at 2,000), this has no cap — it exists to store the whole list.

    Each page gets one retry. A page that still fails raises
    `CiterFetchError`, carrying how many were fetched, so the caller can
    store a partial list marked incomplete rather than a short list that
    looks whole.
    """
    wid = oa_short_id(work_id)
    if not wid:
        return
    cursor = "*"
    while cursor:
        url = (f"https://api.openalex.org/works?filter=cites:{wid}"
               f"&per-page={OA_PAGE_MAX}&select={select}&cursor={urllib.parse.quote(cursor)}")
        data = api_get_json(url, OPENALEX_TIMEOUT)
        if data is None:
            data = api_get_json(url, OPENALEX_TIMEOUT)      # one retry
        if data is None:
            raise CiterFetchError(f"page failed for {wid}")
        results = data.get("results") or []
        meta = data.get("meta") or {}
        yield results, meta
        cursor = meta.get("next_cursor") if results else None


class CiterFetchError(RuntimeError):
    """A citer page did not come back after a retry."""


# ---------- Mapping: OpenAlex work -> Corpus frontmatter dict ----

def _from_openalex(work: dict) -> dict:
    """Map an OpenAlex work payload to Corpus fields.

    OA's role in the pipeline:
      - VERIFIER for scalars Crossref/SS already cover: title, year,
        doi, publisher, kind, volume, issue, pages, language, issn,
        references_count, retracted, alternative_ids
      - AUTHORITATIVE for the structured hierarchy fields OA uniquely
        provides:
          * per-author institutions with ROR + country + type + lineage
          * corresponding-author flag + author position
          * OA status classification (gold/green/hybrid/bronze/closed)
          * all-locations list (every free copy across sources)
          * topics (domain → field → subfield → topic hierarchy)
          * keywords with relevance scores
          * FWCI (Field-Weighted Citation Impact)
          * cited_by_count (OA's third-source count)
          * counts_by_year (citation trajectory)
          * retraction_notice text (beyond just the flag)
          * versions (preprint/accepted/published chain across sources)

    Complex nested fields (oa_authors, oa_topics, etc.) are stashed as
    dicts/lists on the returned dict; prefill_summary emits them as
    JSON literal block scalars because _fm.py can't parse nested dicts
    inside flow mappings.
    """
    out: dict = {"source": "openalex"}

    # ---- Simple scalar verifiers ------------------------------------
    title = (work.get("title") or work.get("display_name") or "").strip()
    if title:
        out["title"] = title
    year = work.get("publication_year")
    if isinstance(year, int):
        out["year"] = year
    if work.get("language"):
        out["language"] = str(work["language"]).strip().lower()

    # DOI (redundant with URL) — normalize away https://doi.org/ prefix.
    doi = (work.get("doi") or "").lower()
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    if doi:
        out["doi"] = doi

    # kind — prefer Crossref's original type mapping, then OA's own.
    # Mapping lives in `_api_http.crossref_type_to_kind` so all clients
    # that consume Crossref-shape type strings agree.
    kind = crossref_type_to_kind(work.get("type_crossref") or work.get("type") or "")
    if kind:
        out["kind"] = kind

    # Venue / publisher
    prim_loc = work.get("primary_location") or {}
    src = prim_loc.get("source") or {}
    venue = (src.get("display_name") or "").strip()
    if not venue:
        venue = ((work.get("host_venue") or {}).get("display_name") or "").strip()
    if venue:
        out["publisher"] = venue
    # Venue type (journal / conference / repository / ebook platform / …)
    vt = (src.get("type") or "").strip()
    if vt:
        out["venue_type"] = vt
    # Publisher hierarchy: the immediate host_organization + its full
    # lineage chain (e.g. "Wiley → John Wiley & Sons → RELX Group").
    ho = (src.get("host_organization_name") or "").strip()
    if ho:
        out["host_organization"] = ho
    lineage = [str(x).strip() for x in (src.get("host_organization_lineage_names") or []) if x]
    if lineage:
        out["host_organization_lineage"] = lineage
    # ISSN — OA gives issn_l (canonical) + issn[] (all variants)
    issn_list: list[str] = []
    if src.get("issn_l"):
        issn_list.append(str(src["issn_l"]).strip())
    for i in (src.get("issn") or []):
        s = str(i).strip()
        if s and s not in issn_list:
            issn_list.append(s)
    if issn_list:
        out["issn"] = issn_list

    # Bibliographic (volume/issue/pages)
    bib = work.get("biblio") or {}
    if bib.get("volume"):
        out["volume"] = str(bib["volume"]).strip()
    if bib.get("issue"):
        out["issue"] = str(bib["issue"]).strip()
    fp = str(bib.get("first_page") or "").strip()
    lp = str(bib.get("last_page") or "").strip()
    if fp and lp and fp != lp:
        out["pages"] = f"{fp}-{lp}"
    elif fp:
        out["pages"] = fp

    # Source URL — prefer canonical DOI URL (matches Crossref format for
    # verifier merge). OA locations get their own dedicated field below.
    if doi:
        out["source_url"] = f"https://doi.org/{doi}"

    # Abstract — reconstruct from OA's inverted-index format.
    inv = work.get("abstract_inverted_index")
    if isinstance(inv, dict) and inv:
        max_pos = max((max(v) for v in inv.values() if v), default=-1)
        if max_pos >= 0:
            words = [""] * (max_pos + 1)
            for word, positions in inv.items():
                for p in positions:
                    if 0 <= p <= max_pos:
                        words[p] = word
            abstract = " ".join(w for w in words if w).strip()
            if abstract:
                out["abstract"] = abstract

    # Counts / metrics -------------------------------------------------
    cbc = work.get("cited_by_count")
    if isinstance(cbc, int):
        out["citation_count_oa"] = cbc
    rwc = work.get("referenced_works_count")
    if isinstance(rwc, int):
        out["references_count"] = rwc
    fwci = work.get("fwci")
    if isinstance(fwci, (int, float)):
        out["fwci"] = float(fwci)

    # counts_by_year: list of {year: N, cited_by_count: M}
    cby = work.get("counts_by_year") or []
    cby_list = []
    for entry in cby:
        if isinstance(entry, dict) and isinstance(entry.get("year"), int):
            cby_list.append({
                "year":  int(entry["year"]),
                "count": int(entry.get("cited_by_count") or 0),
            })
    if cby_list:
        # sort ascending by year for consistent display
        cby_list.sort(key=lambda x: x["year"])
        out["counts_by_year"] = cby_list

    # Full-text availability + paratext flag ---------------------------
    if work.get("has_fulltext") is not None:
        out["has_fulltext"] = bool(work.get("has_fulltext"))
    if work.get("fulltext_origin"):
        out["fulltext_origin"] = str(work["fulltext_origin"]).strip()
    if work.get("is_paratext") is not None:
        out["is_paratext"] = bool(work.get("is_paratext"))

    # OA record freshness (when OA first indexed this + last touched it)
    if work.get("created_date"):
        out["oa_created_date"] = str(work["created_date"]).strip()
    if work.get("updated_date"):
        out["oa_updated_date"] = str(work["updated_date"]).strip()

    # Retraction ------------------------------------------------------
    if work.get("is_retracted"):
        out["retracted"] = True
        # Retraction notice — OA sometimes gives a text field or points
        # at the retracting work. Capture whatever text is available.
        notice = (work.get("retraction_notice") or "").strip()
        if notice:
            out["retraction_notice"] = notice

    # Alternative IDs from OA's `ids` dict (MAG, PMID, PMCID). Skip DOI
    # (already in main field) and openalex (their own ID; captured
    # separately below).
    alt_ids: list[str] = []
    ids = work.get("ids") or {}
    for k, v in ids.items():
        if not v: continue
        kk = str(k).lower()
        if kk in ("doi", "openalex"): continue
        alt_ids.append(str(v).strip())
    if alt_ids:
        out["alternative_ids"] = alt_ids
    if ids.get("openalex"):
        out["oa_paper_id"] = str(ids["openalex"]).strip()

    # OA status + all locations (list of every free copy) ----------------
    oa_block = work.get("open_access") or {}
    if oa_block.get("oa_status"):
        out["oa_status"] = str(oa_block["oa_status"]).strip()
    if oa_block.get("is_oa") is not None:
        out["is_oa"] = bool(oa_block["is_oa"])

    all_locs = []
    for loc in (work.get("locations") or []):
        if not isinstance(loc, dict): continue
        loc_src = loc.get("source") or {}
        url = (loc.get("pdf_url") or loc.get("landing_page_url") or "").strip()
        if not url: continue
        all_locs.append({
            "url":          url,
            "is_oa":        bool(loc.get("is_oa")),
            "version":      (loc.get("version") or "").strip(),   # submittedVersion/acceptedVersion/publishedVersion
            "license":      (loc.get("license") or "").strip(),
            "source_name":  (loc_src.get("display_name") or "").strip(),
            "source_type":  (loc_src.get("type") or "").strip(),  # journal/repository/etc.
            "host_org":     (loc_src.get("host_organization_name") or "").strip(),
            "pdf":          bool(loc.get("pdf_url")),
        })
    if all_locs:
        out["oa_locations"] = all_locs

    # Grants — funders + award IDs (verifier for Crossref's funder list).
    grants = work.get("grants") or []
    funder_out = []
    for g in grants:
        if not isinstance(g, dict): continue
        name = (g.get("funder_display_name") or "").strip()
        if not name: continue
        funder_out.append({
            "name":   name,
            "doi":    (g.get("funder") or "").strip().lower() or "unknown",  # OA gives the OA funder-URI; keep as-is
            "awards": [str(g.get("award_id")).strip()] if g.get("award_id") else [],
        })
    if funder_out:
        out["funder"] = funder_out

    # Topics / keywords -----------------------------------------------
    # topics: [{id, display_name, subfield: {display_name}, field: {display_name}, domain: {display_name}, score}]
    topics = []
    for t in (work.get("topics") or []):
        if not isinstance(t, dict): continue
        topics.append({
            "topic":    (t.get("display_name") or "").strip(),
            "subfield": ((t.get("subfield") or {}).get("display_name") or "").strip(),
            "field":    ((t.get("field")    or {}).get("display_name") or "").strip(),
            "domain":   ((t.get("domain")   or {}).get("display_name") or "").strip(),
            "score":    float(t.get("score") or 0.0),
        })
    if topics:
        out["topics"] = topics

    keywords = []
    for k in (work.get("keywords") or []):
        if not isinstance(k, dict): continue
        name = (k.get("display_name") or k.get("keyword") or "").strip()
        if name:
            keywords.append({"name": name, "score": float(k.get("score") or 0.0)})
    if keywords:
        out["keywords"] = keywords

    # Per-author OA structure (institutions with ROR + country + type +
    # lineage, corresponding flag, position). Emitted as JSON block
    # scalar downstream since _fm.py doesn't parse nested flow mappings.
    oa_authors = []
    detailed_flat = []      # for the shared authors_detailed merge (Crossref remains authoritative)
    authors_full_flat = []
    for a in (work.get("authorships") or []):
        author = (a.get("author") or {}) or {}
        display = (author.get("display_name") or "").strip()
        if not display: continue
        # Split shared with `_from_pdf_metadata`; handles both
        # "Endel Tulving" and "Smith J." shapes.
        family, given = split_display_name(display)
        if not family:
            continue
        # Structured institutions
        insts_struct = []
        insts_flat: list[str] = []
        for inst in (a.get("institutions") or []):
            if not isinstance(inst, dict): continue
            name = (inst.get("display_name") or "").strip()
            if not name: continue
            insts_struct.append({
                "name":         name,
                "ror":          (inst.get("ror") or "").strip(),
                "country_code": (inst.get("country_code") or "").strip().upper(),
                "type":         (inst.get("type") or "").strip(),
                "lineage":      [str(x).strip() for x in (inst.get("lineage") or []) if x],
            })
            if name not in insts_flat:
                insts_flat.append(name)
        # Raw affiliation strings publishers originally submitted (before
        # OA normalized them to institution objects). Useful for
        # verification when OA's normalization looks wrong.
        raw_affils = [str(x).strip() for x in (a.get("raw_affiliation_strings") or []) if x]
        oa_authors.append({
            "family":         family,
            "given":          given,
            "orcid":          (author.get("orcid") or "").strip(),
            "position":       (a.get("author_position") or "").strip(),
            "is_corresponding": bool(a.get("is_corresponding")),
            "institutions":   insts_struct,
            "raw_affiliations": raw_affils,
            "raw_author_name": (a.get("raw_author_name") or "").strip(),
        })
        detailed_flat.append({"family": family, "given": given, "institutions": insts_flat})
        authors_full_flat.append(surname_initial(family, given))

    if detailed_flat:
        out["authors_detailed"] = detailed_flat
        out["authors_full"] = authors_full_flat
        first = detailed_flat[0]
        init = (first["given"].strip()[0] + ".") if first["given"] else ""
        out["author"] = f"{first['family']}, {init}".strip(", ").strip()
    if oa_authors:
        out["oa_authors"] = oa_authors

    # Versions — OA doesn't have a first-class "versions" field, but we
    # derive it from locations by grouping non-empty `version` tags
    # (submittedVersion = preprint, acceptedVersion = author-accepted,
    # publishedVersion = version of record). Same paper across sources.
    versions = []
    seen_v_urls = set()
    for loc in (work.get("locations") or []):
        if not isinstance(loc, dict): continue
        v = (loc.get("version") or "").strip()
        if not v: continue
        url = (loc.get("landing_page_url") or loc.get("pdf_url") or "").strip()
        if not url or url in seen_v_urls: continue
        seen_v_urls.add(url)
        src2 = loc.get("source") or {}
        versions.append({
            "version":     v,   # submittedVersion / acceptedVersion / publishedVersion
            "url":         url,
            "source_name": (src2.get("display_name") or "").strip(),
        })
    if versions:
        out["versions"] = versions

    return out


# SS publication type → paper_type enum mapping. SS returns a LIST per
# paper (e.g. ["JournalArticle", "Review"]); we pick the most specific

