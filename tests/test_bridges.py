"""Citation bridges — indirect connections between corpus papers.

Jack, 2026-09-17: "check for bridges between papers in the corpus …
the shortest paper connection … how long the bridge is between those
connections, and the title and some basic information about the
connecting papers."

A bridge is A -> M -> B where A and B are both in the corpus and M is
not. Found by MEETING IN THE MIDDLE: intersect A's references with the
works that cite B. Measured on the real corpus, walking outward from A
instead costs 64 requests and 18.4s for one pair and usually finds
nothing; the intersection answers every pair at once for ~70 requests.

**No test here touches the network.** `openalex_client` is monkeypatched
throughout. CLAUDE.md forbids live API calls in tests, and a bridge
suite is exactly where that rule is easiest to break by accident.
"""
from __future__ import annotations

import json

import pytest

from bridges import Bridge, bridges_for, find_bridges


# ---------- the graph logic (pure) ----------

def test_a_shared_middle_paper_is_a_bridge():
    """Catches: the intersection being computed in the wrong direction.

    `forward` holds what A CITES; `backward` holds what CITES B. The
    bridge is their overlap. Intersecting forward with forward, or
    backward with backward, still yields plausible-looking output on
    symmetric fixtures — this one is asymmetric on purpose."""
    fwd = {"new-2020": {"M1", "M2", "X9"}}
    back = {"old-2005": {"M2", "Z8"}}
    got = find_bridges(fwd, back, years={"new-2020": 2020, "old-2005": 2005})
    assert [(b.src, b.dst, b.hops, b.middles) for b in got] == \
           [("new-2020", "old-2005", 2, ["M2"])]


def test_no_shared_middle_is_not_a_bridge():
    """Catches: reporting a pair whenever both sides are non-empty."""
    fwd = {"a-2020": {"M1"}}
    back = {"b-2005": {"M2"}}
    assert find_bridges(fwd, back, years={"a-2020": 2020, "b-2005": 2005}) == []


def test_a_directly_citing_pair_is_not_reported_as_a_bridge():
    """Catches: duplicating a link the panel already shows.

    The connections block renders direct citations separately. A pair
    appearing in both reads as two different findings about the same
    relationship."""
    fwd = {"a-2020": {"M1"}}
    back = {"b-2005": {"M1"}}
    y = {"a-2020": 2020, "b-2005": 2005}
    assert find_bridges(fwd, back, years=y), "fixture should bridge without the direct set"
    assert find_bridges(fwd, back, direct={("a-2020", "b-2005")}, years=y) == []


def test_a_pair_is_only_oriented_newer_to_older():
    """Catches: emitting both orderings of the same pair.

    A citation points backwards in time, so an older paper citing a
    newer one is impossible, not merely absent. Emitting it would
    double every result and imply a relationship that cannot exist."""
    fwd = {"old-2005": {"M1"}, "new-2020": {"M1"}}
    back = {"old-2005": {"M1"}, "new-2020": {"M1"}}
    got = find_bridges(fwd, back, years={"old-2005": 2005, "new-2020": 2020})
    assert [(b.src, b.dst) for b in got] == [("new-2020", "old-2005")]


def test_unknown_years_do_not_silently_drop_a_pair():
    """Catches: treating a missing year as "older" (or as 0).

    Some summaries have no parseable year. Orientation is a
    presentation nicety; dropping a real connection because a year is
    absent loses data the user cannot get back."""
    fwd = {"a": {"M1"}, "b": {"M1"}}
    back = {"a": {"M1"}, "b": {"M1"}}
    got = find_bridges(fwd, back, years={})
    assert {(b.src, b.dst) for b in got} == {("a", "b"), ("b", "a")}

    # The case that actually bites: ONE year known. Writing the guard
    # as `(ya or 0) < (yb or 0)` treats a missing year as 0, so an
    # unknown-year source is judged older than everything and every
    # bridge from it is discarded.
    half = find_bridges(fwd, back, years={"a": None, "b": 2010})
    assert ("a", "b") in {(x.src, x.dst) for x in half}, (
        "a pair was dropped because the source year is unknown")


