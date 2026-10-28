"""Stored citers: fetch, store, and the in-corpus / elsewhere split.

Requirement (2026-09-22): store the citers of each paper, show them in
the info panel with a clear in-corpus / elsewhere distinction like the
references, and keep the citers list out of the bridge finder for now.

OpenAlex is stubbed throughout — nothing here touches the network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import citations
import openalex_client


def _summary(corpus_dir: Path, slug: str, doi: str, title: str = "T") -> None:
    d = corpus_dir / "summaries"
    d.mkdir(exist_ok=True)
    (d / f"{slug}.md").write_text(
        f"---\ntitle: {title}\nyear: 2020\ndoi: {doi}\ncitation_count: 3\n---\nbody\n")


@pytest.fixture
def stub_openalex(monkeypatch):
    """Serve `pages` of citer works for any paper; record calls."""
    state = {"pages": [], "fail_after": None}

    def works_by(field, values, select):
        return [{"id": "https://openalex.org/W1", "cited_by_count": 3}], 0

    def citer_pages(wid, select=None):
        for i, page in enumerate(state["pages"]):
            if state["fail_after"] is not None and i >= state["fail_after"]:
                raise openalex_client.CiterFetchError("boom")
            yield page, {"count": sum(len(p) for p in state["pages"])}

    monkeypatch.setattr(openalex_client, "openalex_works_by", works_by)
    monkeypatch.setattr(openalex_client, "openalex_citer_pages", citer_pages)
    citations.clear_index_cache()
    return state


def _work(wid, doi, title="A citer", year=2023):
    return {"id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}" if doi else None,
            "publication_year": year, "display_name": title}


def test_before_fetching_the_panel_is_told_nothing_is_stored(client, corpus_dir):
    """Catches reporting "no citers" for a paper nobody has fetched —
    the two mean very different things, and only one is true."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    r = client.get("/api/paper/target-2020/citers").get_json()
    assert r["status"] == "not_fetched"
    assert r["citation_count"] == 3


def test_citers_are_split_into_in_corpus_and_elsewhere(client, corpus_dir, stub_openalex):
    """Catches the in-corpus / elsewhere distinction being wrong or missing: a
    citer whose DOI is a corpus paper must come back linked to its slug,
    and every other citer must not."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    _summary(corpus_dir, "mine-2023", "10.1/mine")
    stub_openalex["pages"] = [[_work("W2", "10.1/mine"), _work("W3", "10.9/stranger")]]
    assert client.post("/api/paper/target-2020/citers/fetch").status_code == 200

    r = client.get("/api/paper/target-2020/citers").get_json()
    assert r["status"] == "ok" and r["stored_count"] == 2
    assert [c["slug"] for c in r["in_corpus"]] == ["mine-2023"]
    assert [c["doi"] for c in r["elsewhere"]] == ["10.9/stranger"]
    assert r["elsewhere_total"] == 1


def test_in_corpus_is_decided_at_read_time_not_stored(client, corpus_dir, stub_openalex):
    """Catches baking the in-corpus flag into the file: importing a citer
    AFTER the fetch must move it into the corpus group with no refetch."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W3", "10.9/later")]]
    client.post("/api/paper/target-2020/citers/fetch")
    assert client.get("/api/paper/target-2020/citers").get_json()["in_corpus"] == []

    _summary(corpus_dir, "later-2024", "10.9/later")          # imported afterwards
    citations.clear_index_cache()
    r = client.get("/api/paper/target-2020/citers").get_json()
    assert [c["slug"] for c in r["in_corpus"]] == ["later-2024"]
    stored = json.loads((corpus_dir / "citers" / "target-2020.json").read_text())
    assert "in_corpus" not in json.dumps(stored)


def test_the_paper_is_never_listed_as_its_own_citer(client, corpus_dir, stub_openalex):
    """Catches a paper showing up "in your corpus" under its own citers —
    OpenAlex lists preprint/published pairs this way."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W9", "10.1/target")]]
    client.post("/api/paper/target-2020/citers/fetch")
    r = client.get("/api/paper/target-2020/citers").get_json()
    assert r["in_corpus"] == [] and r["elsewhere_total"] == 0


def test_the_elsewhere_list_is_paged(client, corpus_dir, stub_openalex):
    """Catches shipping every citer to the panel at once — PRISMA has
    ~105k, which would freeze the pane."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work(f"W{i}", f"10.9/{i}") for i in range(120)]]
    client.post("/api/paper/target-2020/citers/fetch")
    first = client.get("/api/paper/target-2020/citers?limit=50").get_json()
    assert len(first["elsewhere"]) == 50 and first["elsewhere_total"] == 120
    last = client.get("/api/paper/target-2020/citers?offset=100&limit=50").get_json()
    assert len(last["elsewhere"]) == 20


