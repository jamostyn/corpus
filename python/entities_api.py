"""Corpus — /api/authors, /api/institutions, /api/journals blueprint.

Extracted from server.py on 2026-08-16 (Wave-3 blueprint split).

Owns:
  * Three canonical key helpers (`_author_key`, `_institution_key`,
    `_journal_key`) — mirror the JS `EntityKeys.*` and are the source
    of truth for what `/api/<entity>/<key>` will accept.
  * Three aggregators (`_aggregate_authors`, `_aggregate_institutions`,
    `_aggregate_journals`) — walk every summary and merge entity-level
    metadata + provenance into keyed records.
  * `_merge_authors_by_display` — post-aggregation dedup that catches
    same-person / different-key drift.
  * `_enrichable_detail` — shared body for the three near-identical
    detail endpoints.
  * Six routes:
      GET /api/authors, GET /api/author/<key>
      GET /api/institutions, GET /api/institution/<key>
      GET /api/journals, GET /api/journal/<key>

Detail endpoints enrich with OpenAlex's per-entity data (author-by-
ORCID, institution-by-ROR, journal-by-ISSN) via
`oa_enrichment.enrich_*_by_*`, cached at
`~/.corpus/oa_cache/<entity>/<key>.json`.

Wired in server.py via `app.register_blueprint(entities_bp)`.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter, defaultdict

from flask import Blueprint, abort, jsonify, request

from _api_common import (
    _fm_dict,
    _parse_json_block,
    _strip_quotes,
    _walk_summaries,
    require_corpus_or_abort,
)
from _paths import summaries_dir

logger = logging.getLogger("corpus.entities_api")

entities_bp = Blueprint("entities", __name__)


# ---------- Canonical key helpers -----------------------------------
#
# Every /api/<entity>/<key> URL uses one of these to construct the
# key. The JS side (`src/entity-keys.js`) has parallel implementations
# that MUST produce byte-identical output; parity test at
# `tests/test_metadata.py::test_entity_key_python_parity`.

def _author_key(family: str, given: str) -> str:
    """Stable canonical author ID. Format: `<family-lower>-<given-lower>`
    with runs of non-alphanumeric collapsed to hyphens. Collisions
    across different people with the same slug are disambiguated later
    by ORCID / SS ID in the merge step."""
    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
        return s
    fam = _norm(family)
    giv = _norm(given.split()[0] if given else "")  # first token only ("B" from "B. J.")
    return f"{fam}-{giv}" if giv else fam


def _institution_key(name: str, ror: str) -> str:
    """Institution IDs prefer the ROR path fragment (canonical + stable
    across name variants). Fall back to a name slug when ROR is missing."""
    if ror:
        # ROR looks like "https://ror.org/01tgyzw49" — take the last segment.
        m = re.search(r"([a-z0-9]+)$", ror.strip())
        if m:
            return f"ror-{m.group(1)}"
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "unknown"


def _journal_key(name: str, issns: list) -> str:
    """Journal ID prefers the first ISSN (canonical + dedup-friendly
    across name variants), falling back to a name slug when no ISSN
    is available (books, gray literature, older journals)."""
    if issns:
        # Normalize ISSN to XXXX-XXXX (uppercase 'X' for check digit).
        v = str(issns[0]).strip().upper().replace(" ", "")
        return f"issn-{v}" if v else ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "unknown"


# ---------- Shared detail-endpoint wrapper --------------------------

def _enrichable_detail(aggregate_fn, key, id_getter, enricher):
    """Shared body for the three near-identical entity detail endpoints
    (`author_detail`, `institution_detail`, `journal_detail`).

    Each did:
        1. require_corpus_or_abort
        2. rec = aggregate_fn().get(key); 404 if None
        3. entity_id = extract enrichment key from rec
        4. if entity_id: rec["oa_enrichment*"] = enricher(entity_id, force=)
        5. jsonify(rec)

    `id_getter(rec)` returns the enrichment id (empty string = no
    enrichment). `enricher(entity_id, force=...)` returns the
    OA-cache blob dict or falsy."""
    require_corpus_or_abort()
    records = aggregate_fn()
    rec = records.get(key)
    if rec is None:
        abort(404)
    entity_id = (id_getter(rec) or "").strip() if id_getter else ""
    if entity_id:
        force = request.args.get("refresh") == "1"
        blob = enricher(entity_id, force=force)
        if blob:
            rec["oa_enrichment"]         = blob.get("data") or {}
            rec["oa_enrichment_fetched"] = blob.get("fetched_at") or ""
    return jsonify(rec)


# ---------- Journals aggregate + endpoints --------------------------

def _aggregate_journals() -> dict:
    """Walk every summary and merge venue-level metadata into one
    journal record per canonical key. Also stitches which sources
    contributed which fields (using each paper's *_from provenance).
    File-walk skeleton in `_walk_summaries`; JSON-block + quote-strip
    helpers at module scope."""
    result: dict = {}
    for slug, fm, _body in _walk_summaries():
        pub = str(fm.get("publisher") or "").strip()
        if not pub or pub.lower() == "unknown":
            continue
        # Normalize ISSN into a clean list (frontmatter stores it as a
        # list, but bare strings can slip through when only one exists).
        issns_raw = fm.get("issn") or []
        if isinstance(issns_raw, str): issns_raw = [issns_raw]
        issns = [_strip_quotes(x).upper() for x in issns_raw if _strip_quotes(x)]

        k = _journal_key(pub, issns)
        rec = result.setdefault(k, {
            "key":                k,
            "name":               pub,
            "issns":              [],
            "issns_from":         [],
            "host_organization":  "",
            "host_organization_from": [],
            "host_organization_lineage": [],
            "venue_type":         "",       # OA
            "venue_type_from":    [],
            "ss_venue_type":      "",       # SS
            "ss_venue_url":       "",
            "ss_venue_alternate_names": [],
            "papers":             [],
            "year_range":         "",
            "sources_seen":       set(),
        })
        # ISSN accretion — dedupe.
        for i in issns:
            if i and i not in rec["issns"]: rec["issns"].append(i)
        for src in fm.get("issn_from") or []:
            if src not in rec["issns_from"]: rec["issns_from"].append(src)
        # host_organization + lineage (OA)
        ho = str(fm.get("host_organization") or "").strip()
        if ho and not rec["host_organization"]:
            rec["host_organization"] = ho
            rec["host_organization_from"] = list(fm.get("host_organization_from") or ["openalex"])
        for l in fm.get("host_organization_lineage") or []:
            l = _strip_quotes(l)
            if l and l not in rec["host_organization_lineage"]:
                rec["host_organization_lineage"].append(l)
        # Venue types (OA + SS)
        vt = str(fm.get("venue_type") or "").strip()
        if vt and not rec["venue_type"]:
            rec["venue_type"] = vt
            rec["venue_type_from"] = list(fm.get("venue_type_from") or ["openalex"])
        svt = str(fm.get("ss_venue_type") or "").strip()
        if svt and not rec["ss_venue_type"]:
            rec["ss_venue_type"] = svt
        svu = str(fm.get("ss_venue_url") or "").strip()
        if svu and not rec["ss_venue_url"]:
            rec["ss_venue_url"] = svu
        for n in fm.get("ss_venue_alternate_names") or []:
            if n and n not in rec["ss_venue_alternate_names"]:
                rec["ss_venue_alternate_names"].append(n)

        # Paper contribution + source presence.
        rec["papers"].append({
            "slug":  slug,
            "title": str(fm.get("title") or "").strip(),
            "year":  str(fm.get("year") or "").strip(),
        })
        for src in fm.get("publisher_from") or []:
            rec["sources_seen"].add(src)

    # Cleanup for JSON.
    for k, rec in result.items():
        rec["papers"].sort(key=lambda p: str(p["year"]), reverse=True)
        years = [p["year"] for p in rec["papers"] if p["year"] and p["year"].isdigit()]
        rec["year_range"]   = f"{min(years)}–{max(years)}" if years else ""
        rec["sources_seen"] = sorted(rec["sources_seen"])
    return result


@entities_bp.route("/api/journals")
def list_journals():
    """Aggregated journal/venue list across every summary. Rows:
    key, name, issn (first if multiple), host_organization,
    venue_type, num_papers, year_range."""
    require_corpus_or_abort()
    js = _aggregate_journals()
    rows = []
    for j in js.values():
        rows.append({
            "key":               j["key"],
            "name":              j["name"],
            "issn":              (j["issns"][0] if j["issns"] else ""),
            "host_organization": j["host_organization"],
            "venue_type":        j["venue_type"] or j["ss_venue_type"],
            "num_papers":        len(j["papers"]),
            "year_range":        j["year_range"],
        })
    rows.sort(key=lambda r: (str(r["name"]).lower(),))
    return jsonify(rows)


@entities_bp.route("/api/journal/<key>")
def journal_detail(key):
    """Full journal record. Enriched with OpenAlex's
    /sources/issn:<issn> endpoint when an ISSN is known — surfaces
    country, homepage URL, is-in-DOAJ / is-OA, APC prices, works
    count, cited-by count, and impact-factor equivalent (2yr mean
    citedness). Cached at ~/.corpus/oa_cache/journals/<issn>.json.
    Journals without any ISSN (books, gray literature) skip enrichment."""
    from oa_enrichment import enrich_journal_by_issn
    return _enrichable_detail(
        _aggregate_journals, key,
        id_getter=lambda j: (j["issns"][0] if j.get("issns") else ""),
        enricher=enrich_journal_by_issn,
    )


# ---------- Institutions aggregate + endpoints ----------------------

def _aggregate_institutions() -> dict:
    """Walk every author's institutions across every summary, group by
    canonical institution key. Each entry accumulates {authors, papers,
    lineage, sources_seen}. Same JSON-safe cleanup as authors."""
    authors = _aggregate_authors()
    result: dict = {}
    for author_key, a in authors.items():
        for inst in a.get("institutions") or []:
            if not isinstance(inst, dict):
                continue
            name = str(inst.get("name") or "").strip()
            if not name:
                continue
            ror  = str(inst.get("ror") or "").strip()
            k    = _institution_key(name, ror)
            rec  = result.setdefault(k, {
                "key":          k,
                "name":         name,
                "ror":          ror,
                "country_code": str(inst.get("country_code") or "").strip(),
                "type":         str(inst.get("type") or "").strip(),
                "lineage":      list(inst.get("lineage") or []),  # OA IDs; opaque URLs
                "authors":      [],   # {key, family, given}
                "papers":       set(),  # slug set; converted to list at the end
                "sources_seen": set(),
            })
            # Enrich with any additional data (later authors may report a
            # ROR/country the first didn't).
            if ror         and not rec["ror"]:          rec["ror"]          = ror
            if inst.get("country_code") and not rec["country_code"]: rec["country_code"] = str(inst["country_code"]).strip()
            if inst.get("type") and not rec["type"]:    rec["type"]         = str(inst["type"]).strip()
            for l in inst.get("lineage") or []:
                if l and l not in rec["lineage"]: rec["lineage"].append(l)
            rec["authors"].append({
                "key":    author_key,
                "family": a["family"],
                "given":  a["given"],
            })
            for p in a.get("papers") or []:
                rec["papers"].add(p["slug"])
        # sources_seen — inherit union of the author's institutions_from
        # (which sources contributed institution data at all for this
        # author). Aggregate per institution too.
        for src in a.get("institutions_from") or []:
            for inst in a.get("institutions") or []:
                if not isinstance(inst, dict): continue
                k = _institution_key(inst.get("name",""), inst.get("ror",""))
                if k in result:
                    result[k]["sources_seen"].add(src)

    # Serializable cleanup + dedupe authors + attach paper details.
    all_slugs = {}
    for k, rec in result.items():
        # Dedupe authors by key
        seen = set(); deduped = []
        for a in rec["authors"]:
            if a["key"] in seen: continue
            seen.add(a["key"]); deduped.append(a)
        rec["authors"]      = sorted(deduped, key=lambda x: (x["family"].lower(), x["given"].lower()))
        rec["papers"]       = sorted(rec["papers"])
        rec["sources_seen"] = sorted(rec["sources_seen"])
        # Collect all slugs we need summaries for.
        for s in rec["papers"]: all_slugs[s] = None

    # Batch-load titles/years for all referenced papers.
    slug_meta = {}
    for slug in all_slugs:
        md = summaries_dir() / f"{slug}.md"
        fm = _fm_dict(md) if md.exists() else {}
        slug_meta[slug] = {
            "slug":  slug,
            "title": (str(fm.get("title") or "").strip() or slug) if fm else slug,
            "year":  str(fm.get("year") or "").strip(),
        }
    for k, rec in result.items():
        rec["papers"] = [slug_meta.get(s, {"slug": s, "title": s, "year": ""})
                          for s in rec["papers"]]
        rec["papers"].sort(key=lambda p: str(p["year"]), reverse=True)
    return result


@entities_bp.route("/api/institutions")
def list_institutions():
    """Aggregated institution list across every summary. Rows are
    lightweight: key, name, ror, country_code, type, num_authors,
    num_papers, sources_seen."""
    require_corpus_or_abort()
    insts = _aggregate_institutions()
    rows = []
    for i in insts.values():
        rows.append({
            "key":          i["key"],
            "name":         i["name"],
            "ror":          i["ror"],
            "country_code": i["country_code"],
            "type":         i["type"],
            "num_authors":  len(i["authors"]),
            "num_papers":   len(i["papers"]),
        })
    rows.sort(key=lambda r: (str(r["name"]).lower(),))
    return jsonify(rows)


@entities_bp.route("/api/institution/<key>")
def institution_detail(key):
    """Full institution record: authors + papers + lineage +
    per-source coverage of institution-level fields. Enriched with
    OpenAlex's /institutions/<id> endpoint when a ROR is known —
    surfaces homepage URL, geo, works count, cited-by count, associated
    concepts. Cached at ~/.corpus/oa_cache/institutions/<ror>.json."""
    from oa_enrichment import enrich_institution_by_ror
    return _enrichable_detail(
        _aggregate_institutions, key,
        id_getter=lambda i: i.get("ror") or "",
        enricher=enrich_institution_by_ror,
    )


# ---------- Authors aggregate + endpoints ---------------------------

# In-process author aggregate — recomputed on every request. Corpus
# sizes stay in the low thousands (each summary ~5-15 authors), so
# aggregating from scratch keeps the code simpler than an on-disk cache.
# File-walk skeleton in `_walk_summaries`; JSON-block helper at module
# scope.
def _aggregate_authors() -> dict:
    result: dict = {}
    for slug, fm, _body in _walk_summaries():
        paper_title = str(fm.get("title") or "").strip()
        paper_year  = str(fm.get("year") or "").strip()
        paper_doi   = str(fm.get("doi") or "").strip().lower()
        oa_authors  = _parse_json_block(fm.get("oa_authors"))
        oa_by_name  = {}
        for oa in oa_authors:
            if isinstance(oa, dict) and oa.get("family"):
                oa_by_name[str(oa["family"]).strip().lower()] = oa
        ss_raw = fm.get("_ss_authors_raw") or []
        ss_by_name = {}
        for ss in ss_raw if isinstance(ss_raw, list) else []:
            if isinstance(ss, dict) and ss.get("name"):
                fam = str(ss["name"]).split()[-1].lower()
                ss_by_name[fam] = ss

        # authors_detailed is our canonical Crossref-supplied ordering.
        detailed = fm.get("authors_detailed") or []
        for a in detailed if isinstance(detailed, list) else []:
            fam = str((a or {}).get("family", "")).strip()
            giv = str((a or {}).get("given", "")).strip()
            if not fam:
                continue
            k = _author_key(fam, giv)
            fam_lower = fam.lower()
            oa = oa_by_name.get(fam_lower) or {}
            ss = ss_by_name.get(fam_lower) or {}

            rec = result.setdefault(k, {
                "key":               k,
                "family":            fam,
                "given":             giv,
                "orcid":             "",
                "orcid_from":        [],
                "position_counts":   Counter(),
                "corresponding_on":  [],
                "institutions":      [],
                "institutions_from": [],
                "raw_affiliations":  [],
                "h_index":           None,
                "papers_count_ss":   None,
                "citation_count_ss": None,
                "ss_id":             "",
                "papers":            [],  # per-paper contributions
                "sources_seen":      set(),
            })

            # ORCID — prefer OA (URL form), then Crossref, then SS.
            orcid_val = ""
            for source_name, src in (("openalex", oa), ("crossref", a), ("semanticscholar", ss)):
                v = (src.get("orcid") or "").strip() if isinstance(src, dict) else ""
                if v and not orcid_val:
                    orcid_val = v
                    if source_name not in rec["orcid_from"]:
                        rec["orcid_from"].append(source_name)
                elif v and source_name not in rec["orcid_from"]:
                    rec["orcid_from"].append(source_name)
            if orcid_val and not rec["orcid"]:
                rec["orcid"] = orcid_val

            # Position: prefer OA's canonical vocabulary; fall back to Crossref-derived.
            pos = (oa.get("position") if isinstance(oa, dict) else "") or a.get("position") or ""
            if pos:
                rec["position_counts"][str(pos).lower()] += 1

            # Corresponding author — only OA reliably marks this.
            if isinstance(oa, dict) and oa.get("is_corresponding"):
                rec["corresponding_on"].append(slug)

            # Institutions — merge OA's structured records + Crossref strings.
            for inst in (oa.get("institutions") or []) if isinstance(oa, dict) else []:
                if isinstance(inst, dict) and inst.get("name"):
                    entry = {
                        "name":         str(inst["name"]).strip(),
                        "ror":          str(inst.get("ror") or "").strip(),
                        "country_code": str(inst.get("country_code") or "").strip().upper(),
                        "type":         str(inst.get("type") or "").strip(),
                    }
                    if entry["name"] and entry["name"] not in [i["name"] for i in rec["institutions"]]:
                        rec["institutions"].append(entry)
                        if "openalex" not in rec["institutions_from"]:
                            rec["institutions_from"].append("openalex")
            for inst_str in a.get("institutions") or []:
                if isinstance(inst_str, str) and inst_str.strip():
                    name = inst_str.strip()
                    if name not in [i["name"] for i in rec["institutions"]]:
                        rec["institutions"].append({"name": name, "ror": "", "country_code": "", "type": ""})
                        if "crossref" not in rec["institutions_from"]:
                            rec["institutions_from"].append("crossref")
            for ss_aff in (ss.get("affiliations") or []) if isinstance(ss, dict) else []:
                if isinstance(ss_aff, str) and ss_aff.strip():
                    name = ss_aff.strip()
                    if name not in [i["name"] for i in rec["institutions"]]:
                        rec["institutions"].append({"name": name, "ror": "", "country_code": "", "type": ""})
                    if "semanticscholar" not in rec["institutions_from"]:
                        rec["institutions_from"].append("semanticscholar")

            # Raw affiliation strings (OA)
            for raw in (oa.get("raw_affiliations") or []) if isinstance(oa, dict) else []:
                if isinstance(raw, str) and raw.strip() and raw not in rec["raw_affiliations"]:
                    rec["raw_affiliations"].append(raw.strip())

            # SS author profile stats — take the max seen so far (SS
            # values grow over time as new papers are indexed).
            def _upd_max(cur, new):
                if not isinstance(new, int): return cur
                return new if cur is None or new > cur else cur
            if isinstance(ss, dict):
                rec["h_index"]           = _upd_max(rec["h_index"],           ss.get("h_index"))
                rec["papers_count_ss"]   = _upd_max(rec["papers_count_ss"],   ss.get("papers_count"))
                rec["citation_count_ss"] = _upd_max(rec["citation_count_ss"], ss.get("citation_count"))
                if ss.get("ss_id") and not rec["ss_id"]:
                    rec["ss_id"] = ss["ss_id"]

            # Track which sources contributed anything for this author.
            if a: rec["sources_seen"].add("crossref")
            if oa: rec["sources_seen"].add("openalex")
            if ss: rec["sources_seen"].add("semanticscholar")

            rec["papers"].append({
                "slug":      slug,
                "title":     paper_title,
                "year":      paper_year,
                "doi":       paper_doi,
                "position":  str(pos).lower(),
                "is_corresponding": bool(isinstance(oa, dict) and oa.get("is_corresponding")),
            })

    # Defensive post-aggregation dedup — merge any records whose
    # DISPLAY (normalized family + given) is identical but whose
    # `_author_key`s ended up different. This catches subtle byte
    # differences across papers (invisible unicode, spacing variants)
    # that produced two records for what's visibly the same person.
    result = _merge_authors_by_display(result)

    # Serializable cleanup — Counter → dict, set → list.
    # Dedupe papers by DOI: two summaries with the same DOI (usually
    # because one PDF was slugged twice while cleaning up a rename)
    # would otherwise show as duplicate entries in the author's paper
    # list. Keep the first occurrence per DOI. Slugs without a DOI
    # (unknown / preprint / etc.) can't dedupe — they stay as-is.
    for k, rec in result.items():
        rec["position_counts"] = dict(rec["position_counts"])
        rec["sources_seen"]    = sorted(rec["sources_seen"])
        seen_doi = set()
        deduped = []
        for p in rec["papers"]:
            doi = (p.get("doi") or "").strip().lower()
            if doi and doi != "unknown":
                if doi in seen_doi: continue
                seen_doi.add(doi)
            deduped.append(p)
        rec["papers"] = sorted(deduped, key=lambda p: str(p["year"]), reverse=True)
    return result


def _merge_authors_by_display(result: dict) -> dict:
    """Merge author records whose DISPLAY (normalized family + given)
    matches but whose `_author_key`s differ. `_author_key` uses only
    the first token of `given` and can produce distinct keys when
    subtle byte differences appear across papers (invisible unicode,
    NBSP spacing, HTML entities, etc.). This second pass groups by
    the FULL normalized (family, given) and merges collisions into
    a single record.

    Merge policy:
      * Survivor key = shortest (most canonical) tie-broken alphabetically.
      * Papers merged and deduped by slug.
      * Institutions merged and deduped by name.
      * Scalar-max fields (h_index, papers_count_ss, citation_count_ss)
        take the max seen.
      * List-of-string fields (orcid_from, institutions_from,
        corresponding_on, raw_affiliations) merged preserving order.
      * position_counts summed.
      * sources_seen unioned.
      * Scalar-first-write fields (orcid, ss_id) prefer survivor,
        fall back to other.
    """
    def _dkey(rec):
        # Strip ALL non-alnum (not just collapse) so "Han Gyol" +
        # "HanGyol" + "Han-Gyol" all reduce to the same "hangyol".
        # These variants show up when Crossref reformats a name
        # across two papers for what's visibly the same person.
        fam = re.sub(r"[^a-z0-9]", "", (rec.get("family") or "").lower())
        giv = re.sub(r"[^a-z0-9]", "", (rec.get("given")  or "").lower())
        # Primary institution guards against false-merging two
        # different people who happen to share a family name at
        # different universities.
        primary_inst = re.sub(r"[^a-z0-9]", "",
                              (rec["institutions"][0]["name"] if rec["institutions"] else "").lower())
        return (fam, giv, primary_inst)

    groups: dict = defaultdict(list)
    for key, rec in result.items():
        groups[_dkey(rec)].append(key)

    merged: dict = {}
    for group_keys in groups.values():
        if len(group_keys) == 1:
            k = group_keys[0]
            merged[k] = result[k]
            continue
        # Survivor = shortest key, tie-broken alphabetically.
        group_keys.sort(key=lambda k: (len(k), k))
        survivor_k = group_keys[0]
        survivor   = result[survivor_k]
        for other_k in group_keys[1:]:
            other = result[other_k]
            # Papers — dedupe by slug.
            seen_slugs = {p["slug"] for p in survivor["papers"]}
            for p in other["papers"]:
                if p["slug"] not in seen_slugs:
                    survivor["papers"].append(p)
                    seen_slugs.add(p["slug"])
            # Institutions — dedupe by name.
            seen_inst = {i["name"] for i in survivor["institutions"]}
            for i in other["institutions"]:
                if i["name"] not in seen_inst:
                    survivor["institutions"].append(i)
                    seen_inst.add(i["name"])
            # Scalar-max fields.
            for f in ("h_index", "papers_count_ss", "citation_count_ss"):
                v = other.get(f)
                if isinstance(v, int) and (survivor.get(f) is None or v > survivor[f]):
                    survivor[f] = v
            # List-of-string fields (order-preserving dedup).
            for f in ("orcid_from", "institutions_from", "corresponding_on", "raw_affiliations"):
                for v in other.get(f) or []:
                    if v not in survivor[f]:
                        survivor[f].append(v)
            # Counters.
            for pos, count in (other.get("position_counts") or Counter()).items():
                survivor["position_counts"][pos] = survivor["position_counts"].get(pos, 0) + count
            # Sets.
            survivor["sources_seen"] |= other.get("sources_seen") or set()
            # First-write scalars.
            for f in ("orcid", "ss_id"):
                if not survivor.get(f) and other.get(f):
                    survivor[f] = other[f]
        logger.info("author_dedupe_merged survivor=%s dropped=%s reason=display_match",
                    survivor_k, group_keys[1:])
        merged[survivor_k] = survivor
    return merged


@entities_bp.route("/api/authors")
def list_authors():
    """Aggregated author list across every summary. Returns lightweight
    rows (key, family, given, orcid, num_papers, primary_institution,
    h_index, papers_count_ss, citation_count_ss) — enough for the
    sidebar list and filter/sort in the UI."""
    require_corpus_or_abort()
    authors = _aggregate_authors()
    rows = []
    for a in authors.values():
        rows.append({
            "key":                a["key"],
            "family":             a["family"],
            "given":              a["given"],
            "orcid":              a["orcid"],
            "num_papers":         len(a["papers"]),
            "primary_institution": (a["institutions"][0]["name"] if a["institutions"] else ""),
            "h_index":            a["h_index"],
            "papers_count_ss":    a["papers_count_ss"],
            "citation_count_ss":  a["citation_count_ss"],
        })
    rows.sort(key=lambda r: (str(r["family"]).lower(), str(r["given"]).lower()))
    return jsonify(rows)


@entities_bp.route("/api/author/<key>")
def author_detail(key):
    """Full author record with papers-by-author + per-source coverage
    of author-level fields. Enriched with OpenAlex's /authors/<id>
    endpoint when an ORCID is known — surfaces OA-side h-index / works /
    citations (verifier for SS's numbers), career citations-by-year,
    topic footprint, and last-known institution."""
    from oa_enrichment import enrich_author_by_orcid
    return _enrichable_detail(
        _aggregate_authors, key,
        id_getter=lambda a: a.get("orcid") or "",
        enricher=enrich_author_by_orcid,
    )
