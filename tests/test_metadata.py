"""extract_metadata.py — pure-function helpers that don't hit the network.

DOI candidate ranking, title-candidate filters. Anything that requires
Crossref/OA/SS is skipped here — integration tests belong elsewhere.
"""


def test_doi_regex_finds_standard_shape():
    from extract_metadata import _extract_doi_candidates
    cands = _extract_doi_candidates("DOI: 10.1038/nature12345 elsewhere")
    assert cands
    assert cands[0][0] == "10.1038/nature12345"


def test_doi_supplement_collapses():
    from extract_metadata import _extract_doi_candidates
    cands = _extract_doi_candidates(
        "10.1073/pnas.1912330117/-/DCSupplemental "
        "and later 10.1073/pnas.1912330117"
    )
    # Both entries collapse to the base DOI — dedup keeps one.
    dois = [d for d, _ in cands]
    assert "10.1073/pnas.1912330117" in dois
    assert not any("/-/" in d for d in dois)


def test_masthead_beats_citation():
    """DOI in the masthead (position 0) with 'https://doi.org/' prefix should
    outscore a citation-context DOI further down."""
    from extract_metadata import _rank_dois
    text = (
        "Article Title\n"
        "https://doi.org/10.1234/masthead\n"
        "Body of paper.\n"
        "Nosofsky et al., 1988. Categorization. J. Exp. Psy. "
        "doi:10.5555/citation\n"
    )
    ranked = _rank_dois(text)
    assert ranked[0][0] == "10.1234/masthead"


def test_title_filter_rejects_journal_name():
    from extract_metadata import _looks_like_container_title
    for junk in (
        "Proceedings of the Annual Meeting of the Cognitive Science Society",
        "Journal of Experimental Psychology",
        "The Annual Meeting",
        "Nature Neuroscience",
        "PLOS ONE",
        "Frontiers in Psychology",
        "IEEE Transactions on Something",
        "Brain and Cognition",
    ):
        assert _looks_like_container_title(junk), f"should be rejected: {junk!r}"


def test_title_filter_accepts_real_titles():
    from extract_metadata import _looks_like_container_title
    for good in (
        "Rule discovery performance unchanged by incentives",
        "Category Learning Through Active Sampling",
        "Feedback and stimulus-offset timing effects in perceptual category learning",
    ):
        assert not _looks_like_container_title(good), f"should be accepted: {good!r}"


def test_metadata_label_soup_rejected():
    from extract_metadata import _looks_like_metadata_label_soup
    assert _looks_like_metadata_label_soup("Copyright Information")
    assert _looks_like_metadata_label_soup("Publication Date")
    assert _looks_like_metadata_label_soup(
        "Title Permalink Journal Authors Publication Date Copyright Information"
    )
    # Real titles that happen to contain a label word should NOT be caught.
    assert not _looks_like_metadata_label_soup(
        "Working memory dynamics bias the generation of beliefs"
    )


# ---------- Shared _api_http helpers (2026-08-16 dedup pass) ----------


def test_shared_doi_regex_catches_bare_and_stops_at_boundaries():
    from _api_http import DOI_RE
    text = (
        'Article body 10.1073/pnas.1912330117 more text, '
        'and 10.1038/nature12345; '
        'and one wrapped (10.1234/foo.bar).'
    )
    matches = [m.group(0) for m in DOI_RE.finditer(text)]
    assert "10.1073/pnas.1912330117" in matches
    assert "10.1038/nature12345" in matches
    assert "10.1234/foo.bar" in matches


def test_split_display_name_handles_all_shapes():
    from _api_http import split_display_name
    # Full given + family
    assert split_display_name("Endel Tulving")   == ("Tulving",  "Endel")
    assert split_display_name("Daniel Kahneman") == ("Kahneman", "Daniel")
    # Surname + initials (fast path)
    assert split_display_name("Smith J.")   == ("Smith",    "J.")
    assert split_display_name("Kahneman D.") == ("Kahneman", "D.")
    # Middle-initial form ("Given M. Family")
    assert split_display_name("John R. Anderson") == ("Anderson", "John R.")
    # Single token
    assert split_display_name("Cher") == ("Cher", "")
    # Edge cases
    assert split_display_name("") == ("", "")
    assert split_display_name("   ") == ("", "")


