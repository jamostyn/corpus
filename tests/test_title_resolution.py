"""Recovering papers whose DOI never resolved, by title.

Requirement (2026-09-24): get the Crossref, Semantic Scholar or OpenAlex
id from the title when the DOI is not found.

A read-only probe of the 11 corpus papers with `doi: unknown` answered it:
with correct titles OpenAlex found 10, Semantic Scholar 9, Crossref 8 —
but with the titles Corpus pulled from the PDFs, each found only 2. So
the fix is two halves, and both are pinned here:

  * the first-page title extractor must stop dropping words, and
  * OpenAlex / S2 title lookup must follow Crossref's, including for
    works that have no DOI at all.

No network: every client is stubbed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import crossref_client
import extract_metadata as em
import openalex_client
import semanticscholar_client


# ---------- the title extractor ----------

def _fake_page(monkeypatch, lines):
    """Serve `lines` — each a list of (text, size) spans — as page 1."""
    blocks = [{"lines": [{"bbox": [50, 100 + 30 * i, 500, 120 + 30 * i],
                          "spans": [{"text": t, "size": s, "bbox": [0, 100 + 30 * i, 0, 0]}
                                    for t, s in spans]}]}
              for i, spans in enumerate(lines)]

    class Page:
        def get_text(self, kind):
            return {"blocks": blocks}

    class Doc:
        def __getitem__(self, i):
            return Page()

        def close(self):
            pass

    monkeypatch.setattr(em.fitz, "open", lambda p: Doc())


def test_a_title_set_in_mixed_sizes_keeps_every_word(monkeypatch):
    """Catches grouping by span size: small words or small caps set a
    point smaller landed in their own bucket and vanished. Real case,
    2026-09-24: "A New Theory of Disuse and an Old Theory of Stimulus
    Fluctuation" was extracted as "Theory Disuse Theory and Stimulus
    Fluctuation" and no service could find it."""
    _fake_page(monkeypatch, [
        [("A New Theory ", 18.0), ("of ", 13.0), ("Disuse and an Old Theory ", 18.0),
         ("of ", 13.0), ("Stimulus Fluctuation", 18.0)],
        [("Body text that is clearly not the title of anything at all.", 10.0)],
    ])
    got = em._title_candidates_from_pdf_text(Path("x.pdf"))
    assert got[0] == "A New Theory of Disuse and an Old Theory of Stimulus Fluctuation"


def test_title_lines_in_near_equal_sizes_stay_together(monkeypatch):
    """Catches a two-line title splitting into two half-candidates when
    its lines differ slightly in size — the 17.1pt / 16.6pt pair measured
    on knowlton-1993, whose extracted title was "Learning Categories:"."""
    _fake_page(monkeypatch, [
        [("The Learning of Categories: Parallel Brain Systems", 17.1)],
        [("for Item Memory and Category Knowledge", 16.6)],
        [("Barbara J. Knowlton and Larry R. Squire", 12.5)],
    ])
    got = em._title_candidates_from_pdf_text(Path("x.pdf"))
    assert got[0] == ("The Learning of Categories: Parallel Brain Systems "
                      "for Item Memory and Category Knowledge")


def test_words_stored_without_spaces_are_separated_by_their_gaps():
    """Catches both ways of joining spans wrong. knowlton-1993 stores each
    word as its own span with no space characters, and a bare join gave
    "TheLearningofCategories:"; a blanket " " join would instead split a
    small-caps word ("T" + "HE") that sits flush."""
    spaced = [{"text": "The", "bbox": [0, 0, 30, 0]}, {"text": "Learning", "bbox": [35, 0, 90, 0]},
              {"text": "of", "bbox": [95, 0, 110, 0]}]
    assert em._join_spans(spaced, 17.0) == "The Learning of"
    flush = [{"text": "T", "bbox": [0, 0, 12, 0]}, {"text": "HE", "bbox": [12.3, 0, 30, 0]}]
    assert em._join_spans(flush, 17.0) == "THE"


def test_body_text_does_not_join_the_title(monkeypatch):
    """Catches the tier tolerance being so loose that the author line or
    body copy is appended to the title, which then matches nothing."""
    _fake_page(monkeypatch, [
        [("Working memory capacity and disfluency effect", 16.0)],
        [("Julia Lehmann and Tina Seufert and Maria Goussios", 11.0)],
    ])
    got = em._title_candidates_from_pdf_text(Path("x.pdf"))
    assert got[0] == "Working memory capacity and disfluency effect"


# ---------- the title lookups ----------