def test_middles_are_capped_per_pair():
    """Catches: shipping an unbounded list into the panel.

    A heavily-cited pair can share hundreds of middle papers. The cap
    keeps both the cached payload and the rendered list finite."""
    from bridges import MAX_MIDDLES_PER_PAIR
    many = {f"M{i}" for i in range(MAX_MIDDLES_PER_PAIR + 40)}
    got = find_bridges({"a": many}, {"b": many}, years={"a": 2020, "b": 2000})
    assert len(got[0].middles) == MAX_MIDDLES_PER_PAIR


def test_stronger_bridges_sort_first():
    """Catches: arbitrary ordering. Sharing five middle papers is a
    stronger signal than sharing one, and the panel shows the top of
    the list."""
    # The WEAK pair must come first alphabetically, so insertion order
    # is [1, 3] and only a real sort produces [3, 1]. An earlier
    # fixture had the strong pair first, which meant deleting the sort
    # entirely still passed.
    fwd = {"a": {"M9"}, "c": {"M1", "M2", "M3"}}
    back = {"b": {"M9"}, "d": {"M1", "M2", "M3"}}
    y = {"a": 2020, "b": 2000, "c": 2020, "d": 2000}
    got = find_bridges(fwd, back, years=y)
    assert [(b.src, len(b.middles)) for b in got] == [("c", 3), ("a", 1)]


# ---------- per-paper view ----------

def test_a_paper_sees_bridges_from_both_ends():
    """Catches: showing only bridges where this paper is the source.

    The panel asks "what is this connected to", which has no direction.
    Storing one row per ordered pair and flipping on read is what keeps
    the same fact from being stored twice."""
    rows = [Bridge("new", "old", 2, ["M1"]).as_dict()]
    assert [(r["other"], r["direction"]) for r in bridges_for("new", rows)] == \
           [("old", "cites-via")]
    assert [(r["other"], r["direction"]) for r in bridges_for("old", rows)] == \
           [("new", "cited-via")]
    assert bridges_for("unrelated", rows) == []


# ---------- endpoints (network stubbed) ----------

def _summary(corpus_dir, slug, doi, year=2020):
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        f"---\ntitle: {slug}\nyear: {year}\nauthor: T, A.\ndoi: {doi}\n---\n\n## References\n",
        encoding="utf-8")


@pytest.fixture
def stub_oa(monkeypatch):
    """Stand in for every OpenAlex call. Returns the installed maps so a
    test can shape the graph."""
    import bridges_api
    refs = {}      # short id -> referenced works
    citers = {}    # short id -> citer ids
    meta = {}      # short id -> display fields
    doi_to_id = {}

    # Returns (results, lookup_failures) — the real signature since
    # 2026-09-21. `fail_n` lets a test simulate a dropped chunk, which
    # is the failure that silently built a bridge graph on 80% of the
    # corpus.
    state = {"fail_n": 0}

    def works_by(field, values, select):
        if field == "doi":
            rows = [{"id": f"https://openalex.org/{doi_to_id[d]}", "doi": d,
                     "publication_year": 2020,
                     "referenced_works": [f"https://openalex.org/{r}"
                                          for r in refs.get(doi_to_id[d], [])]}
                    for d in values if d in doi_to_id]
            return rows, state["fail_n"]
        return ([{"id": f"https://openalex.org/{v}", **meta.get(v, {})}
                 for v in values if v in meta], 0)

    monkeypatch.setattr(bridges_api, "openalex_works_by", works_by)
    # Default [] = "nothing cites it". An explicit None means the
    # lookup FAILED. The real client draws exactly this distinction,
    # and a stub that returns None for anything unset would make every
    # paper look like a network error.
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda wid: citers.get(wid, []))
    return {"refs": refs, "citers": citers, "meta": meta,
            "doi_to_id": doi_to_id, "state": state}


def test_get_bridges_before_computing_says_so(client, corpus_dir):
    """Catches: an uncomputed cache rendering as "no connections".

    Those are completely different claims — one means we have not
    looked. Conflating them tells the user a paper is unconnected when
    nothing has been checked."""
    r = client.get("/api/bridges").get_json()
    assert r["computed_at"] is None
    assert r["bridges"] == []


