"""End-to-end round-trip for paper-detail deep-links.

The paper-detail endpoint returns a `link_keys` block with canonical
keys for the journal, each author, and each per-author institution.
These keys must ALWAYS match what `/api/journal/<key>`,
`/api/author/<key>`, and `/api/institution/<key>` accept — otherwise
clicking a link on paper detail 404s.

This test writes a tiny fixture summary to the scratch corpus, fetches
paper detail, then uses each returned key to hit the corresponding
entity endpoint. If either side of the key computation drifts, one
of the follow-up requests 404s and the test fails.
"""
from __future__ import annotations


_FIXTURE_MD = """---
author: Kahneman, D.
authors_full: [Kahneman D., Tversky A.]
authors_detailed:
  - {family: Kahneman, given: "Daniel", institutions: ["Princeton University"]}
  - {family: Tversky,  given: "Amos",   institutions: ["Stanford University"]}
year: 1979
title: "Prospect Theory: An Analysis of Decision under Risk"
kind: article
publisher: "Econometric Society"
doi: 10.2307/1914185
schema_version: 1
---

Body text goes here.
"""


def test_paper_link_keys_round_trip(client, corpus_dir):
    slug = "kahneman-1979"
    (corpus_dir / "summaries" / f"{slug}.md").write_text(_FIXTURE_MD)

    r = client.get(f"/api/paper/{slug}")
    assert r.status_code == 200
    body = r.get_json()
    lk = body.get("link_keys") or {}

    # Shape.
    assert "journal" in lk
    assert lk["journal"], "journal key should be non-empty for a real publisher"
    assert isinstance(lk.get("authors_detailed"), list)
    assert isinstance(lk.get("authors_detailed_insts"), list)
    assert len(lk["authors_detailed"]) == 2
    assert len(lk["authors_detailed_insts"]) == 2

    # Journal key resolves.
    r = client.get(f"/api/journal/{lk['journal']}")
    assert r.status_code == 200, (
        f"journal key {lk['journal']!r} produced by paper-detail was rejected "
        f"by /api/journal/<key>. The frontend/backend key computation has drifted."
    )
    assert r.get_json()["name"] == "Econometric Society"

    # Each author key resolves.
    for i, akey in enumerate(lk["authors_detailed"]):
        r = client.get(f"/api/author/{akey}")
        assert r.status_code == 200, (
            f"author key {akey!r} (index {i}) was rejected by /api/author/<key>"
        )

    # Each institution key resolves.
    for i, insts in enumerate(lk["authors_detailed_insts"]):
        for j, ikey in enumerate(insts):
            r = client.get(f"/api/institution/{ikey}")
            assert r.status_code == 200, (
                f"institution key {ikey!r} (author {i}, inst {j}) was rejected "
                f"by /api/institution/<key>"
            )


def test_paper_link_keys_absent_publisher_yields_empty_key(client, corpus_dir):
    """`publisher: unknown` should produce an empty journal key so
    paper-detail can render the value as plain text (no dead link)."""
    slug = "unknown-2020"
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        _FIXTURE_MD.replace("Econometric Society", "unknown")
    )
    r = client.get(f"/api/paper/{slug}")
    assert r.status_code == 200
    assert r.get_json()["link_keys"]["journal"] == ""
