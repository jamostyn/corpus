"""Guards on finding a paper by its title or arXiv id (extract_metadata).

Requirement (2026-10-29): papers whose PDF prints no DOI are found by
title search, and the record found must be the paper itself. A 25-paper
import found 2 wrong papers: a seed made only of section headings
("ABSTRACT 1 Introduction") matched a junk record, and an arXiv paper's
title search returned a published review of it by other authors. Every
test names the mistake it catches. No network: every client is stubbed.
"""
from __future__ import annotations

import fitz
import pytest

import extract_metadata as E
from _api_http import title_worth_searching


def test_a_seed_made_of_section_headings_is_never_searched():
    """Catches "ABSTRACT 1 Introduction" (three words, so past the length
    rule) being sent to the title search, where it matched a junk record."""
    assert not title_worth_searching("ABSTRACT 1 Introduction")
    assert not title_worth_searching("Research Article Abstract Keywords")
    assert title_worth_searching("An Introduction to Category Learning Models")


def test_a_title_label_is_not_part_of_the_title():
    """Catches a manuscript's "Title: …" label kept in the seed, which no
    service's title matches."""
    assert E._clean_candidate("Title: Modelling continual learning") == "Modelling continual learning"
    assert E._clean_candidate("Full title:  Learning to classify") == "Learning to classify"
    assert E._clean_candidate("Titles of nobility in history") == "Titles of nobility in history"


def _rec(*families):
    return {"authors_detailed": [{"family": f} for f in families]}


def test_authors_are_found_through_markers_accents_and_hidden_hyphens():
    """Catches the author check rejecting the right paper: an affiliation
    marker glued to the name ("Flesch1,"), an accent missing on one side,
    or a soft hyphen inside "Holt-Lunstad" (all three seen on real PDFs)."""
    assert E.authors_on_page((_rec("Flesch"),), "Timo Flesch1, David Nagy2") is True
    assert E.authors_on_page(({}, _rec("Gómez")), "R. Gomez and P. Li") is True
    assert E.authors_on_page((_rec("Holt-Lunstad"),), "Julianne Holt-­Lunstad") is True
    assert E.authors_on_page((_rec("Holt-Lunstad"),), "Julianne Holt‐Lunstad") is True


def test_other_authors_fail_and_no_authors_is_unknown():
    """Catches a name matched inside a longer word ("Li" in "Lin") letting
    another paper through, or a record without authors counted as a
    mismatch (it is unknown, so it may pass)."""
    assert E.authors_on_page((_rec("Carlson"),), "Cameron R. Jones, Benjamin K. Bergen") is False
    assert E.authors_on_page((_rec("Li"),), "Wei Lin and Ana Lima") is False
    assert E.authors_on_page(({}, {"authors_detailed": []}), "anything") is None


def test_a_title_search_hit_by_other_authors_is_refused(monkeypatch):
    """Catches the author check missing from _resolve_by_title: the
    Turing-test paper's title search returned a review of it by Carlson."""
    monkeypatch.setattr(E, "crossref_search_by_title", lambda *a, **k: "10.1/review")
    monkeypatch.setattr(E, "_collect_api_metadata", lambda doi: (
        {"doi": doi, "title": "Large Language Models Pass the Turing Test", **_rec("Carlson")}, {}, {}))
    monkeypatch.setattr(E, "openalex_search_by_title", lambda t, year=None: None)
    monkeypatch.setattr(E, "semanticscholar_match_title", lambda t: None)
    title = "Large Language Models Pass the Turing Test"
    assert E._resolve_by_title(title, "Cameron R. Jones, Benjamin K. Bergen") == ({}, {}, {})
    assert E._resolve_by_title(title, "Cameron R. Jones and S. Carlson")[0]["doi"] == "10.1/review"


def test_arxiv_ids_become_arxiv_dois():
    """Catches the version suffix kept in the DOI, a repeated stamp giving
    two lookups, or an old-style id ("hep-th/9901001") turned into a
    malformed DOI."""
    text = "arXiv:2503.23674v1 [cs.CL] 31 Mar 2025 … arXiv: 2503.23674 … arXiv:hep-th/9901001"
    assert E.dois_from_arxiv_text(text) == ["10.48550/arxiv.2503.23674"]


