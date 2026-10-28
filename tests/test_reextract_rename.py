"""Re-extract must never strand a paper's highlights, projects or links.

2026-09-21, 16:18:46: Re-extract on `pan-2025-1`
resolved a canonical slug of `pan-2025` and renamed the PDF and
summary — only. 177 highlights, its project membership and every note
link stayed keyed to `pan-2025-1`, and the note workspace reported
"none of the pdfs are loading here". The data was repaired by hand.

These tests drive the real route with metadata extraction stubbed, so
they exercise the rename decision and the migration, not the network.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def stub_extract(monkeypatch):
    """Make re-extract resolve to a chosen canonical slug, offline."""
    import extract_api
    import extract_metadata as em
    import prefill_summary as ps

    state = {"canon": None, "doi": "10.1/x"}
    monkeypatch.setattr(em, "extract_metadata", lambda pdf: {"doi": state["doi"]})
    monkeypatch.setattr(ps, "canonical_slug_for", lambda meta: state["canon"])
    monkeypatch.setattr(ps, "render_summary",
                        lambda slug, pdf, existing_target=None, meta=None:
                        f"---\ntitle: T\ndoi: {state['doi']}\npdf_link: papers/{slug}.pdf\n---\n")
    monkeypatch.setattr(extract_api, "_kick_enrichment", lambda slug: None)
    return state


def _seed(corpus_dir, slug):
    for sub in ("papers", "summaries", "highlights", "pdf_refs", "projects", "notes"):
        (corpus_dir / sub).mkdir(exist_ok=True)
    (corpus_dir / "papers" / f"{slug}.pdf").write_bytes(b"%PDF-1.4 stub")
    (corpus_dir / "summaries" / f"{slug}.md").write_text("---\ntitle: T\n---\n")
    (corpus_dir / "highlights" / f"{slug}.json").write_text(json.dumps({"highlights": [{"id": "h1"}]}))
    (corpus_dir / "pdf_refs" / f"{slug}.json").write_text("{}")
    (corpus_dir / "projects" / "p1.json").write_text(json.dumps({
        "id": "p1", "title": "Prelims", "members": {"paper": [slug, "other-2020"], "note": []}}))
    (corpus_dir / "notes" / "n1.json").write_text(json.dumps({
        "id": "n1", "title": "N",
        "body_html": f'<a data-open-paper="{slug}">x</a> <a data-open-paper="{slug}-9">y</a>'}))


def test_a_suffix_only_difference_never_renames(client, corpus_dir, stub_extract):
    """Catches re-introducing the rename that orphaned pan-2025-1.

    The canonical slug differs only by the collision suffix. Dropping it
    is cosmetic, and it changed the identity of a paper with 177
    highlights and a live note linking to it."""
    _seed(corpus_dir, "pan-2025-1")
    stub_extract["canon"] = "pan-2025"
    r = client.post("/api/paper/pan-2025-1/re-extract")
    assert r.status_code == 200
    assert r.get_json()["renamed"] is False
    assert (corpus_dir / "papers" / "pan-2025-1.pdf").exists()
    assert not (corpus_dir / "papers" / "pan-2025.pdf").exists()
    assert (corpus_dir / "highlights" / "pan-2025-1.json").exists()


def test_a_real_rename_carries_every_slug_keyed_store(client, corpus_dir, stub_extract):
    """Catches renaming the PDF and summary and nothing else.

    An `unknown-2020` placeholder resolving to `smith-2020` is a genuine
    rename. Highlights, project membership and note links must follow,
    and the cached reference list must not survive under the old name."""
    _seed(corpus_dir, "unknown-2020")
    stub_extract["canon"] = "smith-2020"
    r = client.post("/api/paper/unknown-2020/re-extract")
    body = r.get_json()
    assert body["renamed"] is True and body["slug"] == "smith-2020"

    assert (corpus_dir / "papers" / "smith-2020.pdf").exists()
    assert (corpus_dir / "highlights" / "smith-2020.json").exists()
    assert not (corpus_dir / "highlights" / "unknown-2020.json").exists()
    assert not (corpus_dir / "pdf_refs" / "unknown-2020.json").exists()

    proj = json.loads((corpus_dir / "projects" / "p1.json").read_text())
    assert proj["members"]["paper"] == ["smith-2020", "other-2020"]

    note = json.loads((corpus_dir / "notes" / "n1.json").read_text())["body_html"]
    assert 'data-open-paper="smith-2020"' in note


def test_note_links_to_a_longer_slug_are_left_alone(client, corpus_dir, stub_extract):
    """Catches a prefix match in the note rewrite.

    Renaming `unknown-2020` must not touch a link to `unknown-2020-9` —
    the same shape as `pan-2025` versus `pan-2025-1`."""
    _seed(corpus_dir, "unknown-2020")
    stub_extract["canon"] = "smith-2020"
    client.post("/api/paper/unknown-2020/re-extract")
    note = json.loads((corpus_dir / "notes" / "n1.json").read_text())["body_html"]
    assert 'data-open-paper="unknown-2020-9"' in note


def test_migration_refuses_to_merge_highlights_into_an_existing_file(corpus_dir, client):
    """Catches overwriting one paper's highlights with another's."""
    from slug_migration import migrate_paper_slug
    (corpus_dir / "highlights").mkdir(exist_ok=True)
    (corpus_dir / "highlights" / "a-2020.json").write_text('{"highlights":[{"id":"A"}]}')
    (corpus_dir / "highlights" / "b-2020.json").write_text('{"highlights":[{"id":"B"}]}')
    counts = migrate_paper_slug("a-2020", "b-2020")
    assert counts["highlights"] == 0
    assert "B" in (corpus_dir / "highlights" / "b-2020.json").read_text()
    assert (corpus_dir / "highlights" / "a-2020.json").exists()
