"""Elsevier PII → DOI at import (extract_metadata, 2026-10-29).

Older Elsevier PDFs print no DOI but carry their PII ("PII:
S0010-0285(02)00505-4") in /Info or on page 1; johansen-2002 imported
with no metadata at all. Every test names the mistake it catches.
"""
from __future__ import annotations

import extract_metadata as E


def test_a_bracketed_pii_becomes_its_doi():
    """Catches the PII being missed in /Info-style text, or the DOI built
    with the wrong prefix or case."""
    assert E.dois_from_pii_text("PII: S0010-0285(02)00505-4") == ["10.1016/S0010-0285(02)00505-4"]
    assert E.dois_from_pii_text("pii s0010-0285(02)00505-4 … PII: S0010-0285(02)00505-4") \
        == ["10.1016/S0010-0285(02)00505-4"]


def test_other_numbers_and_compact_piis_are_not_turned_into_dois():
    """Catches an ISSN or page range read as a PII, or the compact
    17-character PII (whose DOI is journal-coded, not derivable) turned
    into a wrong 10.1016/ DOI."""
    assert E.dois_from_pii_text("ISSN 0010-0285, pp. 297-343, S0010028502005054") == []


def test_import_uses_the_pii_when_no_doi_is_printed(tmp_path, monkeypatch):
    """Catches the PII step not running (or running before the printed-DOI
    steps), and a PII DOI skipping the registry gate."""
    pdf = tmp_path / "x.pdf"
    import fitz
    d = fitz.open(); d.new_page().insert_text((72, 72), "Are there representational shifts during learning?")
    d.set_metadata({"title": "PII: S0010-0285(02)00505-4"}); d.save(str(pdf))
    seen = []
    monkeypatch.setattr(E, "_rank_dois", lambda text: [])
    monkeypatch.setattr(E, "_is_registered_paper", lambda doi: seen.append(doi) or True)
    monkeypatch.setattr(E, "_collect_api_metadata",
                        lambda doi: ({"DOI": doi, "title": ["Are there representational shifts during category learning?"]}, {}, {}))
    monkeypatch.setattr(E, "_resolve_by_title", lambda *a: ({}, {}, {}))
    E.extract_metadata(pdf)
    assert seen == ["10.1016/S0010-0285(02)00505-4"]


def test_the_registry_gate_refuses_front_matter_figures_and_unknown_dois(monkeypatch):
    """Catches the shared gate letting through journal front matter (how
    snow-1996 became noauthorshipindicated-2002), a figure DOI, or a DOI
    Crossref does not know — for every DOI source that uses it."""
    records = {"10.1/paper": {"type": "journal-article", "title": ["Rules and exemplars"]},
               "10.1/editors": {"type": "journal-article", "title": ["Psychology, Public Policy, and Law: Editors."]},
               "10.1/fig": {"type": "component", "title": ["Figure 1"]}}
    monkeypatch.setattr(E, "crossref_lookup", lambda doi: records.get(doi))
    assert E._is_registered_paper("10.1/paper")
    assert not E._is_registered_paper("10.1/editors")
    assert not E._is_registered_paper("10.1/missing")
    assert not E._is_registered_paper("10.1/fig")
