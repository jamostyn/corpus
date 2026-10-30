"""Pop-outs open as windows, not macOS tabs (launcher._disable_window_tabbing).

Reported 2026-10-28: in full screen, a popped-out note joined the main
window as a tab under a native tab bar with no space above it. Corpus
cannot style that bar, so it turns macOS's automatic tabbing off.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _launcher():
    spec = importlib.util.spec_from_file_location("corpus_launcher_tabbing", _ROOT / "launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_appkit(calls):
    ns = types.SimpleNamespace(setAllowsAutomaticWindowTabbing_=lambda v: calls.append(v))
    return types.SimpleNamespace(NSWindow=ns)


def test_tabbing_is_switched_off_on_macos(monkeypatch):
    """Catches the call being dropped or passed True: pop-outs would merge
    into the main window as tabs again."""
    L = _launcher()
    calls = []
    monkeypatch.setattr(L.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", _fake_appkit(calls))
    assert L._disable_window_tabbing() is True
    assert calls == [False]


def test_other_platforms_and_a_missing_appkit_are_left_alone(monkeypatch):
    """Catches a crash at launch on Windows, or on a Mac where AppKit
    cannot be imported — the app must still open."""
    L = _launcher()
    calls = []
    monkeypatch.setitem(sys.modules, "AppKit", _fake_appkit(calls))
    monkeypatch.setattr(L.sys, "platform", "win32")
    assert L._disable_window_tabbing() is False and calls == []
    monkeypatch.setattr(L.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", None)   # import raises
    assert L._disable_window_tabbing() is False


def test_it_runs_before_any_window_is_created():
    """Catches it moving after create_window: macOS decides tabbing when a
    window opens, so the main window would already allow tabs."""
    src = (_ROOT / "launcher.py").read_text(encoding="utf-8")
    main = src[src.index("def main()"):]
    assert main.index("_disable_window_tabbing()") < main.index("webview.create_window(")