def _pdf(tmp_path, lines, name="x.pdf"):
    p = tmp_path / name
    d = fitz.open()
    page = d.new_page()
    for i, (text, size) in enumerate(lines):
        page.insert_text((60, 80 + 28 * i), text, fontsize=size)
    d.save(str(p))
    return p


def _no_doi_steps(monkeypatch):
    monkeypatch.setattr(E, "_rank_dois", lambda text: [])
    monkeypatch.setattr(E, "_dois_from_pii", lambda pdf: [])


def test_import_uses_the_arxiv_stamp_and_checks_its_authors(tmp_path, monkeypatch):
    """Catches the arXiv step not running, its DOI going through the
    Crossref gate (Crossref does not know arXiv DOIs, so it would always
    fail), or a record by other authors being accepted."""
    pdf = _pdf(tmp_path, [("arXiv:2503.23674v1 [cs.CL] 31 Mar 2025", 9),
                          ("Large Language Models Pass the Turing Test", 18),
                          ("Cameron R. Jones and Benjamin K. Bergen", 11)])
    _no_doi_steps(monkeypatch)
    monkeypatch.setattr(E, "_is_registered_paper", lambda doi: False)
    monkeypatch.setattr(E, "_resolve_by_title", lambda *a: ({}, {}, {}))
    authors = ["Jones"]
    monkeypatch.setattr(E, "_collect_api_metadata", lambda doi: (
        {}, {"doi": doi, "title": "Large Language Models Pass the Turing Test", **_rec(*authors)}, {}))
    assert E.extract_metadata(pdf).get("doi") == "10.48550/arxiv.2503.23674"
    authors[0] = "Carlson"
    assert E.extract_metadata(pdf).get("doi") in (None, "", "unknown")


def test_a_title_wrapped_on_a_dangling_word_takes_the_next_line():
    """Catches the font-size title stopping at "… gating and", which no
    service finds, or the join taking a line far below the title."""
    tier = [(100.0, 60.0, "Modelling continual learning with Hebbian gating and")]
    lines = [(18.0, 100.0, 60.0, tier[0][2]), (18.0, 124.0, 60.0, "decaying task signals"),
             (11.0, 300.0, 60.0, "Timo Flesch")]
    assert [t for _y, _x, t in E._complete_dangling_title(tier, lines)] == \
        [tier[0][2], "decaying task signals"]
    far = [(18.0, 100.0, 60.0, tier[0][2]), (11.0, 300.0, 60.0, "Timo Flesch")]
    assert E._complete_dangling_title(tier, far) == tier
    whole = [(100.0, 60.0, "Modelling continual learning")]
    assert E._complete_dangling_title(whole, [(18.0, *whole[0]), lines[1]]) == whole


def test_a_uniform_font_title_wrapped_on_a_dangling_word_is_joined(tmp_path):
    """Catches the line-scan fallback (one font size on the page) keeping
    only the first half of a wrapped title."""
    pdf = _pdf(tmp_path, [("Modelling continual learning in humans with Hebbian context gating and", 11),
                          ("exponentially decaying task signals", 11),
                          ("Timo Flesch, David Nagy, Andrew Saxe", 11)])
    got = E._line_scan_candidates(pdf)
    assert got and got[0] == ("Modelling continual learning in humans with Hebbian context gating and "
                              "exponentially decaying task signals")


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    import crossref_client, openalex_client, semanticscholar_client
    def boom(*a, **k):
        pytest.fail("unexpected network call")
    for mod in (crossref_client, openalex_client, semanticscholar_client):
        monkeypatch.setattr(mod, "api_get_json", boom)


def test_a_title_whose_last_line_is_set_smaller_keeps_it(tmp_path):
    """Catches the font-size title extractor dropping a wrapped title's
    second line because it is a size smaller (its own tier) — the seed
    then ends on "and" and no service finds it."""
    pdf = _pdf(tmp_path, [("Continual learning with Hebbian gating and", 18),
                          ("exponentially decaying task signals", 14),
                          ("Timo Flesch, David Nagy, Andrew Saxe", 10)])
    got = E._title_candidates_from_pdf_text(pdf)
    assert got and got[0] == "Continual learning with Hebbian gating and exponentially decaying task signals"
