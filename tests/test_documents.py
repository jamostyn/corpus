"""The Documents tab: a PDF to read, highlight and annotate — nothing more.

Requirement (2026-09-25): a second documents tab for standalone PDFs such
as a book chapter. It gets the text, highlight, and note features of
paper PDFs but no API-backed enrichment.
"""
from __future__ import annotations

import io
import json

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _upload(client, name="Chapter 3 - Memory.pdf"):
    return client.post("/api/documents", data={"file": (io.BytesIO(PDF), name)},
                       content_type="multipart/form-data")


def test_an_uploaded_pdf_is_listed_and_served(client, corpus_dir):
    """Catches the basic path breaking: upload, list, open."""
    r = _upload(client)
    assert r.status_code == 201
    doc = r.get_json()
    assert doc["id"] == "chapter-3-memory" and doc["title"] == "Chapter 3 - Memory"
    assert [d["id"] for d in client.get("/api/documents").get_json()] == ["chapter-3-memory"]
    pdf = client.get("/document/chapter-3-memory/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_a_document_never_touches_the_paper_pipeline(client, corpus_dir, monkeypatch):
    """Catches a document leaking into papers/ or summaries/. Everything
    there is swept by Scan's backfill, citers and the bridge search — the
    API-backed enrichment documents are excluded from — and a book chapter would show up in the
    paper list with an 'unknown' title. Also: no network, ever."""
    import _api_http
    monkeypatch.setattr(_api_http, "api_get_json",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network call")))
    _upload(client)
    assert not list((corpus_dir / "papers").glob("*.pdf"))
    assert not list((corpus_dir / "summaries").glob("*.md"))
    assert client.get("/api/papers").get_json() == []


def test_two_uploads_with_the_same_name_do_not_overwrite(client, corpus_dir):
    """Catches the id colliding and the second chapter replacing the
    first — and its highlights with it."""
    a = _upload(client).get_json()["id"]
    b = _upload(client).get_json()["id"]
    assert a != b
    assert len(client.get("/api/documents").get_json()) == 2


def test_highlights_and_anchored_notes_round_trip(client, corpus_dir):
    """Catches the note feature not reaching documents: an anchored note
    lives on its highlight, and must survive a save and a reload."""
    doc_id = _upload(client).get_json()["id"]
    hl = {"id": "h1", "page": 2, "color": "#FFEB3B", "text": "encoding",
          "rects": [{"x": 1, "y": 2, "width": 3, "height": 4}], "note": "compare with Tulving"}
    r = client.post(f"/api/document/{doc_id}/highlights", json={"highlights": [hl]})
    assert r.get_json() == {"ok": True, "count": 1}
    got = client.get(f"/api/document/{doc_id}/highlights").get_json()["highlights"]
    assert got[0]["note"] == "compare with Tulving" and got[0]["page"] == 2


def test_documents_and_papers_share_one_highlight_cleaner(client, corpus_dir):
    """Catches the cleaner being copied instead of shared: an empty-rect
    highlight must be dropped by BOTH endpoints, or the viewer would save
    fields one keeps and the other loses."""
    import highlights_store
    import papers_api
    import documents_api
    assert papers_api.clean_highlights is highlights_store.clean_highlights
    assert documents_api.clean_highlights is highlights_store.clean_highlights
    doc_id = _upload(client).get_json()["id"]
    r = client.post(f"/api/document/{doc_id}/highlights",
                    json={"highlights": [{"id": "x", "rects": []}]})
    assert r.get_json()["count"] == 0


def test_a_document_id_cannot_reach_outside_its_folder(client, corpus_dir):
    """Catches path traversal: the id is a folder name, so an id like
    `..` or one with a slash must never be looked up."""
    (corpus_dir / "secret.json").write_text(json.dumps({"highlights": ["leak"]}))
    for bad in ("..", "..%2F", "Chapter", "a_b"):
        assert client.get(f"/api/document/{bad}/highlights").status_code == 404
        assert client.get(f"/document/{bad}/pdf").status_code == 404


def test_only_pdfs_are_accepted(client, corpus_dir):
    """Catches an upload of the wrong file silently becoming a document
    the viewer cannot open."""
    r = client.post("/api/documents", data={"file": (io.BytesIO(b"hello"), "notes.txt")},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert client.get("/api/documents").get_json() == []


# ---------- 2026-09-25, round 2: rename, projects, note links, pop-out ----------
#
# Requirements: documents can be linked from notes, renamed, popped out,
# and added to projects.

def test_renaming_changes_the_title_but_never_the_id(client, corpus_dir):
    """Catches a rename that moves the document: the id is what note
    links, project membership and the highlights folder point at, so
    changing it would orphan all three."""
    doc_id = _upload(client).get_json()["id"]
    client.post(f"/api/document/{doc_id}/highlights", json={"highlights": [
        {"id": "h1", "rects": [{"x": 1, "y": 1, "width": 1, "height": 1}], "note": "kept"}]})
    r = client.patch(f"/api/document/{doc_id}", json={"title": "Craik & Lockhart (1972) ch. 3"})
    assert r.status_code == 200 and r.get_json()["title"] == "Craik & Lockhart (1972) ch. 3"
    row = client.get("/api/documents").get_json()[0]
    assert (row["id"], row["title"]) == (doc_id, "Craik & Lockhart (1972) ch. 3")
    assert client.get(f"/api/document/{doc_id}/highlights").get_json()["highlights"][0]["note"] == "kept"


def test_an_empty_title_is_refused(client, corpus_dir):
    """Catches a blank rename leaving a document the list shows as nothing."""
    doc_id = _upload(client).get_json()["id"]
    assert client.patch(f"/api/document/{doc_id}", json={"title": "   "}).status_code == 400
    assert client.get("/api/documents").get_json()[0]["title"] == "Chapter 3 - Memory"


def test_a_document_can_join_a_project(client, corpus_dir):
    """Catches the member kind existing on one side only: the project
    endpoint must accept a document AND resolve it to a title, or the
    project shows a count with nothing listed."""
    doc_id = _upload(client).get_json()["id"]
    pid = client.post("/api/projects", json={"title": "Prelims"}).get_json()["id"]
    r = client.post(f"/api/project/{pid}/members", json={"kind": "document", "id": doc_id, "op": "add"})
    assert r.status_code == 200
    got = client.get(f"/api/project/{pid}").get_json()
    assert [(m["id"], m["title"]) for m in got["resolved"]["document"]] == [(doc_id, "Chapter 3 - Memory")]
    assert [p["title"] for p in client.get(f"/api/member-projects/document/{doc_id}").get_json()] == ["Prelims"]


def test_a_note_keeps_a_document_link_when_saved(client, corpus_dir):
    """Catches the sanitizer's allow-list missing the new kind: a
    `data-open-document` link would be stripped the moment the note
    saved, leaving plain text where the link was."""
    from notes_api import _sanitize_note_html
    html = ('<a href="#" class="note-entity-link" data-open-document="chapter-3-memory" '
            'data-open-highlight="h1">quote</a>')
    out = _sanitize_note_html(html)
    assert 'data-open-document="chapter-3-memory"' in out and 'data-open-highlight="h1"' in out


def test_a_document_pop_out_opens_as_a_document_not_a_paper():
    """Catches the pop-out window reading its `#detached=document:<id>`
    hash as a paper — an unknown kind falls back to "paper", which would
    look the id up as a paper slug and show a blank window."""
    from pathlib import Path
    app = (Path(__file__).resolve().parent.parent / "src" / "app.js").read_text()
    kinds = app[app.index("const DETACH_KINDS"):]
    assert '"document"' in kinds[:kinds.index(";")]
    boot = app[app.index("async function boot()"):]
    boot = boot[:boot.index("\n}\n")]
    assert 'detached.kind === "document"' in boot and "selectDocument(detached.id)" in boot
