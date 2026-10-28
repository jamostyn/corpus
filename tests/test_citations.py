"""Intra-corpus citation linking — index construction and the endpoints.

Links are DERIVED from what is on disk, never stored. These tests pin
the properties that makes worth having:
  * a link appears as soon as both papers exist, with no repair pass
  * DOIs that differ only in case or resolver prefix still match
  * references to papers outside the corpus stay unlinked
  * duplicate DOIs are surfaced, not silently collapsed
"""
import pytest

import citations


def write_summary(corpus_dir, slug, doi, refs=(), title=None, year="2020"):
    """Write a minimal summary MD. `refs` is a list of DOI strings (or
    raw markdown lines, when a test needs a specific shape)."""
    lines = [
        "---",
        f"title: {title or slug.replace('-', ' ').title()}",
        f"year: {year}",
        f"doi: {doi}",
        "schema_version: 1",
        "---",
        "",
        "## References",
    ]
    for r in refs:
        lines.append(r if str(r).lstrip().startswith("-")
                     else f"- **[Someone 1999 A Cited Work]** — DOI: {r}")
    p = corpus_dir / "summaries" / f"{slug}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------- normalize_doi ----------

def test_one_doi_normalizer_shared_by_matcher_and_parser():
    """Catches: a second DOI normalizer being reintroduced.

    Reference DOIs are folded by the reference-line parser, and paper
    DOIs are folded by the citation index. If those become two
    functions with even one differing rule, links silently disappear
    for the DOI forms they disagree on — and a missing link looks
    exactly like "these papers aren't related", so nobody notices.

    A mutation that dropped normalization on the reference side
    initially survived the suite precisely because both paths happened
    to normalize; this asserts they are literally the same object."""
    import _api_http
    import extract_references
    assert citations.normalize_doi is _api_http.normalize_doi
    assert extract_references._norm_doi is _api_http.normalize_doi


@pytest.mark.parametrize("raw,expected", [
    ("10.1/ABC",                      "10.1/abc"),
    ("https://doi.org/10.1/abc",      "10.1/abc"),
    ("http://dx.doi.org/10.1/abc",    "10.1/abc"),
    ("doi:10.1/abc",                  "10.1/abc"),
    ("  10.1/abc  ",                  "10.1/abc"),
    ("10.1/abc.",                     "10.1/abc"),
    ("unknown",                       ""),
    ("",                              ""),
    (None,                            ""),
])
def test_normalize_doi_forms(raw, expected):
    """Catches: comparing DOIs without normalizing.

    A paper's frontmatter DOI and a reference's DOI are deposited by
    different parties. Crossref returns `10.1523/JNEUROSCI...` in one
    place and `https://doi.org/10.1523/jneurosci...` in another. Raw
    string comparison silently misses those links, and a missing link
    looks identical to "these papers aren't related"."""
    assert citations.normalize_doi(raw) == expected


# ---------- index construction ----------

def test_link_appears_when_both_papers_exist(corpus_dir):
    """Catches: the core feature not working at all."""
    write_summary(corpus_dir, "citing-2023", "10.1/citing", refs=["10.1/cited"])
    write_summary(corpus_dir, "cited-2020", "10.1/cited")
    idx = citations.build_index()
    assert idx.outgoing["citing-2023"] == ["cited-2020"]
    assert idx.incoming["cited-2020"] == ["citing-2023"]
    assert idx.edges == [("citing-2023", "cited-2020")]


def test_link_is_not_stored_so_adding_a_paper_creates_it(corpus_dir):
    """Catches: a design regression to storing `in_corpus` on each
    reference line.

    This is the property the whole derived-not-stored decision buys.
    The citing paper's file is written ONCE, before the cited paper
    exists, and is never touched again — yet the link must appear the
    moment the second paper lands. If someone changes this to a stored
    flag, this test fails and the failure explains why."""
    citing = write_summary(corpus_dir, "early-2023", "10.1/early",
                           refs=["10.1/later"])
    before = citing.read_text(encoding="utf-8")
    assert citations.build_index().outgoing["early-2023"] == []

    write_summary(corpus_dir, "later-2024", "10.1/later")
    assert citations.build_index().outgoing["early-2023"] == ["later-2024"]
    assert citing.read_text(encoding="utf-8") == before, \
        "the citing summary must not be rewritten to record the link"


