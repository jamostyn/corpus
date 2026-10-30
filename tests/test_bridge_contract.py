"""launcher.py's pywebview bridge vs the JS that calls it.

The Pop-out feature crosses a language boundary: `src/*.js` calls
`window.pywebview.api.<method>()`, and those methods are supplied by
`_Bridge` in `launcher.py`. Nothing else ties the two together — no
shared schema, no codegen.

Why this matters more than a normal contract: every JS call site wraps
the bridge call in `try { ... } catch (_) {}`. If a Python method is
renamed, the JS throws, the empty catch swallows it, and the feature
dies with no error, no toast, and no log line. The user just clicks
"Pop out" and nothing happens.

`app.js` additionally sniffs for ONE specific method
(`api.open_detached`) to decide whether it is running under pywebview
at all. Renaming that method doesn't just break pop-out — it silently
downgrades every user to the browser `window.open` fallback path.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_DEV_ROOT = Path(__file__).resolve().parent.parent
_SRC = _DEV_ROOT / "src"

# Methods the frontend is allowed to call on the bridge. Update this
# set ONLY together with both sides of the boundary.
EXPECTED_BRIDGE_METHODS = {
    "pick_folder",
    "open_detached",
    "focus_detached",
    "close_detached",
    # 2026-09-21: a note window's PDF panel claims/releases the paper it
    # shows, so the same paper cannot be edited in two windows.
    "set_panel_paper",
    # 2026-10-29: a project's references exported to a file the user picks.
    "save_text_file",
}

# The single method app.js probes to decide pywebview-vs-browser mode.
BRIDGE_SNIFF_METHOD = "open_detached"


@pytest.fixture(scope="module")
def bridge_cls():
    """Load launcher.py by path. It is not importable as `launcher`
    from the tests package, and it has no import-time side effects —
    main() is guarded by `if __name__ == "__main__"`."""
    spec = importlib.util.spec_from_file_location(
        "corpus_launcher", _DEV_ROOT / "launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._Bridge


def _js_bridge_calls() -> set[str]:
    """Every `window.pywebview.api.<name>` referenced in shipped JS.
    dev_only/ is excluded — it is stripped from shipped builds."""
    found = set()
    for js in sorted(_SRC.glob("*.js")):
        for m in re.finditer(r"pywebview\.api\.([A-Za-z_][A-Za-z0-9_]*)",
                             js.read_text(encoding="utf-8")):
            found.add(m.group(1))
    return found


def test_every_js_bridge_call_exists_on_the_python_bridge(bridge_cls):
    """Catches: renaming or deleting a `_Bridge` method in launcher.py
    without updating the JS that calls it.

    This is the failure the empty `catch (_) {}` blocks hide. Without
    this test the only detector is a human clicking Pop out and
    noticing nothing happened."""
    missing = sorted(name for name in _js_bridge_calls()
                     if not hasattr(bridge_cls, name))
    assert not missing, (
        f"JS calls pywebview.api methods that _Bridge does not define: {missing}")


def test_js_calls_exactly_the_expected_bridge_surface():
    """Catches: a new `pywebview.api.*` call appearing in JS without
    the corresponding Python method being added AND this contract
    being updated deliberately.

    Fails loudly on an unlisted method rather than letting the pair
    drift silently."""
    assert _js_bridge_calls() == EXPECTED_BRIDGE_METHODS


def test_python_bridge_exposes_exactly_the_expected_surface(bridge_cls):
    """Catches: a public `_Bridge` method being added or removed
    without updating this contract. Public here means callable from
    JS — pywebview exposes every non-underscore attribute."""
    public = {n for n in dir(bridge_cls)
              if not n.startswith("_") and callable(getattr(bridge_cls, n))}
    assert public == EXPECTED_BRIDGE_METHODS


def test_app_js_sniffs_a_method_that_actually_exists(bridge_cls):
    """Catches: app.js probing for a bridge method that no longer
    exists, which silently routes every pywebview user down the
    browser `window.open` fallback instead of opening a native window.

    Asserts both that the sniffed name is still present in app.js and
    that _Bridge still defines it."""
    app_js = (_SRC / "app.js").read_text(encoding="utf-8")
    assert f"pywebview.api.{BRIDGE_SNIFF_METHOD}" in app_js, (
        f"app.js no longer sniffs for {BRIDGE_SNIFF_METHOD}; update "
        f"BRIDGE_SNIFF_METHOD here to match the new probe.")
    assert hasattr(bridge_cls, BRIDGE_SNIFF_METHOD)


def test_open_detached_rejects_empty_slug(bridge_cls):
    """Catches: dropping the falsy-slug guard. An empty slug would be
    stored as a key in the `_detached` map, so the close/focus lookups
    could collide across papers."""
    assert bridge_cls().open_detached("", "http://x", "t") == "error"


def test_focus_and_close_return_false_for_unknown_slug(bridge_cls):
    """Catches: these returning None (or raising) instead of False for
    a paper that isn't popped out. The JS treats the return value as a
    boolean when deciding whether to fall back to its own window
    tracking."""
    b = bridge_cls()
    assert b.focus_detached("not-open-2020") is False
    assert b.close_detached("not-open-2020") is False


def test_fresh_bridge_tracks_no_windows(bridge_cls):
    """Catches: `_detached` being made a class attribute instead of an
    instance attribute — a classic Python mutable-default bug that
    would leak popped-out window state between _Bridge instances."""
    a, b = bridge_cls(), bridge_cls()
    a._detached["x"] = object()
    assert b._detached == {}



def test_save_text_file_writes_where_the_user_chose(bridge_cls, tmp_path, monkeypatch):
    """Catches the export reporting "saved" without writing, writing to a
    path the user did not pick, or crashing on a cancelled dialog."""
    import sys, types
    target = tmp_path / "out.txt"
    calls = []
    win = types.SimpleNamespace(create_file_dialog=lambda kind, save_filename=None:
                                (calls.append(save_filename) or str(target)))
    fake = types.SimpleNamespace(windows=[win], FileDialog=types.SimpleNamespace(SAVE=30))
    monkeypatch.setitem(sys.modules, "webview", fake)
    b = bridge_cls()
    assert b.save_text_file("../../evil/refs.txt", "A. (2020). Title.") == "saved"
    assert target.read_text(encoding="utf-8") == "A. (2020). Title."
    assert calls == ["refs.txt"], "only a bare file name is suggested"
    win.create_file_dialog = lambda kind, save_filename=None: None
    assert b.save_text_file("refs.txt", "x") == "cancelled"