def test_paper_detail_never_triggers_the_network(client, corpus_dir, monkeypatch):
    """Catches: computing bridges on the paper-detail path.

    That path runs on every sidebar click. A ~40s network call there
    would make the whole app feel broken, and would hit OpenAlex once
    per click."""
    import bridges_api
    called = []
    monkeypatch.setattr(bridges_api, "openalex_works_by",
                        lambda *a, **k: called.append(1) or [])
    monkeypatch.setattr(bridges_api, "openalex_citers_of",
                        lambda *a, **k: called.append(1) or [])
    _summary(corpus_dir, "a-2020", "10.1000/aaa")
    d = client.get("/api/paper/a-2020").get_json()
    assert called == [], "paper detail hit the network"
    assert d["bridges"]["computed"] is False


def test_compute_then_read_round_trip(client, corpus_dir, stub_oa):
    """Catches: the cache not being written, or not being readable.

    The whole design rests on compute-once / read-many; if the write
    or the read is broken the button appears to do nothing."""
    _summary(corpus_dir, "new-2020", "10.1000/aaa", 2020)
    _summary(corpus_dir, "old-2005", "10.1000/bbb", 2005)
    stub_oa["doi_to_id"].update({"10.1000/aaa": "W1", "10.1000/bbb": "W2"})
    stub_oa["refs"]["W1"] = ["M1", "M7"]
    stub_oa["citers"]["W2"] = ["M1"]
    stub_oa["meta"]["M1"] = {"title": "The Middle Paper", "publication_year": 2012,
                             "cited_by_count": 99, "doi": "10.1000/mid"}

    res = client.post("/api/bridges/compute").get_json()
    assert res["totals"]["bridges"] == 1
    assert res["totals"]["citers_failed"] == 0

    got = client.get("/api/bridges").get_json()
    assert got["computed_at"] and got["stale"] is False
    assert got["bridges"][0]["middles"] == ["M1"]
    assert got["middles"]["M1"]["title"] == "The Middle Paper"

    d = client.get("/api/paper/new-2020").get_json()["bridges"]
    assert d["computed"] is True
    assert d["rows"][0]["other"] == "old-2005"
    assert d["rows"][0]["hops"] == 2
    assert d["middles"]["M1"]["cited_by"] == 99


def test_a_failed_citer_lookup_is_reported_not_swallowed(client, corpus_dir, stub_oa):
    """Catches: treating a network failure as "nothing cites it".

    Both produce zero bridges. Only one of them means the answer is
    wrong, and the user has to be able to tell."""
    _summary(corpus_dir, "a-2020", "10.1000/aaa", 2020)
    stub_oa["doi_to_id"]["10.1000/aaa"] = "W1"
    stub_oa["refs"]["W1"] = ["M1"]
    stub_oa["citers"]["W1"] = None          # network failure

    res = client.post("/api/bridges/compute").get_json()
    assert res["totals"]["citers_failed"] == 1


def test_changing_the_corpus_marks_the_cache_stale(client, corpus_dir, stub_oa):
    """Catches: a cache that never admits it is out of date.

    Adding a paper can create bridges the cached answer does not have.
    Auto-recomputing would put a 40s network call behind a page load,
    so the panel says "stale" instead — but only if this flag works."""
    _summary(corpus_dir, "a-2020", "10.1000/aaa", 2020)
    stub_oa["doi_to_id"]["10.1000/aaa"] = "W1"
    stub_oa["refs"]["W1"] = ["M1"]
    stub_oa["citers"]["W1"] = []
    client.post("/api/bridges/compute")
    assert client.get("/api/bridges").get_json()["stale"] is False

    _summary(corpus_dir, "b-2001", "10.1000/bbb", 2001)
    assert client.get("/api/bridges").get_json()["stale"] is True


def test_a_corpus_with_no_resolvable_dois_fails_loudly(client, corpus_dir, stub_oa):
    """Catches: returning an empty success for a corpus that cannot be
    bridged at all. "0 bridges" would read as "no connections exist"
    rather than "none of your papers have a DOI"."""
    _summary(corpus_dir, "a-2020", "unknown", 2020)
    r = client.post("/api/bridges/compute")
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_resolvable_papers"


