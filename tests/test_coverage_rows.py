"""The paper Coverage table must describe what Corpus actually collects.

Bug (2026-09-22): the table still suggested that citer information is
not collected by choice, and it must stay current as collection changes.

The table (`coverageRows` in src/paper-detail.js) is hand-written, and
the fields it describes are written by `render_frontmatter` in
python/extract/prefill_summary.py. Nothing tied the two together, so a
field could start being collected while its row still said ⊘ "Corpus
deliberately doesn't extract" — exactly what happened to the citer list
(stored since 2026-09-22) and to OpenAlex `versions`.

Three rules, each a way the table drifts:

  1. A row that checks a frontmatter key must name a key Corpus writes.
     Catches a row pointing at a renamed or removed field — it would
     show ✗ on every paper forever.
  2. A ⊘ row names the key it WOULD use ("SKIP:<key>"), and that key must
     NOT be written. Catches the reported bug: collected but still
     claiming to be skipped.
  3. Every key Corpus writes is either on a row or explicitly listed in
     NOT_A_COVERAGE_FIELD with its reason. Catches the next new field
     arriving with no row at all — the table silently incomplete.

Plus: a row backed by a sidecar store ("STORE:<name>") must name a store
the paper API reports.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PREFILL = _ROOT / "python" / "extract" / "prefill_summary.py"
_PAPER_DETAIL = _ROOT / "src" / "paper-detail.js"

# Written to frontmatter, deliberately not a Coverage row. Each needs a
# reason: this list is the decision record, not a dumping ground.
NOT_A_COVERAGE_FIELD = {
    # Bookkeeping Corpus writes about its own extraction, not source data.
    "author": "display form of authors_full (row: Authors (structured))",
    "source_url": "derived from the DOI",
    "pdf_link": "local file path",
    "pdf_available": "local file flag",
    "status": "extraction state",
    "added_at": "local timestamp",
    "last_extracted": "local timestamp",
    "citation_count_as_of": "timestamp for citation_count",
    "schema_version": "file format version",
    "metadata_source": "which resolver won",
    "refs_source": "which source the reference list came from",
    "needs_doi": "extraction flag",
    "retracted": "boolean mirror of the Retraction flag row",
    # Detail of a field that has its own row.
    "influential_citation_count_ss": "shown with Citation count",
    "refs_confirmed_by_ss": "reference cross-check detail",
    "refs_ss_only": "reference cross-check detail",
    "ss_confirmed_dois": "reference cross-check detail",
    "ss_only_refs": "reference cross-check detail",
    "open_access_pdf_status": "detail of Open Access PDF link",
    "open_access_pdf_license": "detail of Open Access PDF link",
    "tldr_model": "detail of TLDR",
    "embedding": "vector behind the Embedding row (checked via embedding_model)",
    "is_oa": "boolean mirror of OA status",
    "host_organization_lineage": "detail of Publisher organization",
    "fulltext_origin": "detail of Full-text availability",
    "component_number": "rare Crossref bibliographic extension",
    "event_name": "conference metadata, shown in the meta grid",
    "event_acronym": "conference metadata, shown in the meta grid",
    "event_location": "conference metadata, shown in the meta grid",
    # Identifiers, not information streams.
    "ss_paper_id": "Semantic Scholar identifier",
    "oa_paper_id": "OpenAlex identifier",
}
# Families written from a loop: `<field>_from` provenance lines and the
# flattened SS external ids (`ss_arxiv_id`, `ss_pubmed_id`, …).
NOT_A_COVERAGE_PATTERNS = (re.compile(r"^.+_from$"), re.compile(r"^ss_[a-z0-9]+_id$"))


def emitted_keys() -> set[str]:
    """Every top-level frontmatter key prefill_summary can write.

    Read from source, three shapes: `lines.append("key: …")` and
    f-string lines starting `key: `; `_emit_*(lines, "key", …)`; and
    `for f in ("a", "b"): _emit_*(lines, f, …)` loops.
    """
    src = _PREFILL.read_text(encoding="utf-8")
    keys: set[str] = set()
    keys |= set(re.findall(r'lines\.append\(f?"([a-z_][a-z0-9_]*):', src))
    keys |= set(re.findall(r'\bf"([a-z_][a-z0-9_]*): ', src))
    keys |= set(re.findall(r'^\s*f?"([a-z_][a-z0-9_]*): ', src, re.M))
    keys |= set(re.findall(r'"([a-z_][a-z0-9_]*): (?:true|false)"', src))
    keys |= set(re.findall(r'_emit_\w+\(lines, "([a-z_][a-z0-9_]*)"', src))
    for tup in re.findall(r'for f in \(([^)]*)\):\s*\n\s*_emit_\w+\(lines, f', src):
        keys |= set(re.findall(r'"([a-z_][a-z0-9_]*)"', tup))
    # Complex-shape emitters write their key from inside a helper.
    helpers = {"_emit_authors_detailed": "authors_detailed", "_emit_funder": "funder",
               "_emit_license": "license", "_emit_update_to": "update_to",
               "_emit_ss_only_refs": "ss_only_refs", "_emit_s2_fields_of_study": "s2_fields_of_study",
               "_emit_ss_authors_raw": "_ss_authors_raw", "_emit_embedding": "embedding"}
    for fn, key in helpers.items():
        if re.search(rf"\b{fn}\(lines,", src):
            keys.add(key)
    keys.discard("f")
    return keys


def coverage_rows() -> list[tuple[str, list]]:
    """(label, [crossref, ss, openalex]) for each paper Coverage row."""
    js = _PAPER_DETAIL.read_text(encoding="utf-8")
    block = js[js.index("const coverageRows = ["):]
    block = block[:block.index("\n  ];")]
    rows = []
    for m in re.finditer(r'\[\s*"([^"]+)",\s*(null|"[^"]*"),\s*(null|"[^"]*"),\s*(null|"[^"]*"),\s*"[^"]*"\s*\]', block):
        cells = [None if c == "null" else c.strip('"') for c in m.groups()[1:]]
        rows.append((m.group(1), cells))
    return rows


def test_the_audit_reads_both_sides():
    """Guards the guard: if either parser silently returned nothing, every
    rule below would pass vacuously."""
    assert len(coverage_rows()) > 50
    keys = emitted_keys()
    for must in ("title", "versions", "abstract", "embedding", "update_to", "oa_authors"):
        assert must in keys, f"emitted-key parser missed {must!r}"


def test_every_checked_key_is_one_corpus_writes():
    """Rule 1: a row pointing at a field that is never written shows ✗
    on every paper forever."""
    written = emitted_keys()
    bad = [(label, c) for label, cells in coverage_rows() for c in cells
           if c and not c.startswith(("SKIP", "STORE:")) and c not in written]
    assert not bad, f"coverage rows check keys Corpus never writes: {bad}"


def test_nothing_marked_skipped_is_actually_collected():
    """Rule 2 — the reported bug. Every ⊘ names the key it would use, and
    that key must not be written."""
    written = emitted_keys()
    unnamed, stale = [], []
    for label, cells in coverage_rows():
        for c in cells:
            if c == "SKIP":
                unnamed.append(label)
            elif c and c.startswith("SKIP:") and c[5:] in written:
                stale.append((label, c[5:]))
    assert not unnamed, f"⊘ rows must name the key they would use (SKIP:<key>): {unnamed}"
    assert not stale, f"rows claim ⊘ skipped but the field IS collected: {stale}"


def test_every_written_field_is_on_a_row_or_explicitly_excluded():
    """Rule 3: a new field must not arrive with no row at all."""
    on_rows = {c for _l, cells in coverage_rows() for c in cells
               if c and not c.startswith(("SKIP", "STORE:"))}
    missing = sorted(k for k in emitted_keys()
                     if k not in on_rows and k not in NOT_A_COVERAGE_FIELD
                     and not any(p.match(k) for p in NOT_A_COVERAGE_PATTERNS))
    assert not missing, (
        f"fields Corpus writes with no Coverage row and no recorded reason: {missing}. "
        "Add a row in src/paper-detail.js or an entry in NOT_A_COVERAGE_FIELD.")


def test_exclusions_do_not_go_stale():
    """Catches NOT_A_COVERAGE_FIELD keeping entries for fields no longer
    written — a decision record full of dead entries stops being read."""
    dead = sorted(k for k in NOT_A_COVERAGE_FIELD if k not in emitted_keys())
    assert not dead, f"excluded fields that are no longer written: {dead}"


def test_store_backed_rows_name_a_store_the_paper_api_reports():
    """A "STORE:<name>" cell is resolved from `d.stores[<name>]`, which
    /api/paper/<slug> computes. A name the API does not report would read
    ✗ on every paper."""
    import papers_api
    reported = set(papers_api.PAPER_STORES)
    used = {c[6:] for _l, cells in coverage_rows() for c in cells if c and c.startswith("STORE:")}
    assert used, "the citer list is stored per paper — its row should read the store"
    assert used <= reported, f"rows read stores the API does not report: {used - reported}"
