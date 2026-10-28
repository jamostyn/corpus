"""pytest fixtures shared across the Corpus smoke suite.

Two things every server-touching test needs:
  1. `python/` and `python/extract/` on sys.path so the same imports
     work as when launcher.py boots the app.
  2. A scratch corpus_dir so tests don't stomp on the user's real one.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

_DEV_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DEV_ROOT / "python"))
sys.path.insert(0, str(_DEV_ROOT / "python" / "extract"))


@pytest.fixture(autouse=True)
def scratch_config(tmp_path, monkeypatch):
    """Point config_api at a throwaway config file for EVERY test.

    autouse, because the protection has to be structural. The project
    has always promised that tests never touch that path, and `config_api`
    has always carried a `CORPUS_CONFIG_PATH` override commented "so
    tests can point at a scratch file instead of stomping on the real
    user's ~/.corpus/config.json" — but nothing used it, so the promise
    rested on every test author remembering to monkeypatch.

    On 2026-09-17 one didn't. `test_setting_corpus_dir_to_the_source_
    tree_is_refused` POSTed to /api/config without redirecting the
    path. That is harmless while the guard it tests is working, and the
    moment the guard was mutated away to check the test had teeth, the
    POST succeeded and wrote `corpus/dev` into the user's real config —
    silently undoing the corpus directory just set.

    Returns the scratch path so tests that need to inspect what was
    written can read it."""
    import config_api
    cfg = tmp_path / "scratch-corpus-config" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_api, "CONFIG_PATH", cfg)
    monkeypatch.setattr(config_api, "CONFIG_DIR", cfg.parent)
    monkeypatch.setattr(config_api, "TOOLTIPS_PATH", cfg.parent / "tooltips.json")
    return cfg


@pytest.fixture
def corpus_dir(tmp_path):
    """Point the running server / extract scripts at a fresh scratch
    corpus dir. Yields the path; ensures every subdir the code expects
    (`papers/`, `summaries/`, `inbox/`, `notes/`, `highlights/`) exists.

    Since 2026-08-16, `server`'s import is a pure module load — no
    Keychain reads, no env writes. Callers who need the real config
    applied call `server.init_app()` explicitly. Tests don't."""
    import server  # noqa: F401 — imports Flask app; safe, side-effect-free
    import _paths
    import _api_common
    import citations
    # Both caches are process-global. Each test gets its own tmp_path
    # corpus, so a surviving entry from a previous test would be a
    # stale answer about a different corpus — the exact failure the
    # caches exist to avoid, reintroduced as test flakiness.
    _api_common.clear_summary_cache()
    citations.clear_index_cache()
    _paths.set_corpus_root(tmp_path)
    _paths.ensure_corpus_layout()
    (tmp_path / "notes").mkdir(exist_ok=True)
    (tmp_path / "highlights").mkdir(exist_ok=True)
    yield tmp_path
    # No teardown needed — tmp_path is auto-cleaned by pytest.


@pytest.fixture
def client(corpus_dir):
    """Flask test client pointed at the scratch corpus."""
    import server
    server.app.testing = True
    return server.app.test_client()
