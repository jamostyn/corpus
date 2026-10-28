"""Corpus launcher — boots the Flask server + opens a pywebview window.

Falls back to a browser tab if pywebview isn't installed (or fails on
this platform). Ctrl-C stops the server.

Run:
    python3 launcher.py
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# In a PyInstaller bundle, sys.frozen is True and sys._MEIPASS points
# to the unpacked resources dir. The Python code lives inside the pyz
# archive PyInstaller builds, so we don't need to touch sys.path —
# PyInstaller wires it up for us. server.py adds its own extract/
# path insert either way.
if not getattr(sys, "frozen", False):
    _HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(_HERE / "python"))

import server as srv  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def _address_recorder():
    """`dev_only.server_address`, or None in a shipped build.

    Imported lazily and guarded twice — by IS_DEV and by ImportError —
    because PyInstaller strips the package it lives in, and a missing
    convenience file must never stop the app from starting.
    """
    if not getattr(srv, "IS_DEV", False):
        return None
    try:
        from dev_only import server_address
        return server_address
    except Exception:
        return None


def _pick_ephemeral_port() -> int:
    """Ask the OS for a free port. Race-free enough for a single-user app."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Bridge:
    """pywebview `js_api` — methods here become callable from browser JS as
    `window.pywebview.api.<method>()`. Used for native OS dialogs the
    browser sandbox can't do (folder picker) + multi-window management
    for the Pop-out feature."""

    def __init__(self) -> None:
        self._main_window = None
        # slug → pywebview Window ref for popped-out PDF viewers.
        # Kept here (not in the browser JS) so we can detect close from
        # the Cocoa side and notify the main window's JS to re-render.
        self._detached: dict[str, object] = {}
        # note key ("note:<id>") -> slug shown in that note window's PDF
        # panel. The panel is an editor (highlights save from it), so a
        # paper in a panel must not also be open anywhere else.
        #
        # Kept HERE because this is the only process that sees every
        # window. Each window's JS state is private to that window — the
        # note window cannot see what the main window has open, nor the
        # reverse — so a lock held in any one window's JS protects nothing.
        self._panel_papers: dict[str, str] = {}

    def _set_main_window(self, w) -> None:
        self._main_window = w

    def _tell_main(self, event: str, detail: dict) -> None:
        """Dispatch a CustomEvent in the main window's JS."""
        mw = self._main_window
        if mw is None:
            return
        js = (f"window.dispatchEvent(new CustomEvent({json.dumps(event)}, "
              f"{{detail: {json.dumps(detail)}}}))")
        try:
            mw.evaluate_js(js)
        except Exception:
            pass

    # ---- Note-window PDF panel: one editor per paper -----------------

    def set_panel_paper(self, note_key: str, key: str | None) -> str:
        """Claim (or release, with key=None) a PDF for a note's panel.

        `key` is the same opaque "<kind>:<id>" as a pop-out window's —
        "paper:pan-2025-1" or "document:chapter-3". It was a bare paper
        slug until documents (2026-09-25) could open in the panel too;
        with two kinds, a bare id could not be compared against the
        pop-out windows, which are keyed "<kind>:<id>".

        Returns "ok", or "busy" when that PDF is already popped out in its
        own window or showing in ANOTHER note's panel. A paper open in one place
        cannot be opened in another, to prevent double editing.

        The main window is told either way, so its pane can lock. (The
        event field is still called `slug`; it carries the key.)
        """
        if not note_key:
            return "busy"
        if not key:
            self._panel_papers.pop(note_key, None)
            self._tell_main("corpus-panel-paper", {"note": note_key, "slug": None})
            return "ok"
        if key in self._detached:
            return "busy"
        for other, k in self._panel_papers.items():
            if k == key and other != note_key:
                return "busy"
        self._panel_papers[note_key] = key
        self._tell_main("corpus-panel-paper", {"note": note_key, "slug": key})
        return "ok"

    def _panel_holder(self, key: str) -> str | None:
        """The note key whose panel is showing `key` ("<kind>:<id>"), if any.

        Private on purpose: pywebview exposes every public method to JS,
        and tests/test_bridge_contract.py pins that surface exactly."""
        for note_key, k in self._panel_papers.items():
            if k == key:
                return note_key
        return None

    def pick_folder(self) -> str | None:
        try:
            import webview
            wins = webview.windows
            if not wins:
                return None
            # pywebview 6+ uses FileDialog.FOLDER; falls back to the old
            # FOLDER_DIALOG int for older releases.
            dialog_kind = getattr(getattr(webview, "FileDialog", None), "FOLDER",
                                  getattr(webview, "FOLDER_DIALOG", 20))
            result = wins[0].create_file_dialog(dialog_kind)
            if result:
                return result[0]
        except Exception:
            pass
        return None

    # ---- Pop-out: multi-window management -----------------------------

    def open_detached(self, slug: str, url: str, title: str) -> str:
        """Create a second pywebview window for the given paper's PDF.
        Returns 'opened' on success, 'focused' if the window was already
        open (existing window is raised), 'error' on failure.

        The main window's JS receives a `corpus-detached-closed` event
        when the popped-out window closes (see `_on_closed`)."""
        if not slug:
            return "error"
        # A paper already showing in a note window's panel is being edited
        # there; popping it out as well would give it two editors.
        if self._panel_holder(slug):
            return "busy"
        existing = self._detached.get(slug)
        if existing is not None:
            try:
                existing.show()
            except Exception:
                pass
            return "focused"
        try:
            import webview
            w = webview.create_window(
                title, url, js_api=self,
                width=1200, height=900, resizable=True, text_select=True,
            )
            def _on_closed(_slug=slug):
                self._detached.pop(_slug, None)
                # A closing note window releases whatever paper its panel
                # held — otherwise that paper stays locked until restart.
                if _slug in self._panel_papers:
                    self._panel_papers.pop(_slug, None)
                    self._tell_main("corpus-panel-paper", {"note": _slug, "slug": None})
                mw = self._main_window
                if mw is not None:
                    js = (
                        "window.dispatchEvent(new CustomEvent('corpus-detached-closed', "
                        f"{{detail: {{slug: {json.dumps(_slug)}}}}}))"
                    )
                    try:
                        mw.evaluate_js(js)
                    except Exception:
                        pass
            try:
                w.events.closed += _on_closed
            except Exception:
                pass
            self._detached[slug] = w
            return "opened"
        except Exception:
            return "error"

    def focus_detached(self, slug: str) -> bool:
        """Bring an already-popped-out window to the front. On macOS
        pywebview .show() raises + activates the window."""
        w = self._detached.get(slug)
        if w is None:
            return False
        try:
            w.show()
            return True
        except Exception:
            return False

    def close_detached(self, slug: str) -> bool:
        """Programmatically close a popped-out window. The window's
        `closed` event will then fire `_on_closed`, which cleans up
        state and posts the close event to the main window's JS."""
        w = self._detached.get(slug)
        if w is None:
            return False
        try:
            w.destroy()
            return True
        except Exception:
            return False


