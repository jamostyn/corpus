"""When the app window cannot open: unblock downloaded files, and say why.

Corpus opens its own window through pywebview; if that fails, the
launcher serves the same app in the default browser instead. On Windows
two causes are common, and neither is visible to the user because a
windowed .exe has no console for the error:

  * Files extracted from a downloaded zip carry Windows' "downloaded from
    the internet" mark (an NTFS `Zone.Identifier` stream). .NET refuses
    to load a marked DLL, so pywebview's .NET bridge (pythonnet) fails.
    A build run on the PC that compiled it has no marks and works.
  * The Microsoft Edge WebView2 Runtime is not installed. pywebview then
    tries its old Internet Explorer renderer (`mshtml`), which Corpus
    does not bundle.

`unblock_downloaded_files` removes the mark from Corpus's own program
files before the window is created (what Explorer's "Unblock" does).
`window_error_notice` turns the failure into what the browser page shows.
"""
from __future__ import annotations

import os
from pathlib import Path

# Only files Windows loads as code are checked; the mark on data files
# is harmless and there are thousands of them.
CODE_SUFFIXES = frozenset({".dll", ".exe", ".pyd"})
ZONE_STREAM = ":Zone.Identifier"


def unblock_downloaded_files(root: Path, remove=os.remove) -> int:
    """Remove the download mark from every code file under `root`.
    Returns how many were removed. Files without a mark, or that cannot
    be changed (a read-only install), are skipped."""
    removed = 0
    for p in Path(root).rglob("*"):
        if p.suffix.lower() not in CODE_SUFFIXES or not p.is_file():
            continue
        try:
            remove(str(p) + ZONE_STREAM)
            removed += 1
        except OSError:
            continue
    return removed


def window_error_notice(exc: BaseException) -> dict:
    """{"reason", "detail"} for the browser page. `reason` is
    "webview2_missing" when the failure is pywebview reaching for the
    Internet Explorer renderer it falls back to without WebView2;
    otherwise "window_failed"."""
    detail = f"{type(exc).__name__}: {exc}"
    low = detail.lower()
    reason = "webview2_missing" if ("mshtml" in low or "webview2" in low) else "window_failed"
    return {"reason": reason, "detail": detail[:500]}
