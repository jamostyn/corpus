"""Corpus — /api/config, /api/tooltips, /api/pick-corpus blueprint.

Extracted from server.py on 2026-08-16 (Wave-3 blueprint split).

Owns:
  * Config store (plain JSON at ~/.corpus/config.json).
  * Secret store (OS Keychain via `keyring`; JSON fallback).
  * `_apply_env` — wires config values into env vars the extract
    scripts consume. Called from `/api/config` POST and from
    `server.init_app()` at boot.
  * `/api/config` GET / POST endpoints.
  * `/api/tooltips` GET.
  * `/api/pick-corpus` POST + `_bridge` state + `set_bridge()` for
    launcher.py's native folder-picker.

Reads `IS_DEV` from `current_app.config["CORPUS_IS_DEV"]` (set by
server.py at startup) — needed for the `dev_mode` field the
frontend consults to decide whether to load the dev-only bundle.

Wired in server.py via `app.register_blueprint(config_bp)`.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from _paths import ensure_corpus_layout, is_corpus_source_tree, set_corpus_root
from _version import __version__

logger = logging.getLogger("corpus.config_api")

config_bp = Blueprint("config", __name__)


# ---------- Config store (plain JSON) + secret store (OS Keychain) ----------

# Config path is overridable via CORPUS_CONFIG_PATH so tests can point at
# a scratch file instead of stomping on the real user's ~/.corpus/config.json.
# Left as an env var (not CLI) because the launcher never exposes flags.
_cfg_override = os.environ.get("CORPUS_CONFIG_PATH")
CONFIG_PATH = Path(_cfg_override).expanduser().resolve() if _cfg_override else (Path.home() / ".corpus" / "config.json")
CONFIG_DIR  = CONFIG_PATH.parent
TOOLTIPS_PATH = CONFIG_DIR / "tooltips.json"
KEYRING_SERVICE = "corpus"
SECRET_KEYS = ("semantic_scholar_key", "openalex_key")  # kept in Keychain


def _load_json_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        logger.warning("config_load_failed path=%s", CONFIG_PATH, exc_info=True)
        return {}


def _save_json_config(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        logger.info("config_saved path=%s keys=%s",
                    CONFIG_PATH, sorted(cfg.keys()))
    except Exception:
        logger.warning("config_save_failed path=%s", CONFIG_PATH, exc_info=True)
        raise


def _get_secret(name: str) -> str | None:
    """Try Keychain first (via keyring). Falls back to config.json if
    keyring isn't installed (e.g. minimal dev environment)."""
    try:
        import keyring
        val = keyring.get_password(KEYRING_SERVICE, name)
        if val:
            return val
    except Exception:
        pass
    cfg = _load_json_config()
    return (cfg.get("_secrets") or {}).get(name)


def _set_secret(name: str, value: str) -> None:
    """Store in Keychain if available, else stash in ~/.corpus/config.json
    (plaintext — a fallback that at least lets the app work)."""
    try:
        import keyring
        if value:
            keyring.set_password(KEYRING_SERVICE, name, value)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, name)
            except Exception:
                pass
        return
    except Exception:
        pass
    cfg = _load_json_config()
    secrets = cfg.get("_secrets") or {}
    if value:
        secrets[name] = value
    else:
        secrets.pop(name, None)
    cfg["_secrets"] = secrets
    _save_json_config(cfg)


def _apply_env() -> None:
    """Wire config values into env vars the extract scripts consume."""
    cfg = _load_json_config()
    corpus = cfg.get("corpus_dir")
    if corpus:
        try:
            set_corpus_root(corpus)
            ensure_corpus_layout()
        except Exception:
            # Usually benign: the corpus dir may not exist yet on first
            # boot. But this also catches the source-tree refusal from
            # ensure_corpus_layout, and a bare `pass` made that
            # invisible — which is how a bad corpus_dir stayed on disk
            # unnoticed. CONTRIBUTING.md requires a log on every
            # swallowing except; this one had none.
            logger.warning("corpus_layout_skipped path=%s", corpus, exc_info=True)
    mailto = cfg.get("mailto", "").strip()
    if mailto:
        os.environ["CORPUS_MAILTO"] = mailto
    else:
        os.environ.pop("CORPUS_MAILTO", None)
    for k in SECRET_KEYS:
        v = _get_secret(k)
        if v:
            os.environ[f"CORPUS_{k.upper()}"] = v
        else:
            os.environ.pop(f"CORPUS_{k.upper()}", None)


