"""Citation data (python/cite_api.py): a summary as CSL-JSON, and titles
in sentence case for the styles that want it.

The formatting is checked against the style guides in
tests/src/cite.test.js; this file checks what Corpus feeds it. Every test
names the mistake it catches.
"""
from __future__ import annotations

import json

import cite_api as C


def test_sentence_case_keeps_proper_nouns_acronyms_and_the_subtitle_start():
    """Catches the sentence-caser lower-casing "Bayesian", "Parkinson's",
    "fMRI", "COVID-19" or the first word after a colon — or touching a
    title that is already in sentence case."""
    abstract = "We fitted Bayesian models to patients with Parkinson's disease in the United States."
    assert C.sentence_case("Bayesian Models of Category Learning in Parkinson's Disease", abstract) \
        == "Bayesian models of category learning in Parkinson's disease"
    assert C.sentence_case("Prospect Theory: An Analysis of Decision under Risk") \
        == "Prospect theory: An analysis of decision under risk"
    assert C.sentence_case("The Hippocampus Supports fMRI-Measured Learning in the United States", abstract) \
        == "The hippocampus supports fMRI-measured learning in the United States"
    assert C.sentence_case("COVID-19 and Learning: Evidence From 3D Tasks") \
        == "COVID-19 and learning: Evidence from 3D tasks"
    already = "Learning reinforces curiosity for related information"
    assert C.sentence_case(already) == already


def test_only_mid_sentence_capitals_count_as_proper_nouns():
    """Catches every sentence-opening word ("Here", "We") being taken for
    a proper noun, which would keep "Here" capitalised in titles."""
    words = C.proper_words("Here we test it. We found that Stroop interference fell.")
    assert "stroop" in words and "here" not in words and "we" not in words


def _fm(**kw):
    base = {"kind": "article", "title": "A Study of Things", "year": "2019",
            "publisher": "Journal of Things", "volume": "8", "issue": "3",
            "pages": "207–217", "doi": "https://doi.org/10.1037/ppm0000185",
            "authors_detailed": [{"family": "Grady", "given": "Jessica Stoltzfus"},
                                 {"family": "Her", "given": "Malina"}]}
    base.update(kw)
    return base


def test_a_journal_article_maps_every_field_csl_needs():
    """Catches a field the styles print (container, volume, issue, pages,
    DOI) not reaching the item, the DOI keeping its URL prefix, or an en
    dash in pages surviving (CSL expects a hyphen)."""
    it = C.csl_item("grady-2019", _fm())
    assert it["type"] == "article-journal" and it["container-title"] == "Journal of Things"
    assert (it["volume"], it["issue"], it["page"]) == ("8", "3", "207-217")
    assert it["DOI"] == "10.1037/ppm0000185"
    assert it["issued"] == {"date-parts": [[2019]]}
    assert it["author"][0] == {"family": "Grady", "given": "Jessica Stoltzfus"}
    assert it["title-sentence"] == "A study of things"


def test_unknown_fields_are_left_out_not_printed():
    """Catches "unknown" printed in a reference ("Unknown, 8(unknown)")."""
    it = C.csl_item("x", _fm(volume="unknown", issue="", doi="unknown", year="unknown"))
    assert "volume" not in it and "issue" not in it and "DOI" not in it and "issued" not in it


def test_an_article_number_is_a_number_not_a_page_range():
    """Catches "e2529176123" sent as a page (APA then omits "Article")."""
    it = C.csl_item("x", _fm(pages="e2529176123", article_number="e2529176123"))
    assert it.get("number") == "e2529176123" and "page" not in it


def test_authors_fall_back_to_the_short_list_with_initials():
    """Catches papers without structured authors losing every author, or
    "Baldassano C.A." becoming a family name "Baldassano C.A."."""
    it = C.csl_item("x", _fm(authors_detailed="unknown",
                             authors_full=["Abir Y.", "Baldassano C.A."]))
    assert it["author"] == [{"family": "Abir", "given": "Y."}, {"family": "Baldassano", "given": "C.A."}]


def test_a_chapter_gets_a_sentence_case_book_title():
    """Catches a chapter's book title left in Title Case for APA, or a
    journal name being lower-cased (journals keep their capitals)."""
    ch = C.csl_item("x", _fm(kind="chapter", publisher="Formal Approaches in Categorization"))
    assert ch["type"] == "chapter" and ch["container-title-sentence"] == "Formal approaches in categorization"
    assert "container-title-sentence" not in C.csl_item("y", _fm())


def test_the_project_endpoint_returns_its_papers_only(client, corpus_dir):
    """Catches notes or documents in a project being exported as
    references, or a project's papers going missing."""
    (corpus_dir / "summaries" / "grady-2019.md").write_text(
        "---\nauthor: Grady, J.\nyear: 2019\ntitle: A Study of Things\nkind: article\n"
        "publisher: Journal of Things\ndoi: 10.1037/ppm0000185\n---\n\nBody.\n")
    pid = client.post("/api/projects", json={"title": "Prelims"}).get_json()["id"]
    client.post(f"/api/project/{pid}/members", json={"kind": "paper", "id": "grady-2019", "add": True})
    body = client.get(f"/api/project/{pid}/csl").get_json()
    assert body["title"] == "Prelims"
    assert [i["id"] for i in body["items"]] == ["grady-2019"]
    assert client.get("/api/paper/grady-2019/csl").get_json()["item"]["DOI"] == "10.1037/ppm0000185"
    assert client.get("/api/paper/nope/csl").status_code == 404
    json.dumps(body)


def test_the_cite_section_and_project_export_are_wired_in():
    """Catches the engine loading after the code that uses it, the paper
    page never mounting its Cite section, or the project export button
    being dropped."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src"
    html = (src / "index.html").read_text(encoding="utf-8")
    order = [html.index(f'src="{f}"') for f in
             ("vendor/citeproc/citeproc.js", "cite.js", "cite-ui.js", "paper-detail.js", "projects.js")]
    assert order == sorted(order)
    pd = (src / "paper-detail.js").read_text(encoding="utf-8")
    assert "${CiteUI.sectionHtml()}" in pd and 'CiteUI.mountPaper(q("#pd-cite"), d.slug);' in pd
    pj = (src / "projects.js").read_text(encoding="utf-8")
    assert 'id="pj-export-refs"' in pj and "CiteUI.openProjectExport(p)" in pj
