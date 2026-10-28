"""Aggregator structural snapshot.

Guards `_aggregate_authors` / `_aggregate_institutions` / `_aggregate_journals`
+ their detail endpoints against silent drift during refactors.

Not byte-for-byte — asserts the invariants that matter (record count,
key format, per-record shape, cross-aggregator consistency). A refactor
that changes any of these should be intentional.
"""
from __future__ import annotations


# Two authors, two institutions across two papers with the same
# publisher/ISSN — exercises the "same journal aggregates" and
# "same author appears in two papers" paths on all three aggregators.
_PAPER_A = """---
author: Kahneman, D.
authors_full: [Kahneman D., Tversky A.]
authors_detailed:
  - {family: Kahneman, given: "Daniel", institutions: ["Princeton University"]}
  - {family: Tversky,  given: "Amos",   institutions: ["Stanford University"]}
year: 1979
title: "Prospect Theory: An Analysis of Decision under Risk"
kind: article
publisher: "Econometric Society"
issn: [0012-9682]
doi: 10.2307/1914185
schema_version: 1
---

Body.
"""

_PAPER_B = """---
author: Tversky, A.
authors_full: [Tversky A., Kahneman D.]
authors_detailed:
  - {family: Tversky,  given: "Amos",    institutions: ["Stanford University"]}
  - {family: Kahneman, given: "Daniel",  institutions: ["Princeton University"]}
year: 1981
title: "The Framing of Decisions and the Psychology of Choice"
kind: article
publisher: "American Association for the Advancement of Science"
issn: [0036-8075]
doi: 10.1126/science.7455683
schema_version: 1
---

Body.
"""


def _seed(corpus_dir):
    (corpus_dir / "summaries" / "kahneman-1979.md").write_text(_PAPER_A)
    (corpus_dir / "summaries" / "tversky-1981.md").write_text(_PAPER_B)


def test_aggregate_authors_shape(client, corpus_dir):
    _seed(corpus_dir)
    import entities_api
    a = entities_api._aggregate_authors()

    # Same two authors appear on both papers → 2 aggregate records, each
    # with 2 paper contributions.
    assert set(a.keys()) == {"kahneman-daniel", "tversky-amos"}
    kd = a["kahneman-daniel"]
    assert kd["family"] == "Kahneman"
    assert kd["given"]  == "Daniel"
    assert len(kd["papers"]) == 2
    assert sorted(p["slug"] for p in kd["papers"]) == ["kahneman-1979", "tversky-1981"]
    # Institution accretion — Princeton for Kahneman.
    assert any(i["name"] == "Princeton University" for i in kd["institutions"])


def test_aggregate_institutions_shape(client, corpus_dir):
    _seed(corpus_dir)
    import entities_api
    inst = entities_api._aggregate_institutions()

    # Two distinct institutions across the two papers, keyed by name-slug
    # (no ROR in fixture data).
    assert set(inst.keys()) == {"princeton-university", "stanford-university"}
    princeton = inst["princeton-university"]
    assert princeton["name"] == "Princeton University"
    # Both papers referenced Princeton (through Kahneman).
    assert sorted(p["slug"] for p in princeton["papers"]) == \
           ["kahneman-1979", "tversky-1981"]
    # Kahneman is Princeton's author.
    assert any(a["key"] == "kahneman-daniel" for a in princeton["authors"])


def test_aggregate_journals_shape(client, corpus_dir):
    _seed(corpus_dir)
    import entities_api
    j = entities_api._aggregate_journals()

    # Two distinct journals — Econometric Society (Prospect Theory paper)
    # and AAAS (Framing paper). Keyed by ISSN.
    assert set(j.keys()) == {"issn-0012-9682", "issn-0036-8075"}
    es = j["issn-0012-9682"]
    assert es["name"] == "Econometric Society"
    assert "0012-9682" in es["issns"]
    assert len(es["papers"]) == 1
    assert es["papers"][0]["slug"] == "kahneman-1979"


def test_aggregate_journals_skips_unknown_publisher(client, corpus_dir):
    """Papers with `publisher: unknown` are excluded from the journal
    aggregate — otherwise `_journal_key("unknown", [])` would create a
    dumping-ground record."""
    _seed(corpus_dir)
    (corpus_dir / "summaries" / "ghost-2000.md").write_text(
        _PAPER_A.replace("Econometric Society", "unknown").replace("kahneman-1979", "ghost-2000")
    )
    import entities_api
    j = entities_api._aggregate_journals()
    for key, rec in j.items():
        assert (rec["name"] or "").lower() != "unknown"