def test_case_and_prefix_differences_still_link(corpus_dir):
    """Catches: dropping normalization on either side of the match."""
    write_summary(corpus_dir, "a-2023", "10.1/a",
                  refs=["- **[X 1999 T]** — DOI: https://doi.org/10.1/TARGET"])
    write_summary(corpus_dir, "b-2020", "10.1/target")
    assert citations.build_index().outgoing["a-2023"] == ["b-2020"]


def test_references_outside_the_corpus_are_not_linked(corpus_dir):
    """Catches: linking to something that isn't there — e.g. matching on
    a falsy DOI so every ref without one resolves to the same paper."""
    write_summary(corpus_dir, "a-2023", "10.1/a",
                  refs=["10.1/not-here", "- **[Y 1990 No DOI Ref]** — no DOI"])
    write_summary(corpus_dir, "b-2020", "10.1/b")
    idx = citations.build_index()
    assert idx.outgoing["a-2023"] == []
    assert idx.ref_counts["a-2023"] == {"total": 2, "with_doi": 1, "linked": 0}


def test_paper_with_unknown_doi_can_cite_but_not_be_cited(corpus_dir):
    """Catches: `doi: unknown` being indexed as a literal DOI, which
    would make every unknown-DOI paper cite every other one.

    This is the exact case part 2 of the feature (PDF reference
    extraction for papers without a DOI) has to improve on, so pin the
    current behaviour."""
    write_summary(corpus_dir, "nodoi-2023", "unknown", refs=["10.1/target"])
    write_summary(corpus_dir, "other-2023", "unknown", refs=["10.1/target"])
    write_summary(corpus_dir, "target-2020", "10.1/target")
    idx = citations.build_index()
    assert idx.outgoing["nodoi-2023"] == ["target-2020"]
    assert "" not in idx.doi_to_slugs
    assert idx.incoming.get("nodoi-2023", []) == []


def test_duplicate_dois_are_surfaced_not_collapsed(corpus_dir):
    """Catches: `doi_to_slugs` mapping to a single slug.

    Two summaries CAN carry the same DOI — the same paper imported
    twice under different slugs. Jack's corpus has exactly this
    (`865.full` and `ashby-2022`). Keeping only one would drop real
    links from the other; hiding the condition would leave inflated
    counts unexplained."""
    write_summary(corpus_dir, "dupe-a", "10.1/same")
    write_summary(corpus_dir, "dupe-b", "10.1/same")
    write_summary(corpus_dir, "citer-2023", "10.1/citer", refs=["10.1/same"])
    idx = citations.build_index()
    assert idx.doi_to_slugs["10.1/same"] == ["dupe-a", "dupe-b"]
    assert idx.duplicate_dois == {"10.1/same": ["dupe-a", "dupe-b"]}
    assert idx.outgoing["citer-2023"] == ["dupe-a", "dupe-b"]


def test_self_citation_from_duplicate_doi_is_dropped(corpus_dir):
    """Catches: a paper appearing in its own cites list.

    A summary that references its own DOI (happens with duplicate
    imports and with errata) would otherwise produce a self-loop, which
    is meaningless in a citation graph and would corrupt any centrality
    measure computed from it later."""
    write_summary(corpus_dir, "selfie-2023", "10.1/self", refs=["10.1/self"])
    idx = citations.build_index()
    assert idx.outgoing["selfie-2023"] == []
    assert idx.edges == []


def test_ref_counts_report_the_three_populations(corpus_dir):
    """Catches: conflating "no DOI" with "not in corpus" in the counts
    the UI shows. They are different situations for the user: one is a
    metadata gap, the other is simply a paper they don't own."""
    write_summary(corpus_dir, "a-2023", "10.1/a", refs=[
        "10.1/in-corpus",
        "10.1/outside",
        "- **[Z 1990 Bare]** — no DOI",
    ])
    write_summary(corpus_dir, "b-2020", "10.1/in-corpus")
    counts = citations.build_index().ref_counts["a-2023"]
    assert counts == {"total": 3, "with_doi": 2, "linked": 1}


# ---------- resolve_references ----------