# ---------- Endpoints ------------------------------------------------

@config_bp.route("/api/config", methods=["GET"])
def get_config():
    cfg = _load_json_config()
    return jsonify({
        "corpus_dir": cfg.get("corpus_dir") or "",
        "mailto":     cfg.get("mailto") or "",
        "keys": {
            k: bool(_get_secret(k))
            for k in SECRET_KEYS
        },
        # dev_mode is true ONLY when dev_only/ dirs are on disk. Shipped
        # builds don't have those dirs, so this returns false and the
        # frontend skips loading the dev-only bundle. server.py sets
        # CORPUS_IS_DEV in app.config at boot.
        "dev_mode": bool(current_app.config.get("CORPUS_IS_DEV")),
    })


@config_bp.route("/api/config", methods=["POST"])
def set_config():
    data = request.get_json(silent=True) or {}
    cfg = _load_json_config()
    if "corpus_dir" in data:
        corpus = (data["corpus_dir"] or "").strip()
        if corpus:
            # Expand user + resolve to absolute so downstream paths are stable.
            corpus = str(Path(corpus).expanduser().resolve())
            # Refuse the Corpus source tree. Accepting it scaffolds
            # papers/ summaries/ inbox/ into the repo, where git cannot
            # see them (empty dirs are untracked) while the app shows an
            # empty corpus — a mistake with no visible symptom. Rejected
            # HERE rather than at scaffold time so the user finds out
            # when they pick the folder, not silently on the next boot.
            if is_corpus_source_tree(corpus):
                logger.info("config_rejected_source_tree path=%s", corpus)
                return jsonify({
                    "ok": False,
                    "error": "corpus_dir_is_source_tree",
                    "description": (
                        "That folder is the Corpus application's own source "
                        "code, not a corpus. Pick or create a separate "
                        "folder for your papers."),
                }), 400
        cfg["corpus_dir"] = corpus
    if "mailto" in data:
        cfg["mailto"] = (data["mailto"] or "").strip()
    _save_json_config(cfg)
    # Secrets go through Keychain, not the JSON file.
    keys = data.get("keys") or {}
    for k in SECRET_KEYS:
        if k in keys:
            _set_secret(k, (keys.get(k) or "").strip())
    _apply_env()
    return jsonify({"ok": True})


@config_bp.route("/api/version", methods=["GET"])
def get_version():
    """Corpus version — read by the frontend for display and by future
    bug reports for error context. Single source of truth: _version.py."""
    return jsonify({"version": __version__})


@config_bp.route("/api/tooltips", methods=["GET"])
def get_tooltips():
    """Serve user overrides from ~/.corpus/tooltips.json. Frontend
    merges these on top of the defaults defined in tooltips.default.js.
    Returns {} if no overrides exist yet."""
    if not TOOLTIPS_PATH.exists():
        return jsonify({})
    try:
        return jsonify(json.loads(TOOLTIPS_PATH.read_text(encoding="utf-8")))
    except Exception:
        return jsonify({})


# ---------- Native-dialog bridge (called by launcher, not by browser JS) -----

# Set by launcher when it exposes pywebview to the app. When None, the
# /api/pick-corpus endpoint returns 501 (browser fallback: user types path).
_bridge = None


def set_bridge(bridge):
    """Called by launcher.py once pywebview is up, so /api/pick-corpus
    can invoke the OS folder-picker. server.py re-exports this for
    backward compat with older launcher versions that did
    `srv.set_bridge(...)`."""
    global _bridge
    _bridge = bridge


@config_bp.route("/api/pick-corpus", methods=["POST"])
def pick_corpus():
    """Ask the desktop shell to open a native folder-picker. Returns
    {path: <string>} or {path: null} if user cancelled. 501 if no
    native shell (running in browser)."""
    if _bridge is None:
        return jsonify({"error": "no_native_shell"}), 501
    path = _bridge.pick_folder()
    return jsonify({"path": path})