def _run_server(port: int, ws) -> None:
    """Serve Flask in a daemon thread."""
    ws.serve_forever()


def main() -> int:
    # Initialize server state (reads persisted config, applies to env,
    # sets corpus root). Explicit call — used to be an import-time
    # side effect, but that leaked user config into tests.
    srv.init_app()
    port = _pick_ephemeral_port()
    ws = make_server("127.0.0.1", port, srv.app, threaded=True)
    t = threading.Thread(target=_run_server, args=(port, ws), daemon=True)
    t.start()

    url = f"http://127.0.0.1:{port}"

    # Write the address down so anything outside the window can reach
    # the API — `/api/progress` in particular, which knows exactly which
    # phase a long import is on. The port is ephemeral and was recorded
    # nowhere before this, so that endpoint was unreachable in practice.
    # Dev only: `python/dev_only/` is stripped from the ship.
    _addr = _address_recorder()
    if _addr:
        _addr.write(port)

    # Try pywebview first (native shell). If it's not installed / fails,
    # fall back to opening the URL in the user's default browser.
    try:
        import webview
        bridge = _Bridge()
        srv.set_bridge(bridge)
        main_win = webview.create_window(
            "Corpus",
            url,
            width=1200,
            height=800,
            resizable=True,
            js_api=bridge,
            # pywebview defaults text_select to False, which disables
            # selection in the WKWebView across the entire app —
            # abstracts, refs, metadata all become uncopyable. Turn it
            # on so users can select + copy anything. Individual
            # elements that shouldn't be selectable (topbar, sidebar
            # rows) still opt out via `user-select: none` in styles.css.
            text_select=True,
        )
        # Give the bridge a handle back to the main window so it can
        # evaluate JS in it when a popped-out window closes (see
        # `_Bridge.open_detached._on_closed`).
        bridge._set_main_window(main_win)
        webview.start()
        # webview.start() returns when the last window closes.
        ws.shutdown()
        if _addr:
            _addr.clear()
        return 0
    except Exception as e:
        # Browser fallback path.
        print(f"[launcher] pywebview unavailable ({type(e).__name__}: {e})", file=sys.stderr)
        print(f"[launcher] opening in default browser: {url}", file=sys.stderr)
        # Small delay so Flask is definitely serving before the browser hits it.
        time.sleep(0.3)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(f"Corpus running at {url}  — Ctrl-C to stop", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[launcher] shutting down", flush=True)
            ws.shutdown()
            if _addr:
                _addr.clear()
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
