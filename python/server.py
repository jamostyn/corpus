"""Corpus HTTP server — Flask composition root.

Every API surface lives in a blueprint under this directory:
  * config_api.py    — /api/config, /api/tooltips, /api/pick-corpus
  * papers_api.py    — /api/papers, /api/paper/<slug>, /pdf/<slug>,
                       highlights, reveal-in-Finder
  * entities_api.py  — /api/authors, /api/institutions, /api/journals
                       + their detail endpoints
  * notes_api.py     — /api/notes CRUD
  * extract_api.py   — /api/extract, /api/scan, re-extract

Server.py itself only wires them together, hosts the SPA static
handler, computes IS_DEV, sets up (or disables) the corpus logger
tree, and exposes the launcher-facing `set_bridge` alias.

Endpoints:
  GET  /                       serves the SPA
  ...all API/dev routes registered via their blueprints
"""
from __future__ import annotations

import logging
import mimetypes
import sys
import time
from pathlib import Path

from flask import Flask, request, send_from_directory

# Extract scripts live in python/extract/; put them on sys.path so
# `import _paths`, `import oa_enrichment`, etc. resolve.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "extract"))

# Blueprints (import order doesn't matter; registration order is
# effectively arbitrary too — no blueprint shadows another's URL).
import config_api    # noqa: E402
import entities_api  # noqa: E402
import extract_api   # noqa: E402
import notes_api     # noqa: E402
import papers_api    # noqa: E402
import bridges_api  # noqa: E402
import citers_api  # noqa: E402
import documents_api  # noqa: E402
import projects_api  # noqa: E402
import progress      # noqa: E402

logger = logging.getLogger("corpus.server")


# ---------- Flask app ----------

# Static frontend lives in ../src/ in the source tree. In a PyInstaller
# bundle it lives at <_MEIPASS>/src/ because the spec ships src/ as a
# top-level data dir. sys.frozen is set by PyInstaller's bootloader.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _SRC = Path(sys._MEIPASS) / "src"
else:
    _SRC = _HERE.parent / "src"
app = Flask(__name__, static_folder=str(_SRC), static_url_path="")


# ---------- Content types for the frontend ----------
#
# Flask serves every static file with `mimetypes.guess_type`. On Windows
# that table is patched from the REGISTRY (mimetypes.read_windows_registry
# runs on first use and overrides the built-in defaults), and other
# installed software can register `.js` / `.mjs` as `text/plain`. The
# browser then refuses to run pdf.js: `pdf.mjs`, `viewer.mjs` and the
# worker are ES modules, and a module served as anything but JavaScript
# is rejected outright. Classic scripts (the whole main app) still run
# under `text/plain`, so the failure shows up ONLY as a PDF viewer with a
# toolbar and no pages (seen on Windows, 2026-09-29).
#
# Pinned here so the answer never depends on the machine. `add_type`
# initialises the table (registry included) first and then overrides, so
# these win. Every extension a browser enforces a type for and that
# ships under src/ must be listed — `tests/test_web_mime_types.py` walks
# src/ to hold this table to it.
WEB_MIME_TYPES = {
    ".js":   "text/javascript",
    ".mjs":  "text/javascript",
    ".css":  "text/css",
    ".html": "text/html",
    ".svg":  "image/svg+xml",
    ".json": "application/json",
    ".pdf":  "application/pdf",
}


def pin_web_mime_types() -> None:
    for ext, mime in WEB_MIME_TYPES.items():
        mimetypes.add_type(mime, ext)


pin_web_mime_types()


# ---------- Dev mode detection ----------
#
# `python/dev_only/` and `src/dev_only/` exist ONLY in the dev repo.
# Release builds strip both directories, so
# their presence is a reliable signal of a dev vs shipped build.
# Anything that should be developer-only (bug reporter, planning
# modal, tooltip editor, LOGGING) is gated on this.
#
# We compute this early so the logging + access-hook wiring below
# can consult it. Also stashed on app.config so blueprints (in
# particular config_api's /api/config endpoint) can read it via
# current_app without importing server (which would circular).
IS_DEV = (_HERE / "dev_only").is_dir() and (_SRC / "dev_only").is_dir()
app.config["CORPUS_IS_DEV"] = IS_DEV


# ---------- Request access log (DEV-ONLY) ----------
#
# Every /api/* call (and dev-only /dev/* call) produces one log line
# with method + path + status + wall-clock duration. Gives dev
# builds a grep-able trail of every user interaction. Static asset
# requests (JS, CSS, PDF worker, etc.) are skipped so the log isn't
# drowned.
#
# SHIPPED BUILDS: these hooks are NOT registered — no `before_request`
# runs, no `time.monotonic()` on every request, no log lines. Zero
# runtime overhead + zero visibility into user actions. Matches
# `_configure_logging()` below which fully disables the `corpus.*`
# logger tree when not dev.
#
# Format: `api_request method=POST path=/api/scan status=200 dur_ms=124`

