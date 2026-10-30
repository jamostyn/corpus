"""When the app window cannot open (python/window_fallback.py, launcher.py).

Requirement (2026-10-30): a Windows build that opened as its own window
on the PC that built it opened in a browser on another PC, with no
reason given. Downloaded files are unblocked before the window opens, and
when it still fails the browser page says why. Every test names the
mistake it catches.
"""
from __future__ import annotations

import re
from pathlib import Path

import config_api
import window_fallback as W

ROOT = Path(__file__).resolve().parent.parent


def test_only_code_files_are_unblocked_and_failures_are_skipped(tmp_path):
    """Catches the download mark left on the .NET bridge's DLLs (or on
    .pyd extensions, upper-case suffixes, files in subfolders), every data
    file being touched, or one unchangeable file stopping the launch."""
    for name in ("Python.Runtime.dll", "_internal/clr_loader/ffi/x.DLL", "_internal/a.pyd",
                 "Corpus.exe", "_internal/src/app.js", "_internal/LICENSE", "_internal/locked.dll"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x")
    asked = []

    def remove(path):
        asked.append(Path(path).relative_to(tmp_path).as_posix())
        if "locked" in path:
            raise PermissionError(path)

    assert W.unblock_downloaded_files(tmp_path, remove=remove) == 4   # the locked one is skipped
    assert sorted(asked) == sorted(f"{n}:Zone.Identifier" for n in (
        "Python.Runtime.dll", "_internal/clr_loader/ffi/x.DLL", "_internal/a.pyd",
        "Corpus.exe", "_internal/locked.dll"))


def test_a_missing_webview2_is_told_apart_from_other_failures():
    """Catches every failure being reported as "install WebView2" (wrong
    advice for a blocked DLL), or the WebView2 case — pywebview reaching
    for its unbundled Internet Explorer renderer — not being recognised."""
    miss = W.window_error_notice(ModuleNotFoundError("No module named 'webview.platforms.mshtml'"))
    assert miss["reason"] == "webview2_missing"
    blocked = W.window_error_notice(RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize"))
    assert blocked == {"reason": "window_failed",
                       "detail": "RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize"}


def test_the_config_endpoint_reports_the_window_error(client, monkeypatch):
    """Catches the launcher's notice never reaching the page (the bar then
    never shows), or a normal window launch reporting an error."""
    assert client.get("/api/config").get_json()["window_error"] is None
    monkeypatch.setattr(config_api, "_window_error", None)
    import server
    server.set_window_error({"reason": "window_failed", "detail": "x"})
    assert client.get("/api/config").get_json()["window_error"] == {"reason": "window_failed", "detail": "x"}


def test_the_launcher_unblocks_first_and_reports_before_the_browser_opens():
    """Catches the unblock running after pywebview has loaded its bridge
    (too late), running outside the Windows build, or the notice being set
    after the browser has already read the config."""
    src = (ROOT / "launcher.py").read_text(encoding="utf-8")
    main = src[src.index("def main("):]
    guard = main.index('if sys.platform == "win32" and getattr(sys, "frozen", False):')
    unblock = main.index("unblock_downloaded_files(Path(sys.executable).parent)")
    assert guard < unblock < main.index("import webview")
    fallback = main[main.index("except Exception as e:"):]
    assert fallback.index("srv.set_window_error(") < fallback.index("webbrowser.open(url)")


def test_the_shipped_build_includes_the_module_and_the_page_mounts_the_bar():
    """Catches PyInstaller leaving window_fallback out (the launcher's
    import then fails inside the fallback itself), or the page losing the
    bar or loading its script after app.js uses it."""
    spec = (ROOT / "pyinstaller_corpus.spec").read_text(encoding="utf-8")
    assert re.search(r"'window_fallback'", spec)
    html = (ROOT / "src" / "index.html").read_text(encoding="utf-8")
    assert 'id="window-notice"' in html
    assert html.index('src="window-notice.js"') < html.index('src="app.js"')
    assert "WindowNotice.show(state.config.window_error)" in (ROOT / "src" / "app.js").read_text(encoding="utf-8")
