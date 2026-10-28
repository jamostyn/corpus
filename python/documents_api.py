"""Corpus — /api/documents blueprint. Added 2026-09-25.

Jack: "i want to add an another documents tab. for now i will just be
uploading a pdf of a book chapter. i dont want any fancy integrations
aside from all the text, highlight, and note features for the paper
pdfs. but none of the api stuff."

So a document is a PDF with a title and highlights, and nothing else:
no metadata lookup, no summary, no citers, no bridges. It is read in the
same PDF.js viewer as a paper, so text selection, search, highlights and
anchored notes all work unchanged — the viewer only needs to know which
highlights endpoint to talk to (see corpus-highlights.js).

Storage: `<corpus>/documents/<id>/` — see `_paths.documents_dir`.

Wired in server.py via `app.register_blueprint(documents_bp)`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from _api_common import require_corpus_or_abort
from _paths import documents_dir
from highlights_store import clean_highlights, load_highlights, save_highlights

logger = logging.getLogger("corpus.documents_api")

documents_bp = Blueprint("documents", __name__)

# An id is also a folder name, so it is the ONLY thing standing between
# a request path and the filesystem. Nothing outside this shape is ever
# looked up.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_PDF, _META, _HIGHLIGHTS = "document.pdf", "meta.json", "highlights.json"


def _folder(doc_id: str) -> Path:
    if not _ID_RE.match(doc_id or ""):
        abort(404)
    d = documents_dir() / doc_id
    if not (d / _PDF).exists():
        abort(404)
    return d


def _new_id(title: str) -> str:
    """Readable and unique: 'Chapter 3 - Memory.pdf' -> 'chapter-3-memory',
    then '-2', '-3' … if taken."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "document"
    doc_id, n = base, 1
    while (documents_dir() / doc_id).exists():
        n += 1
        doc_id = f"{base}-{n}"
    return doc_id


def _title_from_filename(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[_]+", " ", stem).strip() or "Untitled document"


def _meta(folder: Path) -> dict:
    try:
        m = json.loads((folder / _META).read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


@documents_bp.route("/api/documents", methods=["GET"])
def list_documents():
    require_corpus_or_abort()
    rows = []
    for d in sorted(documents_dir().iterdir()):
        if d.is_dir() and _ID_RE.match(d.name) and (d / _PDF).exists():
            m = _meta(d)
            rows.append({"id": d.name,
                         "title": m.get("title") or d.name,
                         "filename": m.get("filename") or "",
                         "added_at": m.get("added_at") or ""})
    rows.sort(key=lambda r: r["added_at"], reverse=True)    # newest first
    return jsonify(rows)


@documents_bp.route("/api/documents", methods=["POST"])
def add_document():
    """Upload one PDF. The title is the filename, tidied — deliberately no
    lookup of any kind."""
    require_corpus_or_abort()
    f = request.files.get("file")
    if f is None or not (f.filename or "").lower().endswith(".pdf"):
        return jsonify({"error": "not_a_pdf", "description": "Choose a PDF file."}), 400
    title = _title_from_filename(f.filename)
    doc_id = _new_id(title)
    folder = documents_dir() / doc_id
    folder.mkdir()
    f.save(str(folder / _PDF))
    meta = {"id": doc_id, "title": title, "filename": Path(f.filename).name,
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (folder / _META).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("document_added id=%s filename=%s", doc_id, meta["filename"])
    return jsonify(meta), 201


@documents_bp.route("/api/document/<doc_id>", methods=["PATCH"])
def rename_document(doc_id):
    """Change the displayed title. The id — which is also the folder name,
    the note-link target and the project member id — never changes, so a
    rename cannot break a link or orphan the highlights."""
    require_corpus_or_abort()
    folder = _folder(doc_id)
    title = str((request.get_json(silent=True) or {}).get("title") or "").strip()
    if not title:
        return jsonify({"error": "empty_title", "description": "A title can't be empty."}), 400
    meta = _meta(folder) or {"id": doc_id}
    meta["title"] = title[:300]
    (folder / _META).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("document_renamed id=%s", doc_id)
    return jsonify(meta)


def document_titles() -> dict:
    """id -> {id, title}, for every document. Used by projects_api to show
    a project's document members."""
    out = {}
    for d in documents_dir().iterdir():
        if d.is_dir() and _ID_RE.match(d.name) and (d / _PDF).exists():
            out[d.name] = {"id": d.name, "title": _meta(d).get("title") or d.name}
    return out


def document_exists(doc_id: str) -> bool:
    return bool(_ID_RE.match(doc_id or "")) and (documents_dir() / doc_id / _PDF).exists()


@documents_bp.route("/document/<doc_id>/pdf", methods=["GET"])
def serve_document_pdf(doc_id):
    require_corpus_or_abort()
    return send_file(_folder(doc_id) / _PDF, mimetype="application/pdf")


@documents_bp.route("/api/document/<doc_id>/highlights", methods=["GET"])
def get_document_highlights(doc_id):
    require_corpus_or_abort()
    return jsonify(load_highlights(_folder(doc_id) / _HIGHLIGHTS))


@documents_bp.route("/api/document/<doc_id>/highlights", methods=["POST"])
def save_document_highlights(doc_id):
    require_corpus_or_abort()
    folder = _folder(doc_id)
    hls = (request.get_json(silent=True) or {}).get("highlights") or []
    if not isinstance(hls, list):
        return jsonify({"error": "highlights must be a list"}), 400
    clean = clean_highlights(hls)
    save_highlights(folder / _HIGHLIGHTS, clean)
    logger.info("document_highlights_saved id=%s count=%d", doc_id, len(clean))
    return jsonify({"ok": True, "count": len(clean)})
