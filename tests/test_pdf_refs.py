"""PDF reference extraction and the additive merge.

Two things are pinned here, and they are different:

  * the PARSER — that real-world reference formats survive extraction,
    and that an unreadable PDF is reported rather than silently
    returning an empty list;
  * the MERGE RULE — that PDF data can only fill blanks and append,
    never displace a value an API deposited.

The merge rule matters more. Crossref and Semantic Scholar values are
what DOIs, links, and provenance badges are keyed on; letting a
page-parsed string overwrite one would corrupt the record with
something that merely looks plausible.

Fixture snippets below are shortened but structurally faithful to the
real PDFs named in each docstring.
"""
import pytest

from extract_references_pdf import (
    MIN_READABLE_CHARS,
    extract_from_text,
    find_references_section,
    split_entries,
)
from pdf_refs_merge import build_pdf_lookup, enrich, pdf_only


# Real papers run to tens of thousands of characters. These fixtures
# carry a body section so they clear MIN_READABLE_CHARS — otherwise
# they trip the scanned-PDF guard, which is correct behaviour but not
# what these tests are about.
_BODY = (
    "In the present study we examined how learners allocate attention "
    "across stimulus dimensions during category learning, and whether "
    "that allocation shifts with feedback. Participants completed a "
    "series of classification blocks with corrective feedback after "
    "every trial. We fit competing models to the trial-by-trial data "
    "and compared them by out-of-sample predictive accuracy. Results "
    "are discussed in relation to selective-attention accounts.\n"
) * 3

APA = _BODY + """
Some closing paragraph of the discussion section.

References
Aha, D. W., & Goldstone, R. L. (1992). Concept learning
and flexible weighting. In Proceedings of the Fourteenth
Annual Conference of the Cognitive Science Society (pp. 534-539).
Berger-Tal, O., Nathan, J., Meron, E., & Saltz, D. (2014). The
exploration-exploitation dilemma: A multidisciplinary
framework. PLOS ONE, 9, Article e95693. https://doi.org/
10.1371/journal.pone.0095693
Blanco, N., Turner, B. M., & Sloutsky, V. M. (2022). The ben-
efits of immature cognitive control. Journal of Experimental
Child Psychology, 226, 105548.
"""

VANCOUVER = _BODY + """
References
1. Montague PR, Dayan P, Sejnowski TJ. A framework for mesencephalic
dopamine systems based on predictive Hebbian learning. J Neurosci.
1996 Mar 1; 16(5):1936-47. [PubMed: 8774460]
2. Frank MJ, O'Reilly RC. A mechanistic account of striatal dopamine
function in human cognition. Behav Neurosci. 2006 Jun; 120(3):497-517.
"""


# ---------- parser ----------

def test_apa_entries_are_split_and_parsed():
    """Catches: the APA branch of the entry detector breaking.

    Three references wrap across lines; a detector that treated every
    capitalised line as a new entry would return far more than three."""
    refs, status = extract_from_text(APA)
    assert status == "ok"
    assert len(refs) == 3
    assert [r["author"] for r in refs] == ["Aha", "Berger-Tal", "Blanco"]
    assert [r["year"] for r in refs] == [1992, 2014, 2022]


def test_vancouver_numbered_entries_are_split():
    """Catches: only handling APA. Numbered Vancouver style ("1. Smith
    AB, Jones CD.") has no comma before the initials, and half the
    corpus's journals use it. Before this was handled, 22 of 47 test
    papers extracted zero references."""
    refs, status = extract_from_text(VANCOUVER)
    assert status == "ok"
    assert len(refs) == 2
    assert [r["author"] for r in refs] == ["Montague", "Frank"]


def test_doi_split_across_a_line_break_is_recovered():
    """Catches: dropping DOIs that the PDF wrapped mid-string.
    Publishers routinely break "https://doi.org/10.1371/..." across two
    lines; a naive regex returns nothing for those."""
    refs, _ = extract_from_text(APA)
    assert refs[1]["doi"] == "10.1371/journal.pone.0095693"


def test_hyphenated_line_breaks_are_rejoined():
    """Catches: leaving "ben- efits" in a title. PDFs hyphenate at line
    ends; without rejoining, titles are unreadable and title matching
    fails."""
    refs, _ = extract_from_text(APA)
    assert "benefits" in refs[2]["title"]
    assert "ben- efits" not in refs[2]["title"]


def test_bullets_before_the_references_header_are_ignored():
    """Catches: scanning the whole document. Discussion sections
    contain author-shaped sentences; picking those up would inject
    fabricated references."""
    refs, _ = extract_from_text(APA)
    assert all("closing paragraph" not in r["raw"] for r in refs)


def test_unreadable_pdf_is_reported_not_silently_empty():
    """Catches: a scanned PDF looking identical to a paper that cites
    nothing.

    catrambone-1995 in the reference corpus yields 12 characters of
    text — it is an image scan. Returning [] with no signal would tell
    the user their paper has no references, which is a fabrication."""
    refs, status = extract_from_text("x" * (MIN_READABLE_CHARS - 1))
    assert status == "unreadable"
    assert refs == []


def test_readable_pdf_with_no_reference_list_says_so():
    """Catches: conflating "no reference section found" with
    "unreadable". They call for different user action — one is a
    parser gap, the other needs OCR."""
    refs, status = extract_from_text("word " * 500)
    assert status == "no_section"
    assert refs == []


def test_section_finder_stops_at_an_appendix():
    """Catches: swallowing appendix prose into the reference list,
    which produces long junk entries after the real ones."""
    seg = find_references_section(
        APA + "\n" + "filler line\n" * 60 + "\nAppendix A\nNot a reference at all.\n")
    assert "Not a reference at all" not in seg


