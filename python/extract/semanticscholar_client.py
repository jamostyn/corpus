"""Semantic Scholar client — /paper/DOI:{doi} lookups,
/author/batch bulk fetches, and mapping from the SS payload into
Corpus's frontmatter dict.

Split from extract_metadata.py on 2026-08-15.

SS is the SOLE source for tldr / SPECTER2 embedding / bibtex /
publication types / paper_type / ss_paper_id + external IDs
(arXiv/PubMed/…). Also contributes overlapping fields (title, year,
publisher, volume, pages, abstract) so those earn a
semanticscholar-verifier badge in the provenance chain when their
values match Crossref's.

The /author/batch endpoint is separate — used by the OA-enrichment
worker to fill h-index / paper count / citation count on authors that
have an SS author ID.
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from _api_http import (
    SS_URL,
    SS_TIMEOUT,
    TITLE_MATCH_FLOOR,
    api_get_json,
    api_headers,
    ssl_contexts,
    title_similarity,
    title_worth_searching,
)


# ---------- Rate limit ------------------------------------------
# Semantic Scholar's public unauthenticated tier caps callers at
# ~1 request/second across the API. With an API key that jumps to
# ~100 req/s. Hitting the public tier faster returns HTTP 429 and
# the response body is discarded — silently, from the caller's
# perspective — so users end up with sporadic missing tldr /
# embedding / bibtex fields on batch operations.
#
# Simple gate: track the last SS call timestamp per process and
# sleep to enforce the minimum interval when no key is set. Thread-
# safe because enrichment workers can run concurrently.
_SS_MIN_INTERVAL_NO_KEY = 1.1   # seconds (small margin over SS's 1 req/s)
_ss_gate_lock = threading.Lock()
_ss_last_call = 0.0


def _ss_rate_limit() -> None:
    """Block until it's safe to make the next SS call given the current
    tier. No-op when a key is present."""
    if os.environ.get("CORPUS_SEMANTIC_SCHOLAR_KEY", "").strip():
        return
    global _ss_last_call
    with _ss_gate_lock:
        now = time.monotonic()
        gap = now - _ss_last_call
        if gap < _SS_MIN_INTERVAL_NO_KEY:
            time.sleep(_SS_MIN_INTERVAL_NO_KEY - gap)
        _ss_last_call = time.monotonic()


# ---------- Endpoints -------------------------------------------

def semanticscholar_lookup(doi: str) -> dict | None:
    """Hit SS graph API by DOI. Returns the paper JSON or None.

    Sends `x-api-key` when CORPUS_SEMANTIC_SCHOLAR_KEY is in the env
    (set by the server from the user's Keychain). Without a key, SS
    caps callers at ~1 req/s; with a key ~100 req/s. See _ss_rate_limit."""
    return _ss_get(SS_URL.format(doi=urllib.parse.quote(doi, safe="/")))


def _ss_get(url: str, retries: int = 0) -> dict | None:
    """Rate-limited, keyed GET. `retries` re-asks after a pause: keyless
    S2 answers a burst with 429s that api_get_json reports as None, and a
    title lookup that gives up on the first 429 reads as "not found"
    (seen 2026-09-24: 1 of 11 probe lookups)."""
    extra: dict = {}
    ss_key = os.environ.get("CORPUS_SEMANTIC_SCHOLAR_KEY", "").strip()
    if ss_key:
        extra["x-api-key"] = ss_key
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(3 * attempt)
        _ss_rate_limit()
        data = api_get_json(url, SS_TIMEOUT, extra_headers=extra)
        if data is not None:
            return data
    return None


def semanticscholar_lookup_id(paper_id: str) -> dict | None:
    """Same payload as `semanticscholar_lookup`, addressed by S2's own
    paperId — the only handle on a work that has no DOI."""
    return _ss_get(SS_URL.replace("DOI:{doi}", "{doi}").format(
        doi=urllib.parse.quote(paper_id, safe="")))


def semanticscholar_match_title(title: str) -> dict | None:
    """S2's best match for `title` as `{"paper_id", "doi"}`, or None.

    `/paper/search/match` is purpose-built for title -> one paper and
    answers a clean 404 when nothing matches; `/paper/search` 429s
    keyless (ROADMAP, verified 2026-08-26). The hit must still clear
    TITLE_MATCH_FLOOR — the endpoint can return a near-miss.
    """
    if not title_worth_searching(title):
        return None
    data = _ss_get("https://api.semanticscholar.org/graph/v1/paper/search/match?query="
                   + urllib.parse.quote(title) + "&fields=title,externalIds", retries=2)
    rows = (data or {}).get("data") or []
    if not rows or title_similarity(title, rows[0].get("title") or "") < TITLE_MATCH_FLOOR:
        return None
    doi = ((rows[0].get("externalIds") or {}).get("DOI") or "").strip().lower()
    return {"paper_id": rows[0].get("paperId"), "doi": doi or None}


def semanticscholar_author_batch(author_ids: list[str]) -> list[dict] | None:
    """POST /graph/v1/author/batch with author IDs; get back h-index,
    paper count, citation count per author.

    Returns list of author dicts (one per requested ID, None entries for
    IDs SS didn't recognize). Returns None on network error."""
    ids = [str(x).strip() for x in author_ids if str(x).strip()]
    if not ids:
        return []
    _ss_rate_limit()
    url = ("https://api.semanticscholar.org/graph/v1/author/batch"
           "?fields=name,hIndex,paperCount,citationCount")
    body = json.dumps({"ids": ids}).encode("utf-8")
    hdrs = dict(api_headers())
    hdrs["Content-Type"] = "application/json"
    ss_key = os.environ.get("CORPUS_SEMANTIC_SCHOLAR_KEY", "").strip()
    if ss_key:
        hdrs["x-api-key"] = ss_key
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    for ctx in ssl_contexts():
        try:
            with urllib.request.urlopen(req, timeout=SS_TIMEOUT, context=ctx) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                continue
            return None
        except ssl.SSLError:
            continue
        except Exception:
            return None
    return None


# ---------- Mapping: SS payload -> Corpus frontmatter dict -------

def _derive_paper_type(pubtypes: list[str]) -> str:
    tags = {str(p).lower().replace("-", "").replace("_", "") for p in (pubtypes or [])}
    if "metaanalysis" in tags:
        return "meta-analysis"
    if "review" in tags:
        return "review"
    if "casereport" in tags or "clinicaltrial" in tags or "study" in tags:
        return "empirical"
    if "editorial" in tags or "lettersandcomments" in tags or "news" in tags:
        return "commentary"
    return ""  # can't confidently classify from what SS returned



def _from_semanticscholar(work: dict) -> dict:
    """Map SS's graph API payload to Corpus fields.

    SS is the SOLE source for:
      - tldr (auto-summary, ~2 sentences)
      - embedding (SPECTER2 768-d vector)
      - citation_count_ss + influential_citation_count_ss
      - s2_fields_of_study (structured topic classification)
      - publication_types
      - paper_type (derived from publication_types)
      - open_access_pdf link
      - bibtex
      - ss_paper_id + arXiv/PubMed/etc. external IDs

    SS ALSO contributes to overlapping fields (title, year, publisher,
    volume, pages, abstract) — these get merged with Crossref and, when
    values match, SS earns a verifier badge in the provenance chain.

    Deliberately does NOT provide authors_full / authors_detailed —
    SS gives single-string author names ('Alexandra O. Cohen'); Crossref
    splits them properly into given + family. We store SS's raw author
    list under `_ss_authors_raw` in case a future verification tool
    wants to cross-check the two sources, but nothing surfaces this in
    the UI.
    """
    out: dict = {"source": "semanticscholar"}

    # --- Overlapping fields (contribute as verifiers via merge) --------
    # Anything that SS *could* independently confirm — even if less
    # reliable than Crossref — goes here so it earns a semanticscholar
    # verifier badge in the UI. The merge only accepts SS's value as a
    # verifier if it matches the Crossref value (after normalization);
    # mismatches are silently ignored (Crossref wins as authoritative).
    title = (work.get("title") or "").strip()
    if title:
        out["title"] = title
    year = work.get("year")
    if isinstance(year, int):
        out["year"] = year
    venue = (work.get("venue") or "").strip()
    if not venue:
        j0 = work.get("journal") or {}
        venue = (j0.get("name") or "").strip()
    if venue:
        out["publisher"] = venue
    j = work.get("journal") or {}
    if j.get("volume"):
        out["volume"] = str(j["volume"]).strip()
    if j.get("pages"):
        out["pages"] = str(j["pages"]).strip()
    abstract = (work.get("abstract") or "").strip()
    if abstract:
        out["abstract"] = abstract

    # DOI + source_url from SS's externalIds — canonical formatting so
    # they match Crossref's (verifier lands).
    ext_ids = work.get("externalIds") or {}
    if isinstance(ext_ids, dict) and ext_ids.get("DOI"):
        ss_doi = str(ext_ids["DOI"]).strip().lower()
        out["doi"] = ss_doi
        out["source_url"] = f"https://doi.org/{ss_doi}"

    # References count (SS returns `referenceCount` — verifies Crossref's
    # `references-count` field).
    rc = work.get("referenceCount")
    if isinstance(rc, int):
        out["references_count"] = rc

    # ISSN from SS's publicationVenue (verifies Crossref's ISSN list).
    pv = work.get("publicationVenue") or {}
    if isinstance(pv, dict):
        issn_raw = pv.get("issn")
        issn_out: list[str] = []
        if isinstance(issn_raw, str) and issn_raw.strip():
            issn_out = [issn_raw.strip()]
        elif isinstance(issn_raw, list):
            issn_out = [str(s).strip() for s in issn_raw if str(s).strip()]
        if issn_out:
            out["issn"] = issn_out

    # Kind — derive article/book/chapter from publicationTypes so SS can
    # verify Crossref's `kind` field. Uses the same tag priority as
    # paper_type derivation below.
    pubtypes_early = work.get("publicationTypes") or []
    if pubtypes_early:
        tags_early = {str(p).lower().replace("-", "").replace("_", "")
                       for p in pubtypes_early}
        if "book" in tags_early and not ("booksection" in tags_early
                                          or "bookchapter" in tags_early):
            out["kind"] = "book"
        elif "booksection" in tags_early or "bookchapter" in tags_early:
            out["kind"] = "chapter"
        elif ("journalarticle" in tags_early or "conferencepaper" in tags_early
              or "review" in tags_early or "metaanalysis" in tags_early
              or "casereport" in tags_early or "clinicaltrial" in tags_early
              or "study" in tags_early or "editorial" in tags_early
              or "lettersandcomments" in tags_early):
            out["kind"] = "article"

    # Alternative IDs — SS's externalIds includes arXiv, PubMed, PII (MAG),
    # DBLP, etc. Merge into the shared `alternative_ids` field so any that
    # Crossref also happened to deposit as alt-ids earn a verifier badge.
    # (SS-only IDs still end up in the flattened ss_<type>_id fields
    # emitted below, for interop even without verification.)
    if isinstance(ext_ids, dict):
        alt_out: list[str] = []
        for k, v in ext_ids.items():
            if not v or str(k).upper() == "DOI":
                continue
            alt_out.append(str(v).strip())
        if alt_out:
            out["alternative_ids"] = alt_out

    # --- SS-unique scalar fields --------------------------------------
    cc = work.get("citationCount")
    if isinstance(cc, int):
        out["citation_count_ss"] = cc
    icc = work.get("influentialCitationCount")
    if isinstance(icc, int):
        out["influential_citation_count_ss"] = icc

    tldr = work.get("tldr") or {}
    if isinstance(tldr, dict):
        t_txt = (tldr.get("text") or "").strip()
        if t_txt:
            out["tldr"] = t_txt
            if tldr.get("model"):
                out["tldr_model"] = str(tldr["model"]).strip()

    emb = work.get("embedding") or {}
    if isinstance(emb, dict) and isinstance(emb.get("vector"), list):
        out["embedding"] = emb["vector"]
        if emb.get("model"):
            out["embedding_model"] = str(emb["model"]).strip()

    fos = work.get("s2FieldsOfStudy") or []
    if fos:
        cleaned = []
        for f in fos:
            if not isinstance(f, dict):
                continue
            cat = (f.get("category") or "").strip()
            if not cat:
                continue
            cleaned.append({
                "category": cat,
                "source":   (f.get("source") or "").strip() or "unknown",
            })
        if cleaned:
            out["s2_fields_of_study"] = cleaned

    pubtypes = work.get("publicationTypes") or []
    if pubtypes:
        pt_list = [str(p).strip() for p in pubtypes if str(p).strip()]
        if pt_list:
            out["publication_types"] = pt_list
            derived = _derive_paper_type(pt_list)
            if derived:
                out["paper_type"] = derived

    oa = work.get("openAccessPdf") or {}
    if isinstance(oa, dict) and oa.get("url"):
        out["open_access_pdf_url"]     = str(oa.get("url")).strip()
        st = (oa.get("status") or "").strip()
        if st:
            out["open_access_pdf_status"] = st
        lic = (oa.get("license") or "").strip()
        if lic:
            out["open_access_pdf_license"] = lic

    cs = work.get("citationStyles") or {}
    if isinstance(cs, dict) and cs.get("bibtex"):
        out["bibtex"] = str(cs["bibtex"]).strip()

    if work.get("paperId"):
        out["ss_paper_id"] = str(work["paperId"]).strip()

    # Flatten SS's externalIds so each becomes its own top-level scalar
    # (_fm.py doesn't parse nested dicts at scalar level). Skip DOI —
    # that's already in the main doi field.
    ext_ids = work.get("externalIds") or {}
    if isinstance(ext_ids, dict):
        for k, v in ext_ids.items():
            if not v or str(k).upper() == "DOI":
                continue
            out[f"ss_{str(k).lower()}_id"] = str(v).strip()

    # SS's reference list — used to cross-verify against Crossref's ref
    # list AND to display SS-only refs (papers SS found that Crossref
    # didn't).
    #   `_ss_reference_dois` = flat DOI list (for the fast Crossref∩SS
    #                          overlap check)
    #   `_ss_references_raw` = per-ref {doi, title, year} dicts (used to
    #                          render SS-only refs with real titles when
    #                          Crossref didn't list them at all)
    ss_refs = work.get("references") or []
    ref_dois: list[str] = []
    raw_refs: list[dict] = []
    for r in ss_refs:
        if not isinstance(r, dict):
            continue
        ext = r.get("externalIds") or {}
        d = ""
        if isinstance(ext, dict):
            d = (ext.get("DOI") or "").strip().lower()
        if d:
            ref_dois.append(d)
        title = (r.get("title") or "").strip()
        year  = r.get("year")
        year  = int(year) if isinstance(year, int) else None
        # Store any ref with either a DOI or a title — skip completely
        # empty entries. Title alone is uncommon but not useless.
        if d or title:
            entry: dict = {}
            if d:     entry["doi"]   = d
            if title: entry["title"] = title
            if year:  entry["year"]  = year
            raw_refs.append(entry)
    if ref_dois:
        out["_ss_reference_dois"] = ref_dois
    if raw_refs:
        out["_ss_references_raw"] = raw_refs

    # SS's raw authors — enriched with per-author profile stats
    # (h-index, papers count, total citations) via the /author/batch
    # endpoint. One extra API call, batches all authors of this paper.
    authors = work.get("authors") or []
    raw_authors = []
    author_ids_for_batch: list[str] = []
    for a in authors:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or "").strip()
        if not name:
            continue
        entry: dict = {"name": name}
        if a.get("authorId"):
            entry["ss_id"] = str(a["authorId"]).strip()
            author_ids_for_batch.append(entry["ss_id"])
        ext = a.get("externalIds") or {}
        if isinstance(ext, dict) and ext.get("ORCID"):
            entry["orcid"] = str(ext["ORCID"]).strip()
        aff_strs: list[str] = []
        for af in (a.get("affiliations") or []):
            if isinstance(af, str) and af.strip():
                aff_strs.append(af.strip())
            elif isinstance(af, dict) and af.get("name"):
                aff_strs.append(str(af["name"]).strip())
        if aff_strs:
            entry["affiliations"] = aff_strs
        raw_authors.append(entry)

    # Batch-fetch author profile stats (h-index etc.) — one extra call
    # even for papers with many authors. Silently degrades if SS is
    # rate-limited or the endpoint fails; the paper still extracts.
    if author_ids_for_batch:
        stats_batch = semanticscholar_author_batch(author_ids_for_batch)
        if isinstance(stats_batch, list):
            by_id: dict = {}
            for s in stats_batch:
                if isinstance(s, dict) and s.get("authorId"):
                    by_id[str(s["authorId"]).strip()] = s
            for entry in raw_authors:
                sid = entry.get("ss_id")
                if sid and sid in by_id:
                    st = by_id[sid]
                    if isinstance(st.get("hIndex"), int):
                        entry["h_index"] = st["hIndex"]
                    if isinstance(st.get("paperCount"), int):
                        entry["papers_count"] = st["paperCount"]
                    if isinstance(st.get("citationCount"), int):
                        entry["citation_count"] = st["citationCount"]

    if raw_authors:
        out["_ss_authors_raw"] = raw_authors

    # Publication venue metadata — SS's richer venue object.
    pv = work.get("publicationVenue") or {}
    if isinstance(pv, dict):
        if pv.get("type"):
            out["ss_venue_type"] = str(pv["type"]).strip()
        if pv.get("url"):
            out["ss_venue_url"] = str(pv["url"]).strip()
        alt = pv.get("alternate_names") or []
        alt_out = [str(x).strip() for x in alt if str(x).strip()]
        if alt_out:
            out["ss_venue_alternate_names"] = alt_out

    return out