def test_a_corrupt_cache_does_not_break_paper_detail(client, corpus_dir):
    """Catches: an unguarded json.loads on the hot path.

    The cache is a plain file in the user's corpus dir. A truncated
    write or a hand-edit must not take out every paper view."""
    from _paths import bridges_dir
    _summary(corpus_dir, "a-2020", "10.1000/aaa")
    (bridges_dir() / "index.json").write_text("{not json", encoding="utf-8")
    d = client.get("/api/paper/a-2020")
    assert d.status_code == 200
    assert d.get_json()["bridges"]["computed"] is False

    # And the endpoint itself. `bridges_for_slug` wraps its own read in
    # a try/except, so paper detail survived a corrupt cache even
    # without the guard inside `_read_cache` — this is the assertion
    # that actually pins it.
    g = client.get("/api/bridges")
    assert g.status_code == 200, "GET /api/bridges 500s on a corrupt cache"
    assert g.get_json()["computed_at"] is None


def test_a_cache_from_an_older_format_is_discarded(client, corpus_dir):
    """Catches: reading a payload whose shape has since changed.

    Half-trusting an old cache produces wrong output rather than a
    missing one, which is much harder to notice."""
    from _paths import bridges_dir
    _summary(corpus_dir, "a-2020", "10.1000/aaa")
    (bridges_dir() / "index.json").write_text(
        json.dumps({"version": 0, "bridges": [{"src": "a-2020", "dst": "x",
                                               "hops": 2, "middles": ["M1"]}]}),
        encoding="utf-8")
    assert client.get("/api/bridges").get_json()["computed_at"] is None
    assert client.get("/api/paper/a-2020").get_json()["bridges"]["computed"] is False


def test_a_failed_lookup_is_not_reported_as_unresolved(client, corpus_dir, stub_oa):
    """Catches: conflating "OpenAlex has no record" with "the request
    failed".

    On 2026-09-21 a bridge run over a 257-paper corpus resolved 206 and
    reported 51 as `papers_unresolved`, which reads as a data gap.
    Re-running the identical lookup resolved all 256 — a chunk had been
    dropped. The graph was built on 80% of the corpus and every number
    in the response looked reasonable.

    The two must be separate fields, because only one of them means the
    answer is wrong."""
    _summary(corpus_dir, "a-2020", "10.1000/aaa")
    stub_oa["doi_to_id"]["10.1000/aaa"] = "W1"
    stub_oa["refs"]["W1"] = []
    stub_oa["citers"]["W1"] = []
    stub_oa["state"]["fail_n"] = 50          # a dropped chunk

    t = client.post("/api/bridges/compute").get_json()["totals"]
    assert t["lookup_failures"] == 50
    assert t["complete"] is False
    assert t["papers_unresolved"] == 0, (
        "a lookup failure was counted as OpenAlex not having the paper")


def test_a_clean_run_is_marked_complete(client, corpus_dir, stub_oa):
    """Catches: `complete` hard-coded False, which would make the flag
    useless — every run would look suspect and nobody would read it."""
    _summary(corpus_dir, "a-2020", "10.1000/aaa")
    stub_oa["doi_to_id"]["10.1000/aaa"] = "W1"
    stub_oa["refs"]["W1"] = []
    stub_oa["citers"]["W1"] = []

    t = client.post("/api/bridges/compute").get_json()["totals"]
    assert t["lookup_failures"] == 0
    assert t["complete"] is True


def test_the_ui_distinguishes_an_incomplete_result_from_a_sparse_one():
    """Catches: reporting a lost-chunk run as a normal success.

    "206 bridges found" is what a 20%-short graph said. The user has no
    way to tell that from a genuine 206 unless the toast says so and
    tells them to run it again."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "src" / "paper-detail.js").read_text(encoding="utf-8")
    fn = src[src.index("async function findBridges("):src.index("async function reExtract(")]
    body = "\n".join(l for l in fn.split("\n") if not l.strip().startswith("//"))
    assert "lookup_failures" in body, "the toast ignores lost lookups"
    assert "t.complete === false" in body, "the toast ignores the completeness flag"
    assert re.search(r'"err"', body), "an incomplete result must not render as success"
