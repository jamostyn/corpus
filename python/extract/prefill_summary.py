#!/usr/bin/env python3
"""
prefill_summary.py

Orchestrator that runs the deterministic extractors and writes a partial
`summaries/<slug>.md` so the summary agent only has to fill in narrative
fields (caveman_summary, findings, methods, hypothesis, abstract) +
verify the pre-filled frontmatter / refs and correct anything that looks
wrong.

What gets PRE-FILLED (no LLM tokens):
  - YAML frontmatter: author, authors_full, authors_detailed, year, title,
    publisher, doi, source_url, pages, kind, pdf_link, projects (default
    []), pdf_available, summary_status (set to "pending"),
    added_at, last_summarized, citation_count (unknown)
  - References list — every line with `in_corpus: false` (fix_in_corpus
    flips later)

What stays for the LLM agent:
  - All narrative sections: Caveman Summary, Question, Approach,
    Findings, Framing, Limitations, Open Questions
  - Project tag verification / theme cluster assignment
  - Visual sanity check on pre-filled fields (the agent should fix any
    obvious wrongness — e.g. Crossref returns a stale title)

Usage:
  python3 prefill_summary.py papers/smith-2023.pdf
  python3 prefill_summary.py papers/smith-2023.pdf --out -
  python3 prefill_summary.py papers/smith-2023.pdf --force

Default writes to summaries/<slug>.md. Refuses to overwrite an existing
complete summary unless --force is passed.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

# Sibling-script imports — this directory on sys.path.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import re                                                            # noqa: E402
import unicodedata                                                   # noqa: E402

from extract_metadata import extract_metadata                       # noqa: E402
from extract_references import extract_references_from_crossref     # noqa: E402


# ---------- Canonical slug ----------

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Latin-alphabet letters that unicodedata.normalize NFKD doesn't decompose
# (they're not combining-diacritic sequences — they're distinct letters).
# Without this map, `.encode("ASCII", "ignore")` drops them entirely, so
# Ørskov → rskov and Straße → strae. Bad.
_LATIN_MAP = str.maketrans({
    "Ø": "O", "ø": "o",
    "Æ": "AE", "æ": "ae",
    "Œ": "OE", "œ": "oe",
    "ß": "ss",
    "Ł": "L", "ł": "l",
    "Đ": "D", "đ": "d",
    "Ð": "D", "ð": "d",
    "Þ": "Th", "þ": "th",
    "İ": "I", "ı": "i",
})


def canonical_slug_for(meta: dict) -> str:
    """Compute the canonical slug `<surname>-<year>` from extracted
    metadata. Returns "" if we can't (missing year or surname).

    The filename is NEVER an input — this uses only the metadata the
    APIs (or PDF /Info) actually produced. The most reputable available
    source wins (Crossref first, per extract_metadata's precedence).

    Surname resolution order (each falls back only if empty):
      1. authors_detailed[0].family   (structured, cleanest)
      2. authors_full[0] split on space (typically 'Family I.')
      3. author field split on comma  ('Family, I.')
    """
    year = meta.get("year")
    if not year or str(year).strip().lower() in ("", "unknown"):
        return ""

    surname = ""
    detailed = meta.get("authors_detailed") or []
    if detailed:
        surname = (detailed[0].get("family") or "").strip()
    if not surname:
        af = meta.get("authors_full") or []
        if af:
            first = str(af[0]).strip()
            surname = first.split()[0] if first else ""
    if not surname:
        auth = str(meta.get("author") or "").strip()
        if auth:
            surname = auth.split(",", 1)[0].strip()
    if not surname:
        return ""

    # Normalize: map special Latin letters that don't decompose (Ø, ß,
    # etc.), then strip accents/diacritics (Apšvalka → Apsvalka),
    # lowercase, strip non-alphanumerics.
    surname = surname.translate(_LATIN_MAP)
    surname = unicodedata.normalize("NFKD", surname)
    surname = "".join(c for c in surname if not unicodedata.combining(c))
    surname = surname.encode("ASCII", "ignore").decode("ASCII")
    surname = _SLUG_STRIP.sub("", surname.lower())
    if not surname:
        return ""

    return f"{surname}-{year}"


def _yaml_str(s: str) -> str:
    """Render a string as a safe YAML scalar. Quote if it contains
    characters that would otherwise break parsing (colon, leading -, etc.)
    """
    if s is None:
        return "unknown"
    s = str(s).strip()
    if not s:
        return '""'
    if any(c in s for c in ':#"\n') or s[:1] in "-?[{|>!*&%":
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _yaml_list(items: list[str]) -> str:
    """Render a string list inline: [a, b, c]."""
    return "[" + ", ".join(items) + "]"


def _yaml_list_quoted(items: list[str]) -> str:
    """Render a string list inline with each item double-quoted:
    [\"a\", \"b\"]. Use for lists whose items may contain commas or
    colons that would confuse the inline-list parser otherwise."""
    if not items:
        return "[]"
    esc = ['"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"' for s in items]
    return "[" + ", ".join(esc) + "]"


def _yaml_json_block(key: str, data) -> list[str]:
    """Emit a nested structure (list of dicts, dict, etc.) as a YAML
    literal block scalar (`|`) containing pretty-printed JSON.

    _fm.py's parser handles block scalars fine (returns them as a
    single string), so the frontend can just JSON.parse the value.
    We use this for OA's per-author institution hierarchies, topics,
    keywords, locations, versions — anything with nested dicts inside
    lists that would otherwise need flow-mapping-inside-flow-mapping
    (which _fm.py doesn't support)."""
    import json as _json
    payload = _json.dumps(data, ensure_ascii=False, indent=2)
    lines = [f"{key}: |"]
    for jline in payload.splitlines():
        lines.append(f"  {jline}")
    return lines


def _yaml_flow_str_list(strings: list[str]) -> str:
    """Empty list → `[]`. Non-empty → `["a", "b"]` with double-quote
    escaping. Used inside per-author / per-funder flow mappings where
    strings can carry commas / colons that would confuse the plain
    inline-list parser."""
    if not strings:
        return "[]"
    return "[" + ", ".join(
        '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' for s in strings
    ) + "]"


# ---- Emit-if-present helpers ---------------------------------------
# Each mutates `lines` in place. The `_if` suffix means "append only
# when the value is truthy" (or, for the int/bool variants, only when
# the specific type test passes). Keeps `render_frontmatter` readable
# as a sequence of "emit this field if it's set" statements instead
# of 300+ lines of interleaved if-blocks.

def _emit_scalar_if(lines: list[str], key: str, value) -> None:
    """`key: "value"` (yaml-string-escaped). Skip when falsy."""
    if value:
        lines.append(f"{key}: {_yaml_str(str(value))}")


def _emit_list_quoted_if(lines: list[str], key: str, items) -> None:
    """`key: ["a", "b"]`. Skip when empty."""
    if items:
        lines.append(f"{key}: {_yaml_list_quoted(items)}")


def _emit_int_if(lines: list[str], key: str, value) -> None:
    """`key: 42`. Skip unless value is a bare int (booleans excluded
    because `isinstance(True, int)` is True in Python)."""
    if isinstance(value, int) and not isinstance(value, bool):
        lines.append(f"{key}: {value}")


def _emit_bool_flag(lines: list[str], key: str, value) -> None:
    """`key: true|false`. Emit whenever value is not None (either
    branch renders). Used for `is_oa`, `has_fulltext`, `is_paratext`
    where "unknown" and "no" are meaningfully different states."""
    if value is not None:
        lines.append(f"{key}: {'true' if value else 'false'}")


def _emit_block_scalar_if(lines: list[str], key: str, text) -> None:
    """`key: |\\n  line1\\n  line2`. Skip when empty/whitespace."""
    text = (text or "").strip()
    if not text:
        return
    lines.append(f"{key}: |")
    for tl in str(text).splitlines():
        lines.append(f"  {tl}")


def _emit_json_block_if(lines: list[str], key: str, data) -> None:
    """`key: |` followed by pretty-printed JSON. Skip when empty."""
    if data:
        lines.extend(_yaml_json_block(key, data))


# ---- Complex-shape emitters ----------------------------------------
# One function per fancy YAML shape. Each returns nothing and appends
# to `lines`. Isolated so `render_frontmatter` reads as prose.

def _emit_authors_detailed(lines: list[str], entries) -> None:
    """`authors_detailed:` block of flow mappings — one per author.
    Entry schema: {family, given, institutions[], departments[],
    orcid?, position?}. Handles both new (institutions: list) and
    legacy (institution: string) input shapes."""
    if not entries:
        return
    lines.append("authors_detailed:")
    for a in entries:
        fam = _yaml_str(a.get("family", ""))
        giv = a.get("given", "") or ""
        raw_insts = a.get("institutions")
        if isinstance(raw_insts, list):
            insts = [str(s).strip() for s in raw_insts if str(s).strip()]
        else:
            single = (a.get("institution") or "").strip()
            insts = [single] if single else []
        depts = ["unknown"] * len(insts)
        insts_str = _yaml_flow_str_list(insts)
        depts_str = "[" + ", ".join(depts) + "]" if depts else "[]"
        extra = ""
        if a.get("orcid"):
            extra += f', orcid: {_yaml_str(a["orcid"])}'
        if a.get("position"):
            extra += f', position: {_yaml_str(a["position"])}'
        lines.append(
            f'  - {{family: {fam}, given: "{giv}", '
            f'institutions: {insts_str}, departments: {depts_str}{extra}}}'
        )


def _emit_funder(lines: list[str], entries) -> None:
    if not entries:
        return
    lines.append("funder:")
    for fn in entries:
        awards = fn.get("awards") or []
        awards_str = _yaml_list_quoted(awards) if awards else "[]"
        lines.append(
            f'  - {{name: {_yaml_str(fn.get("name") or "unknown")}, '
            f'doi: {_yaml_str(fn.get("doi") or "unknown")}, '
            f'awards: {awards_str}}}'
        )


def _emit_license(lines: list[str], entries) -> None:
    if not entries:
        return
    lines.append("license:")
    for lic in entries:
        lines.append(
            f'  - {{url: {_yaml_str(lic.get("url") or "unknown")}, '
            f'type: {_yaml_str(lic.get("type") or "unspecified")}, '
            f'delay_days: {int(lic.get("delay_days") or 0)}}}'
        )


def _emit_update_to(lines: list[str], entries) -> None:
    if not entries:
        return
    lines.append("update_to:")
    for u in entries:
        lines.append(
            f'  - {{doi: {_yaml_str(u.get("doi") or "unknown")}, '
            f'type: {_yaml_str(u.get("type") or "unknown")}, '
            f'label: {_yaml_str(u.get("label") or "")}}}'
        )


def _emit_ss_only_refs(lines: list[str], entries) -> None:
    """`ss_only_refs:` block of flow mappings. Sparse — each entry
    emits only the sub-keys it actually has (doi/title/year)."""
    if not entries:
        return
    lines.append("ss_only_refs:")
    for r in entries:
        parts: list[str] = []
        if r.get("doi"):   parts.append(f'doi: {_yaml_str(r["doi"])}')
        if r.get("title"): parts.append(f'title: {_yaml_str(r["title"])}')
        if r.get("year"):  parts.append(f'year: {r["year"]}')
        lines.append(f"  - {{{', '.join(parts)}}}")


def _emit_s2_fields_of_study(lines: list[str], entries) -> None:
    if not entries:
        return
    lines.append("s2_fields_of_study:")
    for f in entries:
        lines.append(
            f'  - {{category: {_yaml_str(f.get("category") or "unknown")}, '
            f'source: {_yaml_str(f.get("source") or "unknown")}}}'
        )


def _emit_ss_authors_raw(lines: list[str], entries) -> None:
    """`_ss_authors_raw:` block of flow mappings. Sparse — only
    emits sub-keys that are present. Author profile stats
    (h_index / papers_count / citation_count) come from the SS
    /author/batch enrichment and may be missing on entries added
    before that field was populated."""
    if not entries:
        return
    lines.append("_ss_authors_raw:")
    for a in entries:
        parts = [f'name: {_yaml_str(a.get("name") or "unknown")}']
        if a.get("ss_id"):        parts.append(f'ss_id: {_yaml_str(a["ss_id"])}')
        if a.get("orcid"):        parts.append(f'orcid: {_yaml_str(a["orcid"])}')
        if a.get("affiliations"): parts.append(f'affiliations: {_yaml_list_quoted(a["affiliations"])}')
        if isinstance(a.get("h_index"), int):        parts.append(f'h_index: {a["h_index"]}')
        if isinstance(a.get("papers_count"), int):   parts.append(f'papers_count: {a["papers_count"]}')
        if isinstance(a.get("citation_count"), int): parts.append(f'citation_count: {a["citation_count"]}')
        lines.append(f"  - {{{', '.join(parts)}}}")


def _emit_embedding(lines: list[str], vec) -> None:
    """`embedding: [f, f, f, ...]` — inline list of ~768 floats,
    fixed 6-decimal formatting for stability across runs. Long line,
    but _fm.py's inline-list parser handles it."""
    if not (isinstance(vec, list) and vec):
        return
    inner = ", ".join(f"{float(x):.6f}" for x in vec)
    lines.append(f"embedding: [{inner}]")


def _emit_provenance(lines: list[str], provenance: dict, fields) -> None:
    """One `<field>_from: [source, ...]` line per tracked field. List
    is [winner, ...verifiers] — presence of >1 element means multiple
    APIs returned the same value (confirmed). Skips fields without
    provenance."""
    for field in fields:
        srcs = (provenance or {}).get(field) or []
        if srcs:
            lines.append(f"{field}_from: [{', '.join(srcs)}]")


def _preserved_added_at(target: Path | None) -> str | None:
    """If a summary already exists at `target`, return its original
    `added_at` value so re-extraction preserves it. Returns None if
    there's no existing summary or the field can't be found."""
    if target is None or not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    import re as _re
    m = _re.search(r"^added_at:\s*(\S+)\s*$", text, flags=_re.MULTILINE)
    return m.group(1).strip('"\'') if m else None


def render_frontmatter(slug: str, meta: dict,
                        added_at: str | None = None) -> str:
    """Emit the YAML frontmatter block for one summary MD.

    Structure (top to bottom):
      1. Always-emitted header (author, title, year, canonical scalars,
         citation_count, provenance-of-source flags).
      2. Optional Crossref extras (volume/issue/language/issn/…).
      3. Retraction + updates + funder + license + event.
      4. SS-derived (counts, refs-cross-check, publication_types,
         s2_fos, open-access PDF, external IDs, TL;DR/abstract/bibtex/
         embedding, raw author list).
      5. OA-derived (citation_count_oa, fwci, oa_status, is_oa,
         retraction_notice, nested JSON blocks).
      6. Bibliographic extensions (edition_number, deposited_at…).
      7. SS venue + OA venue metadata.
      8. Per-field provenance loop (`<field>_from` lines).
      9. `pages` pass-through.
      10. Closing `---`.

    Complex-shape emitters (authors_detailed, funder, license,
    ss_only_refs, s2_fields_of_study, _ss_authors_raw, embedding) live
    as module-level helpers so this orchestrator reads as prose.
    """
    now = _dt.datetime.now().replace(microsecond=0).isoformat()
    added_at = added_at or now
    pdf_link = f"papers/{slug}.pdf"
    lines: list[str] = ["---"]

    # ---- Always-emitted core -------------------------------------------
    authors_full = meta.get("authors_full") or []
    lines.append(f"author: {_yaml_str(meta.get('author', 'unknown'))}")
    lines.append(f"authors_full: {_yaml_list(authors_full) if authors_full else '[]'}")
    _emit_authors_detailed(lines, meta.get("authors_detailed"))
    lines.extend([
        f"year: {meta.get('year', 'unknown')}",
        f"title: {_yaml_str(meta.get('title', 'unknown'))}",
        f"kind: {meta.get('kind') or 'article'}",
        f"paper_type: {meta.get('paper_type') or 'unknown'}",
        f"publisher: {_yaml_str(meta.get('publisher', 'unknown'))}",
        f"doi: {meta.get('doi') or 'unknown'}",
        f"source_url: {_yaml_str(meta.get('source_url', 'unknown'))}",
        f"pdf_link: {pdf_link}",
        "pdf_available: true",
        f"status: {meta.get('status') or 'prefilled'}",
        f"added_at: {added_at}",
        f"last_extracted: {now}",
        f"citation_count: {meta['citation_count'] if isinstance(meta.get('citation_count'), int) else 'unknown'}",
        f"citation_count_as_of: {now}",
        "schema_version: corpus-v0.1",
        f"metadata_source: {_yaml_str((meta.get('sources') or ['unknown'])[0] if meta.get('sources') else 'unknown')}",
        f"refs_source: {meta.get('refs_source') or 'none'}",
    ])
    if meta.get("needs_doi"):
        lines.append("needs_doi: true")

    # ---- Extended Crossref scalars + string lists ----------------------
    for f in ("volume", "issue", "article_number", "language"):
        _emit_scalar_if(lines, f, meta.get(f))
    for f in ("issn", "isbn", "alternative_ids", "subjects"):
        _emit_list_quoted_if(lines, f, meta.get(f))
    _emit_int_if(lines, "references_count", meta.get("references_count"))

    # ---- Retraction + updates + funder + license + event ---------------
    if meta.get("retracted"):
        lines.append("retracted: true")
    _emit_update_to(lines, meta.get("update_to"))
    _emit_scalar_if(lines, "update_policy", meta.get("update_policy"))
    _emit_funder(lines, meta.get("funder"))
    _emit_license(lines, meta.get("license"))
    for f in ("event_name", "event_acronym", "event_location"):
        _emit_scalar_if(lines, f, meta.get(f))

    # ---- Semantic Scholar-derived fields --------------------------------
    _emit_int_if(lines, "citation_count_ss",             meta.get("citation_count_ss"))
    _emit_int_if(lines, "influential_citation_count_ss", meta.get("influential_citation_count_ss"))
    for f in ("refs_crossref_count", "refs_ss_count",
               "refs_confirmed_by_ss", "refs_ss_only"):
        _emit_int_if(lines, f, meta.get(f))
    _emit_list_quoted_if(lines, "ss_confirmed_dois", meta.get("ss_confirmed_dois"))
    _emit_ss_only_refs(lines, meta.get("ss_only_refs"))
    _emit_list_quoted_if(lines, "publication_types", meta.get("publication_types"))
    _emit_s2_fields_of_study(lines, meta.get("s2_fields_of_study"))
    for f in ("open_access_pdf_url", "open_access_pdf_status", "open_access_pdf_license"):
        _emit_scalar_if(lines, f, meta.get(f))
    _emit_scalar_if(lines, "ss_paper_id", meta.get("ss_paper_id"))
    # Flattened SS external IDs (arXiv, PubMed, MAG, DBLP, ...). Iterate
    # meta in insertion order so output is deterministic.
    for k, v in meta.items():
        if k.startswith("ss_") and k.endswith("_id") and k != "ss_paper_id" and v:
            lines.append(f"{k}: {_yaml_str(str(v))}")
    _emit_scalar_if(lines, "tldr_model",      meta.get("tldr_model"))
    _emit_scalar_if(lines, "embedding_model", meta.get("embedding_model"))
    _emit_ss_authors_raw(lines, meta.get("_ss_authors_raw"))

    # ---- Text-block content --------------------------------------------
    _emit_block_scalar_if(lines, "tldr",     meta.get("tldr"))
    _emit_block_scalar_if(lines, "abstract", meta.get("abstract"))
    _emit_block_scalar_if(lines, "bibtex",   meta.get("bibtex"))
    _emit_embedding(lines, meta.get("embedding"))

    # ---- OpenAlex-derived scalars + booleans ---------------------------
    _emit_int_if(lines, "citation_count_oa", meta.get("citation_count_oa"))
    if isinstance(meta.get("fwci"), (int, float)):
        lines.append(f"fwci: {float(meta['fwci']):.4f}")
    _emit_scalar_if(lines, "oa_status", meta.get("oa_status"))
    _emit_bool_flag(lines, "is_oa", meta.get("is_oa"))
    _emit_scalar_if(lines, "oa_paper_id", meta.get("oa_paper_id"))
    _emit_block_scalar_if(lines, "retraction_notice", meta.get("retraction_notice"))

    # ---- Nested JSON block scalars -------------------------------------
    for f in ("oa_authors", "topics", "keywords", "oa_locations",
               "counts_by_year", "versions", "content_assertions"):
        _emit_json_block_if(lines, f, meta.get(f))

    # ---- Bibliographic extensions (Crossref) + venue metadata ----------
    for f in ("edition_number", "chapter_number", "component_number",
               "journal_issue_date", "deposited_at", "indexed_at"):
        _emit_scalar_if(lines, f, meta.get(f))
    for f in ("ss_venue_type", "ss_venue_url"):
        _emit_scalar_if(lines, f, meta.get(f))
    _emit_list_quoted_if(lines, "ss_venue_alternate_names", meta.get("ss_venue_alternate_names"))

    # ---- OA venue extras ------------------------------------------------
    for f in ("venue_type", "host_organization", "fulltext_origin",
               "oa_created_date", "oa_updated_date"):
        _emit_scalar_if(lines, f, meta.get(f))
    _emit_list_quoted_if(lines, "host_organization_lineage", meta.get("host_organization_lineage"))
    _emit_bool_flag(lines, "has_fulltext", meta.get("has_fulltext"))
    _emit_bool_flag(lines, "is_paratext",  meta.get("is_paratext"))

    # ---- Per-field provenance -------------------------------------------
    from extract_metadata import PROVENANCE_FIELDS
    _emit_provenance(lines, meta.get("_provenance") or {}, PROVENANCE_FIELDS)

    # ---- Trailer --------------------------------------------------------
    _emit_scalar_if(lines, "pages", meta.get("pages"))
    lines.append("---\n")
    return "\n".join(lines)


_REFS_HEADER = "## References\n"


def render_summary(slug: str, pdf: Path,
                    existing_target: Path | None = None,
                    meta: dict | None = None) -> str:
    """Build the full MD body: frontmatter + references only.

    Pass `existing_target` so re-extraction preserves the original
    `added_at` (only `last_extracted` and the metadata payload should
    update on re-run).

    Pass `meta` to skip the extract_metadata() call — useful when the
    caller already did it (e.g. server.py's /api/extract computes the
    canonical slug from meta before calling us, so we don't want to
    re-run the API triple).

    v0.1 policy: API-only. Metadata + refs come exclusively from Crossref
    (and optionally OpenAlex/Semantic Scholar when the user set keys).
    No PDF text scanning. When Crossref doesn't have the paper's refs
    (publisher didn't deposit them), the summary is written with an
    empty References section + `refs_source: none`.
    """
    if meta is None:
        meta = extract_metadata(pdf)
    doi = (meta.get("doi") or "").strip()
    refs = []
    if doi and doi != "unknown":
        refs = extract_references_from_crossref(doi)

    # Cross-check against Semantic Scholar's reference list (DOIs only,
    # stored under _ss_reference_dois by _from_semanticscholar). Adds a
    # source-of-record annotation to refs_source AND surfaces overlap
    # counts so the UI can show 'X confirmed by SS · Y SS-only'.
    ss_dois: list[str] = meta.get("_ss_reference_dois") or []
    ss_raw: list[dict] = meta.get("_ss_references_raw") or []
    cr_dois: set[str] = {(r.doi or "").strip().lower() for r in refs
                          if (r.doi or "").strip()}
    ss_set: set[str] = {d for d in ss_dois if d}
    confirmed = cr_dois & ss_set
    ss_only = ss_set - cr_dois
    # Build the ss-only ref list (with titles/years when SS gave them)
    # so the UI can render them at the bottom of References as real
    # entries instead of bare DOIs.
    ss_only_refs = [r for r in ss_raw if (r.get("doi") or "") in ss_only]

    src_parts: list[str] = []
    if refs:
        src_parts.append("crossref")
    if ss_set:
        src_parts.append("semanticscholar")
    meta["refs_source"] = "+".join(src_parts) if src_parts else "none"
    if refs and not ss_set:
        # Crossref returned refs but SS didn't — keep the informative
        # 'crossref-empty' suffix so it's clear SS was checked and
        # returned nothing.
        pass
    if cr_dois or ss_set:
        meta["refs_confirmed_by_ss"] = len(confirmed)
        meta["refs_ss_only"]         = len(ss_only)
        meta["refs_crossref_count"]  = len(refs)
        meta["refs_ss_count"]        = len(ss_set)
    # Expose the per-ref data the UI needs to badge each entry:
    #   ss_confirmed_dois — DOIs Crossref returned AND SS also returned
    #                       (each Crossref ref with a DOI in this set
    #                       gets a 'both' badge; the rest get 'crossref only')
    #   ss_only_refs      — full ref objects (doi + title + year) that
    #                       SS had but Crossref didn't, so we can render
    #                       them at the bottom of References with real
    #                       titles rather than bare DOIs
    if confirmed:
        meta["ss_confirmed_dois"] = sorted(confirmed)
    if ss_only_refs:
        meta["ss_only_refs"] = ss_only_refs
    added_at = _preserved_added_at(existing_target)
    fm = render_frontmatter(slug, meta, added_at=added_at)
    refs_md = "\n".join(r.to_md_line() for r in refs)
    return fm + _REFS_HEADER + refs_md + "\n"


