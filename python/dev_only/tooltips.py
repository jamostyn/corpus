"""DEV-ONLY — tooltip-editor save endpoint. NOT to be shipped.

The frontend's tooltip editor (src/dev_only/tooltip-editor.js) POSTs
here to persist user-edited tooltip strings. Values are stored at
~/.corpus/tooltips.json; the main server's /api/tooltips GET serves
them back to the app (which merges with hardcoded defaults).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("dev_tooltips", __name__)


def _tooltips_path() -> Path:
    """Sibling of the config file (~/.corpus/tooltips.json in normal
    use; scratchpad sibling in tests). Honors CORPUS_CONFIG_PATH so
    scratchpad tests can't touch the user's real overrides file."""
    override = os.environ.get("CORPUS_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().parent / "tooltips.json"
    return Path.home() / ".corpus" / "tooltips.json"


def _load() -> dict:
    p = _tooltips_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = _tooltips_path()
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@bp.route("/api/dev/tooltips", methods=["POST"])
def save_tooltips():
    """Merge posted {key: text} pairs into the persistent overrides
    file. Empty-string value REMOVES that override (falls back to the
    hardcoded default in the frontend). Returns the resulting overrides
    dict for the editor to reflect immediately."""
    data = request.get_json(silent=True) or {}
    current = _load()
    for k, v in (data.get("updates") or {}).items():
        k = str(k).strip()
        if not k:
            continue
        v = str(v or "").strip()
        if v:
            current[k] = v
        else:
            current.pop(k, None)
    _save(current)
    return jsonify({"ok": True, "overrides": current})


def register(app):
    app.register_blueprint(bp)
