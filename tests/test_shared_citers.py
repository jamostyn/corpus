"""Shared citers of a note's papers (experimental).

Requirement (2026-10-30): from any note linking two or more papers, list
the works that cite at least two of them and are not themselves in the
note — both those already in the corpus and those not.

Built from the stored citer lists; each listed work also shows its
citation count (requested 2026-11-02), looked up from OpenAlex — stubbed
here, so nothing touches the network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import citations
import citers
import citers_api
import openalex_client
from notes_api import linked_paper_slugs
from shared_citers import add_counts, shared_citers


@pytest.fixture(autouse=True)
def stub_counts(monkeypatch):
    """OpenAlex counts: W<n> has n*10 citations; ids in `lost` fail.
    Records every id asked for."""
    state = {"asked": [], "lost": set()}

    def works_by(field, values, select):
        assert field == "openalex"
        state["asked"] += values
        ok = [v for v in values if v not in state["lost"]]
        return ([{"id": f"https://openalex.org/{v}", "cited_by_count": int(v[1:]) * 10} for v in ok],
                len(values) - len(ok))

    monkeypatch.setattr(openalex_client, "openalex_works_by", works_by)
    monkeypatch.setattr(citers_api, "_SHARED_COUNTS", {})
    return state


def _summary(corpus_dir: Path, slug: str, doi: str) -> None:
    d = corpus_dir / "summaries"
    d.mkdir(exist_ok=True)
    (d / f"{slug}.md").write_text(f"---\ntitle: {slug} title\nyear: 2020\ndoi: {doi}\n---\nbody\n")


def _store(corpus_dir: Path, slug: str, wid: str, rows: list, complete: bool = True) -> None:
    d = corpus_dir / "citers"
    d.mkdir(exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps({
        "version": citers.CITERS_VERSION, "slug": slug, "doi": f"10.1/{slug}",
        "openalex_id": wid, "complete": complete, "fields": citers.FIELDS, "rows": rows}))


def _note(corpus_dir: Path, nid: str, slugs: list[str]) -> None:
    d = corpus_dir / "notes"
    d.mkdir(exist_ok=True)
    body = "".join(f'<p><a href="#" data-open-paper="{s}">{s}</a></p>' for s in slugs)
    (d / f"{nid}.json").write_text(json.dumps({"id": nid, "title": "N", "body_html": body}))


def _payload(wid, rows, complete=True):
    return {"openalex_id": wid, "complete": complete, "rows": rows}


def test_only_works_citing_two_or_more_note_papers_are_listed():
    """Catches listing every citer of any one paper (the union) instead
    of the overlap."""
    found = shared_citers({
        "a": _payload("WA", [["W1", "", 2021, "Both"], ["W2", "", 2021, "Only A"]]),
        "b": _payload("WB", [["W1", "", 2021, "Both"], ["W3", "", 2022, "Only B"]]),
    }, {})
    assert [c["openalex_id"] for c in found] == ["W1"]
    assert found[0]["cites"] == ["a", "b"]


def test_a_note_paper_citing_another_is_left_out():
    """Catches suggesting a paper the note already links: B cites A and
    C, but B is in the note. Matched by DOI and by OpenAlex id, since a
    citer row's DOI can be blank."""
    rows = [["WB", "", 2022, "B by id"], ["W9", "10.1/b", 2022, "B by DOI"]]
    found = shared_citers({"a": _payload("WA", rows), "c": _payload("WC", rows),
                           "b": _payload("WB", [])}, {"10.1/b": ["b"]})
    assert found == []


def test_in_corpus_citers_carry_their_slug_and_others_none():
    """Catches the two groups being mixed up: a shared citer whose DOI
    is a corpus paper must name it; one outside must have no slug."""
    rows = [["W1", "10.1/mine", 2021, "Mine"], ["W2", "10.9/x", 2020, "Stranger"]]
    found = shared_citers({"a": _payload("WA", rows), "b": _payload("WB", rows)},
                          {"10.1/mine": ["mine-2021"]})
    assert {c["openalex_id"]: c["slug"] for c in found} == {"W1": "mine-2021", "W2": None}


def test_works_citing_more_note_papers_come_first():
    """Catches an order that buries the most connected works below ones
    citing just two papers."""
    two, three = ["W2", "", 2024, "Two"], ["W3", "", 2001, "Three"]
    found = shared_citers({"a": _payload("WA", [two, three]), "b": _payload("WB", [two, three]),
                           "c": _payload("WC", [three])}, {})
    assert [c["openalex_id"] for c in found] == ["W3", "W2"]


