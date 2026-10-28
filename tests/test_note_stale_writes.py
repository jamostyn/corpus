"""A note edited in two windows must never lose the newer edits.

Bug (2026-09-28): edits made to a note in the popped-out window were not
visible in the notes page after the pop-out was closed.

server.log showed the pop-out's saves landing (11,385 chars), then two
saves of 11,374 chars — the exact length the note had before it popped
out — from the main window, which on unlock re-showed its old in-memory
copy and autosaved it over the newer work. Two layers now stop that, and
each is pinned here:

  1. the server refuses a save edited from an older revision;
  2. the main window reloads the note from disk when a pop-out closes.
"""
from __future__ import annotations

import json
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"


def _new_note(client, body="<p>v1</p>"):
    nid = client.post("/api/notes", json={"title": "Prelims Paper Table"}).get_json()["id"]
    r = client.put(f"/api/note/{nid}", json={"body_html": body, "base_revision": 0})
    assert r.status_code == 200
    return nid, r.get_json()["revision"]


def test_a_save_from_an_older_copy_is_refused_not_written(client, corpus_dir):
    """Catches the reported data loss: window A (the pop-out) saves newer
    work; window B still holds the copy it loaded before, and its save
    must be refused — the newer text stays on disk."""
    nid, rev = _new_note(client)
    # Window A, up to date, saves the new work.
    a = client.put(f"/api/note/{nid}", json={"body_html": "<p>new work</p>", "base_revision": rev})
    assert a.status_code == 200
    # Window B still thinks the note is at `rev`.
    b = client.put(f"/api/note/{nid}", json={"body_html": "<p>old copy</p>", "base_revision": rev})
    assert b.status_code == 409 and b.get_json()["error"] == "stale"
    on_disk = json.loads((corpus_dir / "notes" / f"{nid}.json").read_text())
    assert "new work" in on_disk["body_html"] and "old copy" not in on_disk["body_html"]


def test_consecutive_saves_from_one_editor_are_accepted(client, corpus_dir):
    """Catches the guard refusing the editor's OWN next save — every
    autosave after the first would then fail."""
    nid, rev = _new_note(client)
    for i in range(3):
        r = client.put(f"/api/note/{nid}", json={"body_html": f"<p>{i}</p>", "base_revision": rev})
        assert r.status_code == 200
        rev = r.get_json()["revision"]
    assert rev == 4


def test_keep_mine_overwrites_only_when_asked(client, corpus_dir):
    """Catches the conflict being a dead end: the user's explicit "Keep
    mine" must still be able to save."""
    nid, rev = _new_note(client)
    client.put(f"/api/note/{nid}", json={"body_html": "<p>other window</p>", "base_revision": rev})
    r = client.put(f"/api/note/{nid}",
                   json={"body_html": "<p>mine</p>", "base_revision": rev, "force": True})
    assert r.status_code == 200 and "mine" in r.get_json()["body_html"]


def test_the_editor_sends_its_revision_with_every_save():
    """Catches the client dropping `base_revision`: the server then has
    nothing to compare and accepts any stale save, which is the old bug."""
    notes = (_SRC / "notes.js").read_text(encoding="utf-8")
    payload = notes[notes.index("const payloadNow"):]
    payload = payload[:payload.index("});")]
    assert "base_revision: baseRevision" in payload
    assert "if (e.status === 409) { _showConflict(); return; }" in notes


def test_closing_a_pop_out_reloads_the_note_in_the_main_window():
    """Catches the unlock path re-drawing from memory. `renderNoteDetail`
    draws `state.noteDetail`, which is the copy from before the pop-out;
    the unlock must go through `selectNote`, which fetches from disk."""
    app = (_SRC / "app.js").read_text(encoding="utf-8")
    fn = app[app.index("function _afterDetachChange("):]
    fn = fn[:fn.index("\n}\n")]
    note_branch = fn[fn.index('kind === "note"'):]
    note_branch = note_branch[:note_branch.index("\n  }")]
    assert "else selectNote(id);" in note_branch
