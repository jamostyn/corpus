"""OpenAlex per-entity enrichment — hits the /authors/<id>,
/institutions/<id>, /sources/<id> endpoints and caches results on disk.

Corpus's normal extraction pulls whatever OpenAlex embeds inside a
*work* record (per-paper metadata). But entity-level info — an
institution's works count, a journal's APC, an author's h-index —
lives on separate OpenAlex endpoints. Fetching them per-paper would be
wasteful (same institution appears on many papers); doing it at
aggregate time with a disk cache is exactly the right shape.

Cache layout:
    ~/.corpus/oa_cache/authors/<orcid-slug>.json
    ~/.corpus/oa_cache/institutions/<ror-slug>.json
    ~/.corpus/oa_cache/journals/<issn-slug>.json

Each cache file stores {fetched_at, data} — fetched_at lets the UI
show "updated N days ago" and lets us expire stale entries.

Uses CORPUS_MAILTO (OpenAlex polite pool) when set. No key needed.
Rate limit: ~10 req/s on the polite pool.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from _api_http import api_get_json

logger = logging.getLogger("corpus.oa_enrichment")

TIMEOUT = 10
DEFAULT_TTL_DAYS = 30


def _cache_root() -> Path:
    # Sibling of the config file so scratchpad tests don't touch real
    # ~/.corpus/ (honors CORPUS_CONFIG_PATH like tooltips/planning do).
    override = os.environ.get("CORPUS_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().parent / "oa_cache"
    return Path.home() / ".corpus" / "oa_cache"


def _slug(s: str) -> str:
    """Turn an identifier (ORCID URL, ROR URL, ISSN) into a filename-
    safe slug."""
    s = str(s or "").strip()
    # Drop protocol + host; keep the last meaningful segment.
    s = re.sub(r"^https?://[^/]+/", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "unknown"


def _cache_path(kind: str, key: str) -> Path:
    return _cache_root() / kind / f"{_slug(key)}.json"


def _read_cache(kind: str, key: str, ttl_days: int) -> dict | None:
    p = _cache_path(kind, key)
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    stamp = blob.get("fetched_at")
    if not stamp:
        return None
    try:
        fetched = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except Exception:
        return None
    age_days = (datetime.now(timezone.utc) - fetched).total_seconds() / 86400
    if age_days > ttl_days:
        return None
    return blob


def _write_cache(kind: str, key: str, data: dict) -> dict:
    p = _cache_path(kind, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data":       data or {},
    }
    p.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")
    return blob


def _fetch(url: str) -> dict | None:
    """GET JSON from OpenAlex. Returns None on any failure. Delegates
    to `_api_http.api_get_json` so the multi-context SSL retry (the
    macOS-standalone cert story) + logging are shared with the other
    OA callers. Failures land in ~/.corpus/logs/server.log."""
    return api_get_json(url, timeout=TIMEOUT)


# ---------- Public API — one function per entity type -----------------

def enrich_institution_by_ror(ror: str,
                                force: bool = False,
                                ttl_days: int = DEFAULT_TTL_DAYS) -> dict | None:
    """Look up an institution on OpenAlex by ROR ID (full URL or
    fragment). Returns the cached blob {fetched_at, data} or None if
    the fetch failed and nothing was cached.

    Cached fields (subset of OA's /institutions/<id> response that
    Corpus actually surfaces):
        id, display_name, ror, country_code, type, homepage_url,
        works_count, cited_by_count,
        geo: {city, region, country_code, latitude, longitude},
        summary_stats: {h_index, i10_index, 2yr_mean_citedness},
        x_concepts: [{display_name, score}, …]  (top-5, capped)
    """
    ror = (ror or "").strip()
    if not ror:
        return None
    # ROR full URL preferred by OA's API. Accept bare fragment too.
    if not ror.startswith("http"):
        ror = f"https://ror.org/{ror.lstrip('/')}"
    if not force:
        hit = _read_cache("institutions", ror, ttl_days)
        if hit is not None:
            return hit
    url = f"https://api.openalex.org/institutions/ror:{urllib.parse.quote(ror)}"
    raw = _fetch(url)
    if raw is None:
        return None
    # Slim the response to just what we surface — keeps cache files
    # small + stable across OA schema tweaks.
    concepts = raw.get("x_concepts") or []
    slim = {
        "id":              raw.get("id") or "",
        "display_name":    raw.get("display_name") or "",
        "ror":             raw.get("ror") or "",
        "country_code":    (raw.get("country_code") or "").upper(),
        "type":            raw.get("type") or "",
        "homepage_url":    raw.get("homepage_url") or "",
        "works_count":     raw.get("works_count"),
        "cited_by_count":  raw.get("cited_by_count"),
        "geo":             raw.get("geo") or {},
        "summary_stats":   raw.get("summary_stats") or {},
        "x_concepts":      [
            {"display_name": c.get("display_name"), "score": c.get("score")}
            for c in concepts[:5]
            if isinstance(c, dict) and c.get("display_name")
        ],
    }
    return _write_cache("institutions", ror, slim)


def enrich_journal_by_issn(issn: str,
                             force: bool = False,
                             ttl_days: int = DEFAULT_TTL_DAYS) -> dict | None:
    """Look up a journal / venue on OpenAlex by ISSN (XXXX-XXXX form
    or 8-digit without hyphen). OA accepts both electronic and print
    ISSNs at /sources/issn:<issn>. Returns the cached blob or None.

    Cached fields (subset of /sources/<id> Corpus surfaces):
        id, display_name, issn_l, issn, publisher, host_organization,
        works_count, cited_by_count, country_code, homepage_url,
        is_in_doaj, is_oa, type,
        apc_prices: [{price, currency}, …],
        summary_stats: {h_index, i10_index, 2yr_mean_citedness},
        x_concepts: [{display_name, score}, …]  (top-5)
    """
    issn = (issn or "").strip().upper().replace(" ", "")
    if not issn:
        return None
    # Normalize 8-digit → XXXX-XXXX for the cache key (OA accepts both).
    if len(issn) == 8 and "-" not in issn:
        issn = f"{issn[:4]}-{issn[4:]}"
    if not force:
        hit = _read_cache("journals", issn, ttl_days)
        if hit is not None:
            return hit
    url = f"https://api.openalex.org/sources/issn:{urllib.parse.quote(issn)}"
    raw = _fetch(url)
    if raw is None:
        return None
    concepts = raw.get("x_concepts") or []
    apcs = raw.get("apc_prices") or []
    slim = {
        "id":                raw.get("id") or "",
        "display_name":      raw.get("display_name") or "",
        "issn_l":            raw.get("issn_l") or "",
        "issn":              raw.get("issn") or [],
        "publisher":         raw.get("publisher") or "",
        "host_organization": raw.get("host_organization_name") or "",
        "works_count":       raw.get("works_count"),
        "cited_by_count":    raw.get("cited_by_count"),
        "country_code":      (raw.get("country_code") or "").upper(),
        "homepage_url":      raw.get("homepage_url") or "",
        "is_in_doaj":        raw.get("is_in_doaj"),
        "is_oa":             raw.get("is_oa"),
        "type":              raw.get("type") or "",
        "apc_prices":        [
            {"price": a.get("price"), "currency": a.get("currency")}
            for a in apcs if isinstance(a, dict) and a.get("price") is not None
        ],
        "summary_stats":     raw.get("summary_stats") or {},
        "x_concepts":        [
            {"display_name": c.get("display_name"), "score": c.get("score")}
            for c in concepts[:5]
            if isinstance(c, dict) and c.get("display_name")
        ],
    }
    return _write_cache("journals", issn, slim)


def enrich_author_by_orcid(orcid: str,
                             force: bool = False,
                             ttl_days: int = DEFAULT_TTL_DAYS) -> dict | None:
    """Look up an author on OpenAlex by ORCID (URL or bare 16-digit
    form). Hits /authors/orcid:<orcid>. Returns cached blob or None.

    Cached fields (slim subset of /authors/<id> response):
        id, orcid, display_name,
        works_count, cited_by_count,
        summary_stats: {h_index, i10_index, 2yr_mean_citedness},
        counts_by_year: [{year, works_count, cited_by_count}, …]  (last 15y),
        x_concepts: [{display_name, score}, …]  (top-5),
        last_known_institution: {display_name, ror, country_code, type}
    """
    orcid = (orcid or "").strip()
    if not orcid:
        return None
    # Strip URL prefix if present so we always look up by the bare 16-digit form.
    m = re.search(r"(\d{4}-\d{4}-\d{4}-[\dX]{4})", orcid)
    if not m:
        logger.info("oa_author_enrich_bad_orcid orcid=%r", orcid)
        return None
    bare = m.group(1)
    if not force:
        hit = _read_cache("authors", bare, ttl_days)
        if hit is not None:
            return hit
    # OpenAlex sometimes has multiple author records that share the
    # same ORCID (unmerged duplicates). /authors/orcid:<orcid> returns
    # whichever OA picked as canonical — and it's often the wrong one
    # (a sparse record with 1-2 works instead of the researcher's real
    # 400-work profile). Use the filter form which returns ALL
    # matching records so we can pick the one with the most works.
    # No `mailto` here: `_api_http.with_openalex_auth` adds the user's
    # real one. This line used to hard-code `mailto=x` — a fake address
    # that would also have blocked the real one being added.
    url = f"https://api.openalex.org/authors?filter=orcid:{bare}&per-page=25"
    listing = _fetch(url)
    raw = None
    if listing and isinstance(listing.get("results"), list) and listing["results"]:
        # Pick the record with the highest works_count — the merged/
        # primary profile. Ties fall back to cited_by_count.
        raw = max(listing["results"],
                   key=lambda r: (r.get("works_count") or 0,
                                    r.get("cited_by_count") or 0))
    if raw is None:
        # Fallback: single-record endpoint, in case filter didn't work.
        raw = _fetch(f"https://api.openalex.org/authors/orcid:{bare}")
    if raw is None:
        logger.warning("oa_author_enrich_empty orcid=%s (both filter + direct endpoint returned nothing)", bare)
        return None
    lki = raw.get("last_known_institution") or {}
    slim = {
        "id":                     raw.get("id") or "",
        "orcid":                  raw.get("orcid") or "",
        "display_name":           raw.get("display_name") or "",
        "works_count":            raw.get("works_count"),
        "cited_by_count":         raw.get("cited_by_count"),
        "summary_stats":          raw.get("summary_stats") or {},
        # Career trajectory — last ~15 years by default from OA. Trim
        # to something we can render as a small chart.
        "counts_by_year":         [
            {"year": c.get("year"),
             "works_count":    c.get("works_count"),
             "cited_by_count": c.get("cited_by_count")}
            for c in (raw.get("counts_by_year") or [])
            if isinstance(c, dict) and c.get("year")
        ][:15],
        "x_concepts":             [
            {"display_name": c.get("display_name"), "score": c.get("score")}
            for c in (raw.get("x_concepts") or [])[:5]
            if isinstance(c, dict) and c.get("display_name")
        ],
        "last_known_institution": {
            "display_name": lki.get("display_name") or "",
            "ror":          lki.get("ror") or "",
            "country_code": (lki.get("country_code") or "").upper(),
            "type":         lki.get("type") or "",
        } if lki else {},
    }
    return _write_cache("authors", bare, slim)