def test_entity_key_python_parity():
    """The JS `EntityKeys.author` / `EntityKeys.journal` in
    src/entity-keys.js must produce byte-identical output to the
    Python `_author_key` / `_journal_key` in server.py — otherwise
    paper-detail's deep-link anchors 404 on the backend.

    tests/src/entity-keys.test.js asserts the JS side against the
    same fixtures; this test asserts the Python side. If either
    language drifts, exactly one of the two suites fails, surfacing
    the mismatch immediately.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
    from entities_api import _author_key, _institution_key, _journal_key

    # Author fixtures — mirror tests/src/entity-keys.test.js.
    assert _author_key("Kahneman", "Daniel")   == "kahneman-daniel"
    assert _author_key("Smith",    "J.")       == "smith-j"
    assert _author_key("Cher",     "")         == "cher"
    assert _author_key("Anderson", "John R.")  == "anderson-john"
    assert _author_key("Müller",   "Hans")     == "muller-hans"
    assert _author_key("Peña",     "María")    == "pena-maria"
    assert _author_key("O'Brien",  "Sean")     == "o-brien-sean"
    assert _author_key("van der Berg", "A.")   == "van-der-berg-a"

    # Journal fixtures.
    assert _journal_key("Cognition", ["0010-0277"])                 == "issn-0010-0277"
    assert _journal_key("Nature",    ["0028-0836", "1476-4687"])    == "issn-0028-0836"
    assert _journal_key("Any",       [" 1234-567x "])               == "issn-1234-567X"
    assert _journal_key("PLOS ONE",                     [])         == "plos-one"
    assert _journal_key("Journal of Neuroscience",      [])         == "journal-of-neuroscience"
    assert _journal_key("Zeitschrift für Psychologie",  [])         == "zeitschrift-fur-psychologie"
    assert _journal_key("",                             [])         == "unknown"
    # Bare-string ISSN — Python coerces internally at the aggregator
    # site (before calling _journal_key), so _journal_key itself only
    # sees a list. The frontend regression fixture lives in
    # tests/src/entity-keys.test.js.
    assert _journal_key("Nature", ["0028-0836"])                    == "issn-0028-0836"

    # Institution fixtures.
    assert _institution_key("MIT",       "https://ror.org/042nb2s44") == "ror-042nb2s44"
    assert _institution_key("Any",       "01tgyzw49")                 == "ror-01tgyzw49"
    assert _institution_key("Massachusetts Institute of Technology", "") == "massachusetts-institute-of-technology"
    assert _institution_key("Princeton University",   "")             == "princeton-university"
    assert _institution_key("Université de Montréal", "")             == "universite-de-montreal"
    assert _institution_key("",                       "")             == "unknown"


def test_crossref_type_to_kind_mapping():
    from _api_http import crossref_type_to_kind
    assert crossref_type_to_kind("journal-article")     == "article"
    assert crossref_type_to_kind("proceedings-article") == "article"
    assert crossref_type_to_kind("article")             == "article"
    assert crossref_type_to_kind("book-chapter")        == "chapter"
    assert crossref_type_to_kind("book")                == "book"
    assert crossref_type_to_kind("monograph")           == "book"
    assert crossref_type_to_kind("dissertation")        == "thesis"
    assert crossref_type_to_kind("report")              == "report"
    # Case-insensitive
    assert crossref_type_to_kind("JOURNAL-ARTICLE")     == "article"
    # Unknown → None (callers pick their own default)
    assert crossref_type_to_kind("dataset")             is None
    assert crossref_type_to_kind("")                    is None
    assert crossref_type_to_kind(None)                  is None


def test_an_inverted_name_keeps_its_surname_first():
    """Catches "Wei, Jason" (OpenAlex's form for some arXiv authors) split
    token by token into family "Jason", given "Wei," — Wei et al. 2022
    imported as jason-2022 — or a "Jr." suffix taken for a given name."""
    from _api_http import split_display_name
    assert split_display_name("Wei, Jason") == ("Wei", "Jason")
    assert split_display_name("Chi, Ed  H.") == ("Chi", "Ed H.")
    assert split_display_name("John Smith, Jr.") == ("Smith", "John")
    assert split_display_name("Smith,") == ("Smith", "")
