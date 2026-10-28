"""Rich fixture metadata dict used by both the golden-file capture
script and the render_frontmatter equivalence test. Every emission
kind in render_frontmatter should have SOMETHING here so the test
catches drift across the whole function.

Kept in a shared module so the golden file and the test are guaranteed
to use identical input.
"""
from __future__ import annotations

FIXTURE_SLUG     = "kahneman-1979"
FIXTURE_ADDED_AT = "2026-08-16T20:00:00"
# `render_frontmatter` also stamps `last_extracted` + `citation_count_as_of`
# with `datetime.now()`. Test freezes that.
FIXTURE_NOW      = "2026-08-16T20:00:00"

FIXTURE_META = {
    # ---- Always-emitted core ----
    "author":       "Kahneman, D.",
    "authors_full": ["Kahneman D.", "Tversky A."],
    "authors_detailed": [
        {
            "family": "Kahneman", "given": "Daniel",
            "institutions": ["Princeton University", "Hebrew University"],
            "orcid": "0000-0001-2345-6789",
            "position": "first",
        },
        {
            "family": "Tversky", "given": "Amos",
            "institutions": ["Stanford University"],
        },
    ],
    "year":       1979,
    "title":      "Prospect Theory: An Analysis of Decision under Risk",
    "kind":       "article",
    "paper_type": "empirical",
    "publisher":  "Econometric Society",
    "doi":        "10.2307/1914185",
    "source_url": "https://doi.org/10.2307/1914185",
    "status":     "prefilled",
    "citation_count":  42000,
    "sources":         ["crossref", "openalex"],
    "refs_source":     "crossref+ss",
    "needs_doi":       False,
    "pages":           "263-292",

    # ---- Extended Crossref scalars ----
    "volume":         "47",
    "issue":          "2",
    "article_number": "1914185",
    "language":       "en",

    # ---- Simple string lists ----
    "issn":             ["0012-9682", "1468-0262"],
    "isbn":             [],  # empty — must NOT emit
    "alternative_ids":  ["arXiv:1234"],
    "subjects":         ["Economics", "Psychology"],

    # ---- Integer counts ----
    "references_count": 87,

    # ---- Retracted + updates ----
    "retracted":     True,
    "update_to":     [
        {"doi": "10.2307/9999", "type": "correction", "label": "Corrected typo in eq. 3"},
    ],
    "update_policy": "10.2307/policy",

    # ---- Funder + license ----
    "funder": [
        {"name": "NSF", "doi": "10.13039/100000001", "awards": ["BCS-1234", "BCS-5678"]},
    ],
    "license": [
        {"url": "https://creativecommons.org/licenses/by/4.0/", "type": "cc-by", "delay_days": 0},
    ],

    # ---- Event fields ----
    "event_name":     "Annual Meeting",
    "event_acronym":  "AM26",
    "event_location": "Boston, MA",

    # ---- SS-derived ----
    "citation_count_ss":             40500,
    "influential_citation_count_ss": 12000,
    "refs_crossref_count":           87,
    "refs_ss_count":                 84,
    "refs_confirmed_by_ss":          78,
    "refs_ss_only":                  6,
    "ss_confirmed_dois": ["10.1037/x", "10.1126/y"],
    "ss_only_refs": [
        {"doi": "10.9999/only-ss", "title": "SS-only ref", "year": 1978},
    ],
    "publication_types": ["JournalArticle", "Review"],
    "s2_fields_of_study": [
        {"category": "Economics",  "source": "external"},
        {"category": "Psychology", "source": "s2-fos-model"},
    ],
    "open_access_pdf_url":     "https://example.com/paper.pdf",
    "open_access_pdf_status":  "green",
    "open_access_pdf_license": "cc-by",
    "ss_paper_id":             "abc123",
    "ss_arxiv_id":             "1234.5678",
    "ss_pubmed_id":            "12345678",
    "tldr":         "The paper proposes prospect theory.\nIt replaces expected utility.",
    "abstract":     "We present a critique of expected utility theory.\n\nSecond paragraph.",
    "bibtex":       "@article{kahneman1979,\n  title = {Prospect Theory}\n}",
    "embedding":    [0.1, -0.2, 0.3, 0.4],
    "tldr_model":     "specter2",
    "embedding_model": "specter2",
    "_ss_authors_raw": [
        {"name": "Daniel Kahneman", "ss_id": "ss-kahn", "orcid": "0000-0001-2345-6789",
         "affiliations": ["Princeton University"],
         "h_index": 100, "papers_count": 300, "citation_count": 400000},
    ],

    # ---- OA-derived ----
    "citation_count_oa": 41000,
    "fwci":              5.2345,
    "oa_status":         "green",
    "is_oa":             True,
    "oa_paper_id":       "W1234567",
    "retraction_notice": "The paper contained a typo in eq. 3.\nCorrected 2020-01-01.",
    "oa_authors": [
        {"family": "Kahneman", "given": "Daniel",
         "institutions": [{"name": "Princeton University", "ror": "https://ror.org/00hx57361"}]},
    ],
    "topics":       [{"display_name": "Behavioral Economics", "score": 0.95}],
    "keywords":     [{"display_name": "prospect theory"}],
    "oa_locations": [{"is_oa": True, "landing_page_url": "https://example.com"}],
    "counts_by_year": [{"year": 2023, "cited_by_count": 500}],
    "versions":       [{"version": "publishedVersion", "url": "https://example.com/paper.pdf"}],
    "content_assertions": [{"label": "peer-reviewed"}],

    # ---- More Crossref extras ----
    "edition_number":     "2nd",
    "chapter_number":     "3",
    "component_number":   "1",
    "journal_issue_date": "2026-03-15",
    "deposited_at":       "2026-04-01",
    "indexed_at":         "2026-05-01",

    # ---- SS venue ----
    "ss_venue_type":            "journal",
    "ss_venue_url":             "https://www.jstor.org/journal/econometrica",
    "ss_venue_alternate_names": ["Econometrica"],

    # ---- OA extras ----
    "venue_type":                 "journal",
    "host_organization":          "https://openalex.org/P4310320290",
    "host_organization_lineage":  ["https://openalex.org/P4310320290"],
    "has_fulltext":               True,
    "fulltext_origin":            "ngrams",
    "is_paratext":                False,
    "oa_created_date":            "2015-01-01",
    "oa_updated_date":            "2026-08-01",

    # ---- Provenance (subset of PROVENANCE_FIELDS) ----
    "_provenance": {
        "doi":              ["crossref", "openalex"],
        "title":            ["crossref"],
        "year":             ["crossref", "openalex", "semanticscholar"],
        "authors_detailed": ["crossref"],
        "citation_count":   ["crossref"],
    },
}