def test_resolve_references_tags_the_linked_slug(corpus_dir):
    """Catches: the per-reference `linked_slug` not being set, which is
    what the UI renders the "In corpus" chip from."""
    write_summary(corpus_dir, "b-2020", "10.1/cited")
    body = "## References\n- **[Ashby 2020 A Title]** — DOI: 10.1/cited\n"
    out = citations.resolve_references(body, citations.build_index())
    assert len(out) == 1
    assert out[0]["linked_slug"] == "b-2020"
    assert out[0]["doi"] == "10.1/cited"
    assert out[0]["text"] == "Ashby 2020 A Title"


def test_resolve_references_leaves_external_refs_unlinked(corpus_dir):
    """Catches: defaulting `linked_slug` to something truthy, which
    would put an "In corpus" chip on every reference."""
    write_summary(corpus_dir, "b-2020", "10.1/other")
    body = "## References\n- **[X 1999 T]** — DOI: 10.1/not-in-corpus\n"
    out = citations.resolve_references(body, citations.build_index())
    assert out[0]["linked_slug"] is None


def test_resolve_references_never_links_a_paper_to_itself(corpus_dir):
    """Catches: a paper's own reference list showing an "In corpus"
    chip pointing back at the paper being viewed."""
    write_summary(corpus_dir, "self-2023", "10.1/self")
    body = "## References\n- **[Me 2023 Mine]** — DOI: 10.1/self\n"
    out = citations.resolve_references(body, citations.build_index(),
                                       self_slug="self-2023")
    assert out[0]["linked_slug"] is None


# ---------- endpoints ----------

def test_paper_detail_carries_references_and_both_link_directions(client, corpus_dir):
    """Catches: the citation payload not reaching the frontend. The UI
    reads `references`, `cites`, `cited_by`, and `ref_counts` off this
    response; a missing key renders an empty section with no error."""
    write_summary(corpus_dir, "citing-2023", "10.1/citing", refs=["10.1/cited"])
    write_summary(corpus_dir, "cited-2020", "10.1/cited")

    d = client.get("/api/paper/citing-2023").get_json()
    assert d["cites"] == ["cited-2020"]
    assert d["cited_by"] == []
    assert d["ref_counts"] == {"total": 1, "with_doi": 1, "linked": 1}
    assert d["references"][0]["linked_slug"] == "cited-2020"

    d2 = client.get("/api/paper/cited-2020").get_json()
    assert d2["cited_by"] == ["citing-2023"]
    assert d2["cites"] == []


def test_citation_graph_endpoint_shape(client, corpus_dir):
    """Catches: the graph endpoint drifting from the shape connection
    analysis consumes — directed edges plus per-node degree counts."""
    write_summary(corpus_dir, "a-2023", "10.1/a", refs=["10.1/b"])
    write_summary(corpus_dir, "b-2020", "10.1/b")

    g = client.get("/api/citations").get_json()
    assert g["edges"] == [["a-2023", "b-2020"]]
    by_slug = {n["slug"]: n for n in g["nodes"]}
    assert by_slug["a-2023"]["cites_n"] == 1
    assert by_slug["a-2023"]["cited_by_n"] == 0
    assert by_slug["b-2020"]["cited_by_n"] == 1
    assert g["totals"]["papers"] == 2
    assert g["totals"]["edges"] == 1
    assert g["totals"]["refs_linked"] == 1
    assert g["duplicate_dois"] == {}


def test_citation_graph_reports_duplicate_dois(client, corpus_dir):
    """Catches: duplicate DOIs being invisible in the API. The user
    cannot fix a double import they can't see, and it silently inflates
    every count derived from the graph."""
    write_summary(corpus_dir, "dupe-a", "10.1/same")
    write_summary(corpus_dir, "dupe-b", "10.1/same")
    g = client.get("/api/citations").get_json()
    assert g["duplicate_dois"] == {"10.1/same": ["dupe-a", "dupe-b"]}


def test_citation_endpoints_require_a_corpus(client, corpus_dir, monkeypatch):
    """Catches: the endpoint 500ing instead of returning the standard
    corpus_not_set 400 when no corpus directory is configured.

    Same unset pattern as tests/test_note_endpoints.py — the root is a
    module global, so it is monkeypatched rather than set."""
    import _paths
    monkeypatch.setattr(_paths, "_CORPUS_ROOT", None)
    monkeypatch.delenv("CORPUS_DIR", raising=False)
    assert client.get("/api/citations").status_code == 400