def test_a_failed_page_stores_a_partial_list_marked_incomplete(client, corpus_dir, stub_openalex):
    """Catches a short list that looks whole: a fetch that dies halfway
    must say so, not present 40% of the citers as all of them."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W1a", "10.9/a")], [_work("W1b", "10.9/b")]]
    stub_openalex["fail_after"] = 1
    client.post("/api/paper/target-2020/citers/fetch")
    r = client.get("/api/paper/target-2020/citers").get_json()
    assert r["complete"] is False and r["stored_count"] == 1


def test_a_paper_without_a_doi_cannot_be_fetched(client, corpus_dir):
    """Catches a fetch that quietly stores an empty list for a DOI-less
    paper — which would then read as "nobody cites this"."""
    _summary(corpus_dir, "nodoi-2020", "unknown")
    assert client.post("/api/paper/nodoi-2020/citers/fetch").status_code == 400
    assert not (corpus_dir / "citers" / "nodoi-2020.json").exists()


def test_rows_are_stored_compactly(client, corpus_dir, stub_openalex):
    """Catches storing one keyed object per citer. At ~105k rows for the
    largest paper, repeating four key names per row roughly doubles the
    file for nothing."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W2", "10.9/x")]]
    client.post("/api/paper/target-2020/citers/fetch")
    stored = json.loads((corpus_dir / "citers" / "target-2020.json").read_text())
    assert stored["fields"] == ["openalex_id", "doi", "year", "title"]
    assert stored["rows"] == [["W2", "10.9/x", 2023, "A citer"]]


def test_a_rename_carries_the_stored_citers(corpus_dir, client):
    """Catches leaving citers behind on a slug rename — the store is the
    most expensive thing a paper owns to rebuild."""
    from slug_migration import migrate_paper_slug
    (corpus_dir / "citers").mkdir(exist_ok=True)
    (corpus_dir / "citers" / "unknown-2020.json").write_text("{}")
    counts = migrate_paper_slug("unknown-2020", "smith-2020")
    assert counts["citers"] == 1
    assert (corpus_dir / "citers" / "smith-2020.json").exists()


def test_the_bridge_search_reads_the_store_instead_of_refetching(client, corpus_dir, stub_openalex, monkeypatch):
    """Catches the bridge search going back to the network for citers it
    already has on disk.

    Reusing the store was approved on 2026-09-23 (results are cached so
    the work is not redone each time) — it had been deliberately kept
    apart until then. The measured cost of the redo: 935 paginated requests and
    26.6 minutes per import, for data the citer store already held."""
    import bridges_api
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W2", "10.9/x"), _work("W3", "10.9/y")]]
    client.post("/api/paper/target-2020/citers/fetch")

    monkeypatch.setattr(bridges_api, "openalex_works_by",
                        lambda field, values, select: (
                            [{"id": "https://openalex.org/W1", "doi": "10.1/target",
                              "publication_year": 2020, "referenced_works": []}], 0))
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda wid: pytest.fail("refetched citers that were already stored"))
    payload = bridges_api.compute_bridges_now()
    assert payload["totals"]["citers_from_store"] == 1


def test_a_paper_with_nothing_stored_is_still_fetched(client, corpus_dir, monkeypatch):
    """Catches the opposite failure: treating a missing store as "nothing
    cites this". That would silently drop every bridge through a paper
    whose citers have not been fetched yet."""
    import bridges_api
    _summary(corpus_dir, "target-2020", "10.1/target")
    monkeypatch.setattr(bridges_api, "openalex_works_by",
                        lambda field, values, select: (
                            [{"id": "https://openalex.org/W1", "doi": "10.1/target",
                              "publication_year": 2020, "referenced_works": []}], 0))
    asked = []
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda wid: asked.append(wid) or ["W7"])
    payload = bridges_api.compute_bridges_now()
    assert asked == ["W1"], "a paper with no stored citers was skipped"
    assert payload["totals"]["citers_from_store"] == 0


def test_a_partial_store_is_refetched_rather_than_trusted(client, corpus_dir, stub_openalex, monkeypatch):
    """Catches an interrupted fetch being used as if it were the whole
    citer list — the bridge graph would come out short with nothing
    saying so, which is the failure mode this project keeps guarding
    against."""
    import bridges_api
    _summary(corpus_dir, "target-2020", "10.1/target")
    stub_openalex["pages"] = [[_work("W2", "10.9/a")], [_work("W3", "10.9/b")]]
    stub_openalex["fail_after"] = 1                       # stores page 1 only
    client.post("/api/paper/target-2020/citers/fetch")
    assert client.get("/api/paper/target-2020/citers").get_json()["complete"] is False

    monkeypatch.setattr(bridges_api, "openalex_works_by",
                        lambda field, values, select: (
                            [{"id": "https://openalex.org/W1", "doi": "10.1/target",
                              "publication_year": 2020, "referenced_works": []}], 0))
    asked = []
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda wid: asked.append(wid) or ["W2", "W3"])
    payload = bridges_api.compute_bridges_now()
    assert asked == ["W1"], "a partial citer list was trusted as complete"
    assert payload["totals"]["citers_from_store"] == 0