def test_highlight_links_count_and_each_paper_counts_once():
    """Catches a paper linked twice (or once as a highlight) counting as
    two papers, which would enable the search for a one-paper note."""
    html = ('<a data-open-paper="a">x</a><a data-open-paper="a" data-open-highlight="h1">y</a>'
            '<a data-open-author="smith">s</a><a data-open-paper="b&#x27;bad">z</a>')
    assert linked_paper_slugs(html) == ["a"]


def test_note_endpoint_reports_overlap_and_papers_without_lists(client, corpus_dir):
    """Catches the route ignoring the note's links, or hiding which
    papers had no stored list (so an empty answer looks complete)."""
    for s in ("a", "b", "c"):
        _summary(corpus_dir, s, f"10.1/{s}")
    _summary(corpus_dir, "mine", "10.1/mine")
    shared = [["W1", "10.1/mine", 2021, "Mine"], ["W2", "", 2020, "Stranger"]]
    _store(corpus_dir, "a", "WA", shared)
    _store(corpus_dir, "b", "WB", shared, complete=False)
    _note(corpus_dir, "n1", ["a", "b", "c", "gone"])
    citations.clear_index_cache()

    r = client.get("/api/note/n1/shared-citers").get_json()
    assert {p["slug"]: p["status"] for p in r["papers"]} == {
        "a": "stored", "b": "partial", "c": "not_fetched"}
    assert [c["slug"] for c in r["in_corpus"]] == ["mine"]
    assert [c["title"] for c in r["elsewhere"]] == ["Stranger"]
    assert r["elsewhere_total"] == 1


def test_one_paper_with_a_list_finds_nothing(client, corpus_dir):
    """Catches a single stored list being compared with itself."""
    _summary(corpus_dir, "a", "10.1/a")
    _summary(corpus_dir, "b", "10.1/b")
    _store(corpus_dir, "a", "WA", [["W1", "", 2021, "X"]])
    _note(corpus_dir, "n1", ["a", "b"])
    r = client.get("/api/note/n1/shared-citers").get_json()
    assert r["in_corpus"] == [] and r["elsewhere_total"] == 0


def test_a_missing_note_is_a_404(client, corpus_dir):
    assert client.get("/api/note/nope/shared-citers").status_code == 404


def test_the_button_and_the_server_agree_on_the_minimum():
    """Catches the note button's threshold drifting from the server's:
    a button enabled for a note the server cannot answer, or disabled
    for one it can. The two live in different languages."""
    import re
    from shared_citers import MIN_PAPERS
    js = (Path(__file__).resolve().parent.parent / "src" / "shared-citers.js").read_text()
    assert int(re.search(r"const MIN_PAPERS = (\d+);", js).group(1)) == MIN_PAPERS


def test_each_listed_work_gets_its_citation_count(client, corpus_dir, stub_counts):
    """Catches the count missing from either group or from rows past the
    first page, and a failed lookup not reported to the dialog."""
    for s in ("a", "b"):
        _summary(corpus_dir, s, f"10.1/{s}")
    _summary(corpus_dir, "mine", "10.1/mine")
    shared = [["W1", "10.1/mine", 2021, "Mine"], ["W2", "", 2020, "S2"], ["W3", "", 2019, "S3"]]
    _store(corpus_dir, "a", "WA", shared)
    _store(corpus_dir, "b", "WB", shared)
    _note(corpus_dir, "n1", ["a", "b"])
    citations.clear_index_cache()

    r = client.get("/api/note/n1/shared-citers?limit=1").get_json()
    assert r["in_corpus"][0]["cited_by_count"] == 10
    assert r["elsewhere"][0]["cited_by_count"] == 20
    r = client.get("/api/note/n1/shared-citers?offset=1&limit=1").get_json()
    assert r["elsewhere"][0]["cited_by_count"] == 30 and r["counts_failed"] == 0
    # A lost lookup is reported, so the dialog can say counts are missing.
    citers_api._SHARED_COUNTS.pop("W3")
    stub_counts["lost"] = {"W3"}
    r = client.get("/api/note/n1/shared-citers?offset=1&limit=1").get_json()
    assert r["counts_failed"] == 1 and r["elsewhere"][0]["cited_by_count"] is None


def test_counts_are_looked_up_once_and_failures_retried(stub_counts):
    """Catches re-requesting known counts on every open (or page), and
    caching a failed lookup so the count never appears. A failed count
    is None, not 0 — 0 would read as "never cited"."""
    cache = {}
    stub_counts["lost"] = {"W2"}
    rows = [{"openalex_id": "W1"}, {"openalex_id": "W2"}]
    assert add_counts(rows, cache, openalex_client.openalex_works_by) == 1
    assert [r["cited_by_count"] for r in rows] == [10, None]
    stub_counts["asked"].clear()
    stub_counts["lost"] = set()
    add_counts(rows, cache, openalex_client.openalex_works_by)
    assert stub_counts["asked"] == ["W2"]
    assert rows[1]["cited_by_count"] == 20

