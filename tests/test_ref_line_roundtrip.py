"""`Reference.to_md_line()` and `parse_ref_line()` must stay inverses.

They are the only writer and the only reader of the reference-line
format, and they live in the same file so a change to one is obviously
adjacent to the other. This suite is what actually enforces it.

Why it matters beyond tidiness: intra-corpus citation links are matched
on reference DOIs recovered by the parser. If the writer changes shape
and the parser doesn't follow, every link silently disappears — the UI
shows no error, just an empty "In-corpus connections" section.
"""
import pytest

from extract_references import Reference, parse_ref_line, parse_references_section


CASES = [
    pytest.param(Reference(author_block="Ashby", year=2020,
                           title="Categorization as Decision Making",
                           doi="10.1234/abc", doi_source="structured"),
                 id="full-structured"),
    pytest.param(Reference(title="A Title With No Author",
                           doi="10.1234/def", doi_source="structured"),
                 id="title-only"),
    pytest.param(Reference(author_block="Tulving", year=1972,
                           doi="10.1234/ghi", doi_source="structured"),
                 id="author-year-no-title"),
    pytest.param(Reference(doi="10.1234/jkl", doi_source="structured"),
                 id="doi-only"),
    pytest.param(Reference(title="Smith, J. (1999). Raw citation text here.",
                           unstructured=True),
                 id="unstructured-no-doi"),
    pytest.param(Reference(title="Jones, K. (2001). Another raw one.",
                           doi="10.1234/mno", doi_source="text-scan",
                           unstructured=True),
                 id="unstructured-extracted-doi"),
    pytest.param(Reference(author_block="Miller", year=1956,
                           title="The Magical Number Seven", kind="book"),
                 id="kind-book-no-doi"),
    pytest.param(Reference(author_block="Doe", year=2010,
                           title="No DOI At All"),
                 id="no-doi-no-kind"),
]


@pytest.mark.parametrize("ref", CASES)
def test_line_survives_a_render_parse_render_cycle(ref):
    """Catches: the writer and parser drifting apart.

    Renders, parses, re-renders. The two rendered lines must be
    identical — that is the property the citation index depends on. A
    change to either side alone breaks this for at least one shape."""
    once = ref.to_md_line()
    parsed = parse_ref_line(once)
    assert parsed is not None, f"parser rejected its own output: {once!r}"
    assert parsed.to_md_line() == once


@pytest.mark.parametrize("ref", CASES)
def test_doi_survives_the_round_trip(ref):
    """Catches: a DOI being mangled by rendering or parsing.

    Called out separately from the line-equality test because the DOI
    is the ONLY field intra-corpus linking matches on. A change that
    preserved the line but corrupted the DOI would pass the test above
    while breaking every link."""
    parsed = parse_ref_line(ref.to_md_line())
    assert parsed.doi == ref.doi


def test_extracted_flag_survives():
    """Catches: losing the `(extracted)` marker, which tells the user a
    DOI was regex-fished out of raw text rather than deposited by the
    publisher — i.e. how much to trust it."""
    ref = Reference(title="raw text", doi="10.1/x",
                    doi_source="text-scan", unstructured=True)
    assert parse_ref_line(ref.to_md_line()).doi_source == "text-scan"
    plain = Reference(title="T", doi="10.1/y", doi_source="structured")
    assert parse_ref_line(plain.to_md_line()).doi_source == "structured"


def test_kind_survives_when_there_is_no_doi():
    """Catches: dropping the book/chapter/series tag, which is the only
    type signal for references the publisher deposited without a DOI."""
    for kind in ("book", "chapter", "series"):
        ref = Reference(author_block="X", year=1990, title="T", kind=kind)
        assert parse_ref_line(ref.to_md_line()).kind == kind


def test_non_reference_lines_are_ignored():
    """Catches: the parser treating prose or headings as references,
    which would inject junk entries into the reference list."""
    for line in ("", "   ", "## References", "Some prose.", "* not a dash"):
        assert parse_ref_line(line) is None


def test_parse_section_reads_only_the_references_block():
    """Catches: the section parser picking up bullets from earlier
    sections (Findings, Limitations, etc. are also bullet lists), which
    would inflate reference counts and create bogus links."""
    body = (
        "## Findings\n"
        "- This bullet is NOT a reference\n"
        "- Neither is this one\n"
        "\n"
        "## References\n"
        "- **[Ashby 2020 A Title]** — DOI: 10.1/a\n"
        "- **[Doe 1999 Another]** — DOI: 10.1/b\n"
    )
    refs = parse_references_section(body)
    assert [r.doi for r in refs] == ["10.1/a", "10.1/b"]


def test_missing_references_section_is_empty_not_an_error():
    """Catches: raising on a paper whose publisher deposited no
    references. `refs_source: none` is a normal state for older
    articles, books, and theses."""
    assert parse_references_section("## Findings\n- a\n") == []
    assert parse_references_section("") == []
