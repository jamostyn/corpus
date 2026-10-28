"""Round-trip a note through the HTTP surface.

Covers: create → list → get → update (with sanitize) → delete. If a
refactor of the note endpoints (or their extraction into a blueprint)
breaks the wire format, this fails immediately.
"""


def test_note_crud_round_trip(client, corpus_dir):
    # Create.
    r = client.post("/api/notes", json={
        "title": "First note",
        "body_html": "<p>hello</p>",
    })
    assert r.status_code == 200
    n = r.get_json()
    nid = n["id"]
    assert n["title"] == "First note"
    assert "<p>hello</p>" in n["body_html"]
    assert n["created_at"]

    # List — sidebar row shape.
    r = client.get("/api/notes")
    assert r.status_code == 200
    rows = r.get_json()
    assert len(rows) == 1
    assert rows[0]["id"] == nid
    assert rows[0]["title"] == "First note"
    assert "snippet" in rows[0]

    # Get by id.
    r = client.get(f"/api/note/{nid}")
    assert r.status_code == 200
    assert r.get_json()["id"] == nid

    # Update — sanitizer runs on the body.
    r = client.put(f"/api/note/{nid}", json={
        "title": "Renamed",
        "body_html": "<p>edited</p><script>alert(1)</script>",
    })
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["title"] == "Renamed"
    assert "<script>" not in updated["body_html"]
    assert "<p>edited</p>" in updated["body_html"]

    # 404 for unknown note.
    r = client.get("/api/note/does-not-exist")
    assert r.status_code == 404

    # Delete.
    r = client.delete(f"/api/note/{nid}")
    assert r.status_code == 200

    # Gone.
    r = client.get(f"/api/note/{nid}")
    assert r.status_code == 404


def test_untitled_note_defaults_title(client, corpus_dir):
    r = client.post("/api/notes", json={"title": "   ", "body_html": ""})
    assert r.status_code == 200
    assert r.get_json()["title"] == "Untitled note"


def test_notes_endpoint_requires_corpus(client, corpus_dir, monkeypatch):
    """When corpus_dir is unset the endpoints must 400, not 500."""
    import _paths
    monkeypatch.setattr(_paths, "_CORPUS_ROOT", None)
    monkeypatch.delenv("CORPUS_DIR", raising=False)
    r = client.get("/api/notes")
    assert r.status_code == 400
