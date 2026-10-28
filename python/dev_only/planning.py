"""DEV-ONLY — planning-list persistence. NOT shipped.

The frontend's Planning modal (src/dev_only/planning.js) POSTs the
whole task list here after every edit. Stored at ~/.corpus/planning.json
(or CORPUS_CONFIG_PATH's sibling for tests).

List ORDER = priority. Frontend drag-and-drop reorders locally then
POSTs the new order.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("dev_planning", __name__)


def _planning_path() -> Path:
    override = os.environ.get("CORPUS_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().parent / "planning.json"
    return Path.home() / ".corpus" / "planning.json"


def _load() -> list:
    p = _planning_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # Tolerate both `[tasks]` and `{tasks: [tasks]}` shapes so
        # hand-edits don't nuke the file.
        if isinstance(raw, dict):
            return list(raw.get("tasks") or [])
        return list(raw or [])
    except Exception:
        return []


def _save(tasks: list) -> None:
    p = _planning_path()
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"tasks": tasks}, indent=2, ensure_ascii=False),
                  encoding="utf-8")


@bp.route("/api/dev/planning", methods=["GET"])
def get_planning():
    return jsonify({"tasks": _load()})


@bp.route("/api/dev/planning", methods=["POST"])
def save_planning():
    """Replace the entire task list with what the frontend sent.

    Frontend is the source of truth during a session — it mutates
    locally and POSTs the full new state after each change. Simpler
    than per-field endpoints; no CRUD-race edge cases."""
    data = request.get_json(silent=True) or {}
    tasks = data.get("tasks") or []
    if not isinstance(tasks, list):
        return jsonify({"error": "tasks must be a list"}), 400
    # Light sanitization — strip surrounding whitespace on strings and
    # drop obviously-empty rows.
    clean: list = []
    for t in tasks:
        if not isinstance(t, dict): continue
        title = str(t.get("title") or "").strip()
        if not title: continue
        clean.append({
            "id":          str(t.get("id") or "").strip(),
            "title":       title,
            # Longer free-form notes below the title. Empty is fine —
            # only title is required.
            "description": str(t.get("description") or "").strip(),
            "done":        bool(t.get("done")),
            "created_at":  str(t.get("created_at") or "").strip(),
            "updated_at":  str(t.get("updated_at") or "").strip(),
        })
    _save(clean)
    return jsonify({"ok": True, "tasks": clean})


def register(app):
    app.register_blueprint(bp)