def test_detail_endpoints_all_three_shapes(client, corpus_dir):
    """Ensures the enrichable-detail wrapping is consistent across the
    three endpoints. Guards audit A2 (three near-identical detail
    endpoints).
    """
    _seed(corpus_dir)

    r = client.get("/api/author/kahneman-daniel")
    assert r.status_code == 200
    body = r.get_json()
    assert body["key"]    == "kahneman-daniel"
    assert body["family"] == "Kahneman"

    r = client.get("/api/institution/princeton-university")
    assert r.status_code == 200
    body = r.get_json()
    assert body["key"]  == "princeton-university"
    assert body["name"] == "Princeton University"

    r = client.get("/api/journal/issn-0012-9682")
    assert r.status_code == 200
    body = r.get_json()
    assert body["key"]  == "issn-0012-9682"
    assert body["name"] == "Econometric Society"


def test_detail_endpoints_404_on_unknown_key(client, corpus_dir):
    _seed(corpus_dir)
    for path in (
        "/api/author/does-not-exist",
        "/api/institution/does-not-exist",
        "/api/journal/does-not-exist",
    ):
        r = client.get(path)
        assert r.status_code == 404, f"{path} should 404, got {r.status_code}"


# ---------- Post-aggregation display-based dedup ----------


_DUP_YI_A = """---
author: Yi, Han Gyol
authors_full: [Yi H.G.]
authors_detailed:
  - {family: Yi, given: "Han Gyol", institutions: ["The University of Texas at Austin"]}
year: 2023
title: "A paper by Yi Han Gyol (variant A)"
kind: article
publisher: "Journal One"
schema_version: 1
---

Body.
"""

_DUP_YI_B = """---
author: Yi, HanGyol
authors_full: [Yi H.]
authors_detailed:
  - {family: Yi, given: "HanGyol", institutions: ["The University of Texas at Austin"]}
year: 2024
title: "A paper by Yi Han Gyol (variant B)"
kind: article
publisher: "Journal Two"
schema_version: 1
---

Body.
"""


def test_author_dedupe_merges_display_variants(client, corpus_dir):
    """Two summaries with the SAME PERSON (identical family + same
    institution) but slightly different `given` (whitespace variant)
    used to produce two distinct author records because
    `_author_key` uses only the first token of `given`. The
    post-aggregation `_merge_authors_by_display` step catches this
    and merges into one record. Guards the 2026-08-16 fix."""
    (corpus_dir / "summaries" / "yi-2023.md").write_text(_DUP_YI_A)
    (corpus_dir / "summaries" / "yi-2024.md").write_text(_DUP_YI_B)
    import entities_api
    authors = entities_api._aggregate_authors()

    # Exactly ONE Yi record — not two.
    yi_keys = [k for k, a in authors.items() if a["family"] == "Yi"]
    assert len(yi_keys) == 1, (
        f"expected one Yi record after display-dedup, got {len(yi_keys)}: {yi_keys}"
    )
    yi = authors[yi_keys[0]]
    # Both papers merged into this author's papers list.
    assert sorted(p["slug"] for p in yi["papers"]) == ["yi-2023", "yi-2024"]
    # Institution preserved (both papers had UT Austin).
    assert any(i["name"] == "The University of Texas at Austin" for i in yi["institutions"])


_DUP_YI_DIFF_INST = """---
author: Yi, HanGyol
authors_full: [Yi H.]
authors_detailed:
  - {family: Yi, given: "HanGyol", institutions: ["Stanford University"]}
year: 2024
title: "A DIFFERENT Yi Han Gyol at Stanford"
kind: article
publisher: "Journal Three"
schema_version: 1
---
"""


def test_author_dedupe_institution_guard(client, corpus_dir):
    """The display-dedup should NOT merge two same-named authors at
    different institutions. `_author_key` produces "yi-han" for
    "Han Gyol" and "yi-hangyol" for "HanGyol", so without any
    dedup the aggregator gives two records — safe default. With
    dedup + institution guard we keep those two separate whenever
    they're at different universities (guards against name
    collisions between distinct researchers)."""
    (corpus_dir / "summaries" / "yi-utaustin.md").write_text(_DUP_YI_A)
    (corpus_dir / "summaries" / "yi-stanford.md").write_text(_DUP_YI_DIFF_INST)
    import entities_api
    authors = entities_api._aggregate_authors()
    yi_keys = [k for k, a in authors.items() if a["family"] == "Yi"]
    assert len(yi_keys) == 2, (
        f"expected two separate Yi records (different institutions), "
        f"got {len(yi_keys)}: {yi_keys}"
    )