def test_entries_without_a_year_fold_into_the_previous_one():
    """Catches: mis-splitting a wrapped entry. A continuation line
    beginning "Frank MJ. ..." matches the author shape; treating it as
    a new entry yields a fragment with no year. Every real reference
    has a year, so fragments are folded back."""
    entries = split_entries(
        "Smith, J. A. (2001). A title that runs on.\n"
        "Jones, K. and more continuation text here.\n")
    assert len(entries) == 1


# ---------- merge rule ----------

def _pdf(author, year, title, doi=""):
    return {"author": author, "year": year, "title": title, "doi": doi, "raw": ""}


def test_pdf_fills_a_blank_api_reference():
    """Catches: the fill step not running. Crossref deposits many
    references as a bare DOI with no author or title — 726 of 2929 in
    the reference corpus. Those render as a naked DOI string until the
    PDF supplies the words."""
    by_doi, by_ay = build_pdf_lookup([_pdf("Ashby", 2020, "Category learning", "10.1/x")])
    out = enrich({"text": "", "doi": "10.1/x", "sources": ["crossref"]}, by_doi, by_ay)
    assert out["text"] == "Ashby 2020 Category learning"
    assert out["sources"] == ["crossref", "pdf"]


def test_pdf_never_overwrites_an_api_supplied_title():
    """Catches: the merge preferring PDF text over deposited metadata.

    This is the core rule. A Crossref title is an assertion by the
    publisher; a PDF title is the output of a regex over a page. When
    both exist the API wins, or the record degrades to whatever parsed
    most recently."""
    by_doi, by_ay = build_pdf_lookup([_pdf("Ashby", 2020, "PARSED OFF THE PAGE", "10.1/x")])
    out = enrich({"text": "Ashby 2020 Deposited Title", "doi": "10.1/x",
                  "sources": ["crossref"]}, by_doi, by_ay)
    assert out["text"] == "Ashby 2020 Deposited Title"
    assert "pdf" in out["sources"], "still credited as a confirming source"


def test_pdf_supplies_a_doi_the_api_never_deposited():
    """Catches: refusing new DOIs. A DOI printed on the page but absent
    from the deposit is new information, not a conflict — and it is
    what turns an unlinkable reference into a citation link."""
    by_doi, by_ay = build_pdf_lookup([_pdf("Ashby", 2020, "T", "10.1/found")])
    out = enrich({"text": "Ashby 2020 T", "doi": "", "sources": ["crossref"]},
                 by_doi, by_ay)
    assert out["doi"] == "10.1/found"
    assert out["doi_from_pdf"] is True


def test_author_year_fallback_when_neither_side_has_a_doi():
    """Catches: only ever joining on DOI. Most printed references carry
    no DOI at all, so DOI-only joining leaves the majority unmatched."""
    by_doi, by_ay = build_pdf_lookup([_pdf("Blanco", 2022, "Immature cognitive control")])
    out = enrich({"text": "Blanco 2022", "doi": "", "sources": ["crossref"]},
                 by_doi, by_ay)
    assert "pdf" in out["sources"]


def test_pdf_only_references_are_appended_and_marked():
    """Catches: PDF-only references being silently merged in as though
    an API had vouched for them. The user must be able to tell which
    entries exist only because a page was parsed."""
    api = [{"text": "Ashby 2020 T", "doi": "10.1/x", "sources": ["crossref"]}]
    extra = pdf_only([_pdf("Newman", 1999, "Never deposited", "10.1/new")], api)
    assert len(extra) == 1
    assert extra[0]["sources"] == ["pdf"]
    assert extra[0]["pdf_only"] is True


def test_a_reference_already_in_the_api_list_is_not_duplicated():
    """Catches: every reference appearing twice — once from the API and
    once from the PDF — which is what happens without the dedupe."""
    api = [{"text": "Ashby 2020 T", "doi": "10.1/x", "sources": ["crossref"]}]
    assert pdf_only([_pdf("Ashby", 2020, "T", "10.1/x")], api) == []


def test_bare_doi_reference_is_deduped_by_doi_alone():
    """Catches: dropping the DOI arm of the dedupe.

    A reference deposited as a bare DOI has NO author or year text, so
    the author+year guard cannot see it. Only the DOI comparison stops
    the PDF's copy being appended as a second entry — and bare DOIs are
    the common case (726 of 2929 reference lines in the reference
    corpus), so this would visibly double them.

    Written after a mutation that removed the DOI guard survived the
    suite: the existing dedupe test happened to supply author+year too,
    so the weaker guard covered for the missing one."""
    api = [{"text": "", "doi": "10.1/x", "sources": ["crossref"]}]
    assert pdf_only([_pdf("Ashby", 2020, "Category learning", "10.1/x")], api) == []


def test_dedupe_falls_back_to_author_year_without_dois():
    """Catches: duplicate entries whenever the DOI is missing on one
    side, which is the common case for printed references."""
    api = [{"text": "Blanco 2022 Immature cognitive control", "doi": "",
            "sources": ["crossref"]}]
    assert pdf_only([_pdf("Blanco", 2022, "Immature cognitive control")], api) == []


@pytest.mark.parametrize("bad", [None, [], [{}], [{"author": "", "year": None}]])
def test_merge_tolerates_empty_or_malformed_pdf_input(bad):
    """Catches: an unreadable PDF taking down the paper view. The merge
    runs on every paper load, including ones with no PDF at all."""
    by_doi, by_ay = build_pdf_lookup(bad)
    ref = {"text": "Ashby 2020 T", "doi": "10.1/x", "sources": ["crossref"]}
    assert enrich(ref, by_doi, by_ay)["text"] == "Ashby 2020 T"
    assert pdf_only(bad, [ref]) == []