# ---------- 2026-09-22: whole-corpus backfill, busy guard ----------

def test_backfill_batches_lookups_and_skips_what_is_stored(corpus_dir, client, monkeypatch):
    """Catches three ways to waste the ~3,000-request budget: one lookup
    request per paper instead of batches, refetching papers already
    stored (the run would not be resumable), and aborting the whole run
    when one paper is missing from OpenAlex."""
    import citers
    _summary(corpus_dir, "a-2020", "10.1/a")
    _summary(corpus_dir, "b-2020", "10.1/b")
    _summary(corpus_dir, "gone-2020", "10.1/gone")
    _summary(corpus_dir, "done-2020", "10.1/done")
    (corpus_dir / "citers").mkdir(exist_ok=True)
    # A real stored list, for this paper's DOI: since 2026-09-25 a store
    # only counts as done when it was fetched for the current DOI.
    (corpus_dir / "citers" / "done-2020.json").write_text(json.dumps({
        "version": citers.CITERS_VERSION, "slug": "done-2020", "doi": "10.1/done",
        "fields": citers.FIELDS, "rows": [], "complete": True}))

    lookups = []

    def works_by(field, values, select):
        lookups.append(list(values))
        return [{"id": f"https://openalex.org/W{v[-1]}", "doi": v, "cited_by_count": 1}
                for v in values if v != "10.1/gone"], 0

    fetched = []
    monkeypatch.setattr(openalex_client, "openalex_works_by", works_by)
    monkeypatch.setattr(openalex_client, "openalex_citer_pages",
                        lambda wid, select=None: (fetched.append(wid) or iter([([], {"count": 0})])))
    counts = citers.backfill(None)

    assert len(lookups) == 1, "each paper was looked up with its own request"
    assert "10.1/done" not in lookups[0], "an already-stored paper was refetched"
    assert counts["stored"] == 2 and counts["not_found"] == 1 and counts["skipped"] == 1
    assert sorted(fetched) == ["Wa", "Wb"]


def test_citers_stored_for_a_different_doi_are_fetched_again(corpus_dir, client, monkeypatch):
    """Catches treating "a file exists" as "this paper's citers are
    stored". Taatgen 2013 first resolved to its supplement DOI; after a
    re-extract fixed the DOI, the supplement's citer list (moved along
    with the slug) was skipped as already done."""
    import citers
    _summary(corpus_dir, "taatgen-2013", "10.1037/a0033138")
    (corpus_dir / "citers").mkdir(exist_ok=True)
    (corpus_dir / "citers" / "taatgen-2013.json").write_text(json.dumps({
        "version": citers.CITERS_VERSION, "slug": "taatgen-2013",
        "doi": "10.1037/a0033138.supp", "fields": citers.FIELDS, "rows": [],
        "complete": True}))
    looked_up = []
    monkeypatch.setattr(openalex_client, "openalex_works_by",
                        lambda field, values, select: (looked_up.extend(values) or [], 0))
    counts = citers.backfill(["taatgen-2013"])
    assert looked_up == ["10.1037/a0033138"], "a store for another DOI was trusted"
    assert counts["skipped"] == 0


def test_a_per_paper_fetch_refuses_while_another_job_runs(client, corpus_dir):
    """Catches the collision: starting a citer fetch during an import
    used to write its steps INTO the import's banner."""
    import progress
    _summary(corpus_dir, "target-2020", "10.1/target")
    progress.start("Importing papers", ["Reading PDFs"])
    try:
        r = client.post("/api/paper/target-2020/citers/fetch")
        assert r.status_code == 409
        assert progress.snapshot()["job"] == "Importing papers"
    finally:
        progress.reset()


def test_the_corpus_backfill_starts_in_the_background(client, corpus_dir, monkeypatch):
    """Catches running ~3,000 requests inside the HTTP request (the app
    would hang for 20 minutes), and starting a second one on top."""
    import citers
    import progress
    progress.reset()
    started = []
    monkeypatch.setattr(citers, "backfill", lambda slugs=None, on_step=None, force=False:
                        started.append(slugs) or {})
    r = client.post("/api/citers/fetch-all")
    assert r.status_code == 202
    assert client.post("/api/citers/fetch-all").status_code in (202, 409)
    progress.reset()