@pytest.fixture
def no_network(monkeypatch):
    """Every outbound call fails the test unless a test re-stubs it."""
    def boom(*a, **k):
        pytest.fail("unexpected network call")
    for mod, name in ((crossref_client, "api_get_json"), (openalex_client, "api_get_json"),
                      (semanticscholar_client, "api_get_json")):
        monkeypatch.setattr(mod, name, boom)
    monkeypatch.setattr(em, "crossref_search_by_title", lambda *a, **k: None)
    monkeypatch.setattr(em, "_collect_api_metadata",
                        lambda doi: pytest.fail(f"full lookup for {doi}"))


def test_a_one_word_fragment_is_never_searched(no_network):
    """Catches the Bjork 1994 -> DeLucia-Waack 2006 mismatch: a first-page
    fragment reading "Considerations" matched a chapter titled exactly
    that. No service should be asked about a one- or two-word seed."""
    assert em._resolve_by_title("Considerations") == ({}, {}, {})
    assert crossref_client.crossref_search_by_title("Considerations", "", None) is None


def test_openalex_is_searched_by_title_filter_not_free_text(monkeypatch):
    """Catches a switch to `search=`, which returns a confident top hit
    even for titles OpenAlex does not hold (observed 2026-08-26), and
    catches a comma or colon in the title breaking the filter syntax."""
    urls = []
    title = "Challenge Point: A Framework for Conceptualizing Practice, in Motor Learning"

    def get(url, timeout, extra_headers=None):
        urls.append(url)
        return {"results": [{"id": "https://openalex.org/W1", "title": title}]}
    monkeypatch.setattr(openalex_client, "api_get_json", get)
    assert openalex_client.openalex_search_by_title(title)["id"].endswith("W1")
    assert "filter=title.search:" in urls[0] and "search=" not in urls[0].replace("title.search", "")
    query = urls[0].split("title.search:")[1].split("&")[0]
    assert "%2C" not in query and "%3A" not in query and "," not in query


def test_a_near_miss_title_is_rejected(monkeypatch):
    """Catches accepting whatever the service ranks first. Both searches
    can return a near-miss; below the 0.90 floor it is a different paper."""
    query = "A New Theory of Disuse and an Old Theory of Stimulus Fluctuation"
    near_miss = "A New Theory of Disuse and an Old Theory of Forgetting"
    # Guards the guard: an example far below the floor would stay rejected
    # even if the floor were lowered to 0.5 — which is how the first
    # version of this test let exactly that mutation survive.
    assert 0.5 < openalex_client.title_similarity(query, near_miss) < 0.90
    monkeypatch.setattr(openalex_client, "api_get_json", lambda *a, **k: {
        "results": [{"id": "W9", "title": near_miss}]})
    assert openalex_client.openalex_search_by_title(query) is None


def test_a_doi_found_by_title_gets_the_full_three_source_lookup(no_network, monkeypatch):
    """Catches a title hit being recorded from the search result alone. A
    paper found by title must carry exactly what a paper found by DOI
    does, so the DOI hands off to the normal lookup."""
    monkeypatch.setattr(em, "openalex_search_by_title", lambda t, year=None: {
        "id": "https://openalex.org/W2038221682", "doi": "https://doi.org/10.1126/science.8259522"})
    asked = []
    monkeypatch.setattr(em, "_collect_api_metadata",
                        lambda doi: asked.append(doi) or ({"source": "crossref", "doi": doi}, {}, {}))
    cr, _oa, _ss = em._resolve_by_title("The Learning of Categories: Parallel Brain Systems")
    assert asked == ["10.1126/science.8259522"] and cr["doi"] == asked[0]


def test_a_work_with_no_doi_is_recorded_from_its_own_ids(no_network, monkeypatch):
    """Catches treating "no DOI" as "not found". bjork-1992 exists in
    OpenAlex (W2595422523, 450 citations) and S2, with no DOI anywhere;
    their records are the only way to identify it."""
    monkeypatch.setattr(em, "openalex_search_by_title", lambda t, year=None: {
        "id": "https://openalex.org/W2595422523", "doi": None,
        "ids": {"openalex": "https://openalex.org/W2595422523"},   # real payload shape
        "title": "A new theory of disuse and an old theory of stimulus fluctuation",
        "publication_year": 1992, "cited_by_count": 450})
    monkeypatch.setattr(em, "semanticscholar_match_title",
                        lambda t: {"paper_id": "82d8e57aaf", "doi": None})
    monkeypatch.setattr(em, "semanticscholar_lookup_id",
                        lambda pid: {"paperId": pid, "title": "A new theory of disuse", "year": 1992})
    cr, oa, ss = em._resolve_by_title("A New Theory of Disuse and an Old Theory of Stimulus Fluctuation")
    assert cr == {}
    assert oa.get("oa_paper_id", "").endswith("W2595422523")
    assert oa.get("year") == 1992
    assert ss.get("ss_paper_id") == "82d8e57aaf"


