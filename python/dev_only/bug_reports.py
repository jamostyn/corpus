"""DEV-ONLY — bug report endpoint. NOT to be shipped.

Client (see src/dev_only/bug-reporter.js) captures a screenshot of the
current window (via html2canvas), lets the user draw highlight boxes
and type a description, then POSTs everything here. We stash it under
`~/.corpus/bug-reports/<timestamp>/` so it's easy to find later.
"""
from __future__ import annotations

import base64
import datetime as _dt
import logging
import re
from pathlib import Path

from flask import Blueprint, jsonify, request

logger = logging.getLogger("corpus.bug_reports")

bp = Blueprint("dev_bug_reports", __name__)

REPORTS_DIR = Path.home() / ".corpus" / "bug-reports"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(s: str, max_len: int = 40) -> str:
    """Convert the first line of a description into a filesystem-safe
    slug so the directory name includes a hint of what's inside."""
    s = (s or "").splitlines()[0].strip().lower()
    s = _SLUG_STRIP.sub("-", s).strip("-")
    return s[:max_len] or "unlabeled"


@bp.route("/api/dev/bug-report", methods=["POST"])
def submit_report():
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    screenshot_b64 = data.get("screenshot") or ""
    view_context = data.get("view_context") or {}

    if not description and not screenshot_b64:
        return jsonify({"error": "empty_report"}), 400

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    label = _slugify(description)
    dst = REPORTS_DIR / f"{ts}-{label}"
    dst.mkdir(parents=True, exist_ok=True)

    # Screenshot: data-URL like "data:image/png;base64,iVBORw..." — strip
    # the prefix if present, then decode.
    if screenshot_b64:
        body = screenshot_b64.split(",", 1)[-1]
        try:
            (dst / "screenshot.png").write_bytes(base64.b64decode(body))
        except Exception as e:
            logger.warning("bug_report_screenshot_decode_failed dst=%s", dst, exc_info=True)
            return jsonify({"error": f"screenshot_decode_failed: {e}"}), 400

    # Description with frontmatter — matches the shape Paper Machine's
    # /issues folder uses so a reader can grok both without switching gears.
    fm_lines = [
        "---",
        f'title: "{_first_line(description)}"',
        "kind: bug",
        f"created_at: {_dt.datetime.now().replace(microsecond=0).isoformat()}",
        f'page_url: "{view_context.get("url", "")}"',
        f'viewport: "{view_context.get("viewport", "")}"',
        f'user_agent: "{view_context.get("user_agent", "")}"',
        "status: open",
        "---",
        "",
        description or "(no description)",
    ]
    (dst / "description.md").write_text("\n".join(fm_lines), encoding="utf-8")
    logger.info("bug_report_saved label=%s dst=%s desc_len=%d has_screenshot=%s",
                label, dst, len(description), bool(screenshot_b64))

    return jsonify({"ok": True, "path": str(dst), "label": f"{ts}-{label}"})


def _first_line(text: str) -> str:
    line = (text or "").splitlines()[0].strip() if text else ""
    return line.replace('"', '\\"')[:120]


def register(app):
    """Register this blueprint on the Flask app. Called from server.py
    only when the dev_only/ package is present on disk."""
    app.register_blueprint(bp)