if IS_DEV:
    @app.before_request
    def _access_log_start():
        request._t_start = time.monotonic()  # type: ignore[attr-defined]

    @app.after_request
    def _access_log_finish(resp):
        # Only log real API/dev calls; skip static SPA + PDF-worker chatter.
        path = request.path or ""
        if not (path.startswith("/api/") or path.startswith("/dev/")
                or path.startswith("/pdf/")):
            return resp
        dur_ms = int((time.monotonic() - getattr(request, "_t_start", time.monotonic())) * 1000)
        logger.info("api_request method=%s path=%s status=%d dur_ms=%d",
                    request.method, path, resp.status_code, dur_ms)
        return resp


# ---------- Blueprint registration ----------

app.register_blueprint(config_api.config_bp)
app.register_blueprint(papers_api.papers_bp)
app.register_blueprint(entities_api.entities_bp)
app.register_blueprint(notes_api.notes_bp)
app.register_blueprint(extract_api.extract_bp)
app.register_blueprint(projects_api.projects_bp)
app.register_blueprint(bridges_api.bridges_bp)
app.register_blueprint(citers_api.citers_bp)
app.register_blueprint(documents_api.documents_bp)
app.register_blueprint(progress.progress_bp)


# ---------- Dev-only surfaces ----------
#
# Only present on disk in dev builds — release builds strip
# both python/dev_only/ and src/dev_only/. `IS_DEV` = presence check.
# In a shipped build:
#   - the dev_only Python package isn't importable → this block no-ops
#   - /api/config returns dev_mode: false → frontend never asks for
#     /dev_only/bug-reporter.js
#   - the corpus.* logger tree is fully disabled (_configure_logging)
if IS_DEV:
    try:
        from dev_only import bug_reports as _dev_bug_reports  # noqa: E402
        _dev_bug_reports.register(app)
    except Exception:
        IS_DEV = False
    try:
        from dev_only import tooltips as _dev_tooltips  # noqa: E402
        _dev_tooltips.register(app)
    except Exception:
        pass
    try:
        from dev_only import planning as _dev_planning  # noqa: E402
        _dev_planning.register(app)
    except Exception:
        pass
    try:
        from dev_only import testing as _dev_testing  # noqa: E402
        _dev_testing.register(app)
    except Exception:
        pass
    try:
        from dev_only import client_errors as _dev_client_errors  # noqa: E402
        _dev_client_errors.register(app)
    except Exception:
        pass
    # Static assets under /dev_only/ (bug reporter JS, CSS, etc.).
    @app.route("/dev_only/<path:filename>")
    def _dev_only_static(filename):
        return send_from_directory(_SRC / "dev_only", filename)


# ---------- SPA entry point ----------

@app.route("/")
def index():
    return send_from_directory(_SRC, "index.html")


# ---------- Launcher back-compat ----------

# Launcher calls `srv.set_bridge(bridge)` to hand pywebview to the
# app. Real state lives in config_api._bridge; this is a thin alias
# so launcher.py doesn't need updating.
set_bridge = config_api.set_bridge


# ---------- Boot ----------

def _configure_logging() -> None:
    """Set up (or fully disable) the `corpus.*` logger tree.

    DEV mode: route to ~/.corpus/logs/server.log with rotation, plus
    WARNING+ echo to stderr. Idempotent — safe to call again.

    SHIPPED mode (IS_DEV is False): the entire `corpus.*` tree is
    DISABLED — every `logger.info(...)` / `logger.warning(...)` call
    short-circuits before any formatting, exc_info capture, or handler
    lookup. No log file created. No stderr noise. Zero visibility into
    user actions. This is intentional per user privacy request.

    If the log dir isn't writable (read-only home, etc.), falls back
    to stderr-only silently (dev only)."""
    root = logging.getLogger("corpus")
    if not IS_DEV:
        # Fully silence the corpus tree. Cheaper than any handler-level
        # filtering; short-circuits at Logger.isEnabledFor.
        root.disabled = True
        root.setLevel(logging.CRITICAL + 1)
        return
    if root.handlers:
        return  # already configured
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # File handler — rotates at 5MB, keeps 3 backups.
    try:
        from logging.handlers import RotatingFileHandler
        log_dir = config_api.CONFIG_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "server.log", maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass  # read-only home / no permission — stderr handler still works
    # Console handler — WARNING and up, so dev tail-following stays quiet.
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def init_app() -> None:
    """Initialize server state — configure logging, read the persisted
    config, apply it to the process env (CORPUS_MAILTO, CORPUS_<KEY>),
    and set the corpus root if one is stored. Idempotent — safe to
    call again after a config change (the config endpoint does exactly
    that).

    Extracted from an import-time side effect on 2026-08-16. Import-
    time initialization made every test that imported `server` touch
    the real user's Keychain + config unless CORPUS_CONFIG_PATH was
    set first. Callers now call this explicitly:
      * `launcher.py` before make_server()
      * tests via the `client` / `corpus_dir` fixtures (or explicitly
        when they need env vars populated)
    """
    _configure_logging()
    config_api._apply_env()


if __name__ == "__main__":
    # Development mode: run on a fixed port so the browser can be pointed at it.
    init_app()
    print("Corpus dev server on http://127.0.0.1:5051", flush=True)
    app.run(host="127.0.0.1", port=5051, debug=False, use_reloader=False)
