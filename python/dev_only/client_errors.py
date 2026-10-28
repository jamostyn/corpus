"""Frontend errors, written to server.log. Dev builds only.

Why: the pywebview window has no visible console, so a JavaScript
exception left no trace at all. On 2026-09-21 a popped-out note opened
blank and boot had stopped after /api/tooltips in both windows; the only
evidence was which API calls were MISSING from the log. With this, the
next one arrives as `client_error where=boot msg=...` plus its stack.

Stripped from the ship with the rest of `python/dev_only/`; app.js also
checks `dev_mode` before sending, so a shipped build never calls it.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger("corpus.client")

bp = Blueprint("dev_client_errors", __name__)

# A stack can be long; the log is for finding the line, not archiving.
_MAX_FIELD = 4000


@bp.route("/api/dev/client-error", methods=["POST"])
def client_error():
    d = request.get_json(silent=True) or {}
    where = str(d.get("where") or "")[:40]
    msg = str(d.get("message") or "")[:_MAX_FIELD]
    url = str(d.get("url") or "")[:500]
    stack = str(d.get("stack") or "")[:_MAX_FIELD]
    logger.warning("client_error where=%s msg=%r url=%s\n%s", where, msg, url, stack)
    return jsonify({"ok": True})


def register(app):
    app.register_blueprint(bp)