def test_the_paper_panel_is_told_whether_citers_are_stored(client, corpus_dir, stub_openalex):
    """Catches the Coverage table's citer row going blind again: its
    OpenAlex cell reads `stores.citers` from /api/paper/<slug>. If the
    flag stops tracking the file, the row reads ✗ (or ✓) on every paper
    regardless of what is stored — the same staleness that was reported."""
    _summary(corpus_dir, "target-2020", "10.1/target")
    assert client.get("/api/paper/target-2020").get_json()["stores"]["citers"] is False
    stub_openalex["pages"] = [[_work("W2", "10.9/x")]]
    client.post("/api/paper/target-2020/citers/fetch")
    assert client.get("/api/paper/target-2020").get_json()["stores"]["citers"] is True


# ---------- 2026-09-24: the id index — only changed stores are read ----------

def _bridge_resolve_stub(monkeypatch, pairs):
    """Resolve each (doi, wid) with no references; the tests below are
    about where `backward` comes from, not the graph."""
    import bridges_api
    monkeypatch.setattr(bridges_api, "openalex_works_by",
                        lambda field, values, select: (
                            [{"id": f"https://openalex.org/{w}", "doi": d,
                              "publication_year": 2020, "referenced_works": []}
                             for d, w in pairs if d in values], 0))


def test_a_second_run_reads_no_unchanged_store(client, corpus_dir, stub_openalex, monkeypatch):
    """Catches the reported bug: "even tho it has most citers stored, it
    still loops through them." Every run parsed every store — ~0.6s a
    paper on the live corpus, ~10 minutes at 1,038 papers — to rebuild
    an answer that had not changed."""
    import bridges_api
    _summary(corpus_dir, "a-2020", "10.1/a")
    _summary(corpus_dir, "b-2020", "10.1/b")
    stub_openalex["pages"] = [[_work("W9", "10.9/x")]]
    client.post("/api/paper/a-2020/citers/fetch")
    client.post("/api/paper/b-2020/citers/fetch")
    _bridge_resolve_stub(monkeypatch, [("10.1/a", "W1"), ("10.1/b", "W2")])
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda wid: pytest.fail("refetched a stored paper"))

    first = bridges_api.compute_bridges_now()["totals"]
    assert first["citer_stores_read"] == 2 and first["citers_from_store"] == 2
    second = bridges_api.compute_bridges_now()["totals"]
    assert second["citer_stores_read"] == 0, "unchanged stores were parsed again"
    assert second["citers_from_store"] == 2, "the index lost papers it had"


def test_a_refetched_store_is_read_again(client, corpus_dir, stub_openalex, monkeypatch):
    """Catches the index going stale: a paper whose citers were refetched
    must contribute its NEW list, not the one cached before."""
    import os
    import bridges_api
    import citers as citers_mod
    _summary(corpus_dir, "a-2020", "10.1/a")
    stub_openalex["pages"] = [[_work("W9", "10.9/x")]]
    client.post("/api/paper/a-2020/citers/fetch")
    _bridge_resolve_stub(monkeypatch, [("10.1/a", "W1")])
    idx = corpus_dir / "bridges" / bridges_api.CITER_IDS_INDEX
    citers_mod.citer_ids_for(["a-2020"], idx)

    stub_openalex["pages"] = [[_work("W9", "10.9/x"), _work("W8", "10.9/y")]]
    client.post("/api/paper/a-2020/citers/fetch")
    p = citers_mod.citers_path("a-2020")
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))   # guarantee a new mtime
    got, read = citers_mod.citer_ids_for(["a-2020"], idx)
    assert read == 1 and got["a-2020"] == {"W9", "W8"}, "served the pre-refetch list"


def test_progress_counts_only_stores_actually_read(client, corpus_dir, stub_openalex, monkeypatch):
    """Catches the progress strip walking every paper again: on a run
    where nothing changed, the citer phase must report no per-paper
    steps at all rather than 1,038 "(stored)" lines."""
    import bridges_api
    _summary(corpus_dir, "a-2020", "10.1/a")
    stub_openalex["pages"] = [[_work("W9", "10.9/x")]]
    client.post("/api/paper/a-2020/citers/fetch")
    _bridge_resolve_stub(monkeypatch, [("10.1/a", "W1")])
    bridges_api.compute_bridges_now()                       # warms the index

    steps = []

    class Recorder:                      # stands in for the import's job handle
        def step(self, phase, detail="", done=0, total=0):
            steps.append((phase, detail))

        def finish(self, error=None):
            pass

    bridges_api.compute_bridges_now(job=Recorder())
    walked = [d for ph, d in steps if ph == bridges_api.BRIDGE_PHASES[1]]
    assert walked == [], f"the citer phase stepped through unchanged papers: {walked}"