def test_journal_front_matter_is_not_accepted_as_the_paper():
    """Catches the snow-1996 corruption: a PDF with the journal's editors
    page bundled in resolved to "Psychology, Public Policy, and Law:
    Editors." and was renamed noauthorshipindicated-2002. Also catches the
    guard growing broad enough to reject real titles."""
    assert em._is_front_matter("Psychology, Public Policy, and Law: Editors.")
    assert em._is_front_matter("Editorial Board")
    assert em._is_front_matter("Issue Information")
    assert not em._is_front_matter("A Note on the Role of Editors in Peer Review Outcomes Today")
    assert not em._is_front_matter("Building a new memory index")
    assert not em._is_front_matter("Aptitude Development and Education")


def test_a_title_search_landing_on_front_matter_is_refused(no_network, monkeypatch):
    """Catches the second snow-1996 corruption: the masthead line went in
    as the title, Crossref's title search returned the journal's
    "…: Editors." page, and the guard on the DOI-scan step never saw it.
    Every exit from _resolve_by_title must be checked."""
    monkeypatch.setattr(em, "crossref_search_by_title", lambda *a, **k: "10.1037//1076-8971.8.4.c2")
    monkeypatch.setattr(em, "_collect_api_metadata", lambda doi: (
        {"source": "crossref", "doi": doi, "title": "Psychology, Public Policy, and Law: Editors."}, {}, {}))
    monkeypatch.setattr(em, "openalex_search_by_title", lambda t, year=None: None)
    monkeypatch.setattr(em, "semanticscholar_match_title", lambda t: None)
    assert em._resolve_by_title("Psychology, Public Policy, and Law") == ({}, {}, {})


def test_a_supplement_doi_resolves_to_its_paper():
    """Catches the Taatgen 2013 import: the PDF prints the APA supplement
    DOI (…/a0033138.supp) beside the paper's, the supplement won, and the
    paper imported as "Supplemental Material for The Nature and Transfer
    of Cognitive Skills" under the slug 2013-19654-001."""
    got = [d for d, _ in em._extract_doi_candidates(
        "Supplemental materials: http://dx.doi.org/10.1037/a0033138.supp  "
        "Psychological Review 2013 doi 10.1037/a0033138")]
    assert got == ["10.1037/a0033138"]


def test_a_supplement_record_is_not_accepted_as_the_paper():
    """Catches a supplement arriving by a route the DOI rewrite does not
    cover (another publisher's suffix, a title search). Named after its
    paper, so it matches the paper's title almost exactly."""
    assert em._is_front_matter("Supplemental Material for The Nature and Transfer of Cognitive Skills")
    assert em._is_front_matter("Supplementary Information")
    assert not em._is_front_matter("Supplementary motor area activity during sequence learning")


def test_page_one_is_searched_even_when_info_has_a_title(monkeypatch):
    """Catches page-1 candidates being tried only when /Info is empty.
    A plausible but wrong /Info title was then the ONLY seed, and
    Guadagnoli & Lee's Challenge Point stayed unresolved although page 1
    printed its exact title (2026-09-24)."""
    monkeypatch.setattr(em, "_from_pdf_metadata", lambda pdf: {"title": "Repository Download Copy"})
    monkeypatch.setattr(em, "extract_pdf_text", lambda pdf, max_pages=3: "")
    monkeypatch.setattr(em, "_title_candidates_from_pdf_text",
                        lambda pdf: ["Challenge Point: A Framework for Conceptualizing Practice"])
    seeds = []
    monkeypatch.setattr(em, "_resolve_by_title", lambda t: seeds.append(t) or ({}, {}, {}))
    em.extract_metadata(Path("x.pdf"))
    assert seeds == ["Repository Download Copy",
                     "Challenge Point: A Framework for Conceptualizing Practice"]


def test_s2_retries_a_throttled_title_match(monkeypatch):
    """Catches treating keyless S2's burst 429 (reported as None) as "no
    such paper" — 1 of the 11 probe lookups was lost this way."""
    monkeypatch.setattr(semanticscholar_client, "time", type("T", (), {
        "sleep": staticmethod(lambda s: None), "monotonic": staticmethod(lambda: 0.0)}))
    monkeypatch.setattr(semanticscholar_client, "_ss_rate_limit", lambda: None)
    answers = [None, {"data": [{"paperId": "P1", "title": "Desirable Difficulties in Theory and Practice",
                                "externalIds": {"DOI": "10.1016/J.JARMAC.2020.09.003"}}]}]
    monkeypatch.setattr(semanticscholar_client, "api_get_json", lambda *a, **k: answers.pop(0))
    got = semanticscholar_client.semanticscholar_match_title("Desirable Difficulties in Theory and Practice")
    assert got == {"paper_id": "P1", "doi": "10.1016/j.jarmac.2020.09.003"}
