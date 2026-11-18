"""Which printed DOI is the paper's own (extract_metadata, 2026-11-11).

Weichart et al. (2022) prints the DOI of the Meier & Blair (2013)
dataset it reuses above its own DOI on page 1; both scored alike and
the import filed the PDF as meier-2013. Every test names the mistake
it catches.
"""
from __future__ import annotations

import fitz

import extract_metadata as E

OWN, CITED = "10.1037/rev0000381", "10.1016/j.cognition.2012.09.014"
RECORDS = {
    OWN: {"doi": OWN, "title": "As within, so without, as above, so below: Common mechanisms "
                                "can support between- and within-trial category learning dynamics"},
    CITED: {"doi": CITED, "title": "Waiting and weighting: Information sampling is a balance "
                                   "between efficiency and error-reduction"},
}


def _pdf(tmp_path, lines):
    pdf = tmp_path / "x.pdf"
    d = fitz.open(); page = d.new_page()
    for i, line in enumerate(lines):
        page.insert_text((40, 60 + 14 * i), line, fontsize=8)
    d.save(str(pdf))
    return pdf


def _offline(monkeypatch, ranked):
    monkeypatch.setattr(E, "_rank_dois", lambda text: [(d, 60) for d in ranked])
    monkeypatch.setattr(E, "_is_registered_paper", lambda doi: True)
    monkeypatch.setattr(E, "_collect_api_metadata", lambda doi: (dict(RECORDS[doi]), {}, {}))
    monkeypatch.setattr(E, "_resolve_by_title", lambda *a: ({}, {}, {}))


def test_a_cited_dataset_doi_above_the_papers_own_does_not_win(tmp_path, monkeypatch):
    """Catches the import taking the first registered DOI on the page when
    it belongs to a paper the PDF only cites (how Weichart 2022 became
    meier-2013)."""
    pdf = _pdf(tmp_path, ["As Within, so Without, as Above, so Below: Common Mechanisms Can",
                          "Support Between- and Within-Trial Category Learning Dynamics",
                          "Data made available by Meier and Blair (2013) at https://doi.org/" + CITED,
                          "https://doi.org/" + OWN])
    _offline(monkeypatch, [CITED, OWN])
    assert E.extract_metadata(pdf)["doi"] == OWN


def test_with_no_title_on_the_page_the_first_registered_doi_still_wins(tmp_path, monkeypatch):
    """Catches the title check rejecting every DOI when the PDF's title
    text is garbled or missing, leaving a printed DOI unused."""
    pdf = _pdf(tmp_path, ["(garbled title layer)", "https://doi.org/" + CITED, "https://doi.org/" + OWN])
    _offline(monkeypatch, [CITED, OWN])
    assert E.extract_metadata(pdf)["doi"] == CITED


def test_the_title_check_ignores_line_breaks_hyphens_and_ligatures():
    """Catches the comparison failing on how PDF text actually comes out:
    a title split over lines, a hyphenated word, an "fi" ligature."""
    page = "Learning to classiﬁcation\nfrom feed-\nback: a model of choice"
    assert E.title_on_page(({"title": "Learning to classification from feedback: a model"},), page)
    assert E.title_on_page(({"title": "Waiting and weighting: Information sampling"},), page) is False
    assert E.title_on_page(({"title": "Short"},), page) is None
