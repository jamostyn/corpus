"""The frontend is served with fixed content types, whatever the OS says.

Jack, 2026-09-29, on the Windows build: "the windows pdf viewer is
completely black. it shows the controls but no PDF". Flask takes each
static file's type from `mimetypes`, which on Windows is patched from the
registry; a registry that maps `.mjs` / `.js` to `text/plain` makes the
browser refuse pdf.js's ES modules while the classic-script main app keeps
working. `server.WEB_MIME_TYPES` pins the types. These tests simulate the
hostile registry with `mimetypes.add_type`, which is exactly what
`read_windows_registry` does on Windows.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

import pytest

import server

SRC = Path(server._SRC)

# Extensions a browser REFUSES to use when the type is wrong: module and
# classic scripts, stylesheets, the viewer page, SVG images, WebAssembly.
# Fonts, cmaps and locale files are fetched as bytes and do not care.
BROWSER_ENFORCED = {".js", ".mjs", ".css", ".html", ".svg", ".wasm"}

VIEWER_MODULES = [
    "/vendor/pdfjs/build/pdf.mjs",
    "/vendor/pdfjs/build/pdf.worker.mjs",
    "/vendor/pdfjs/web/viewer.mjs",
]


@pytest.fixture
def hostile_registry():
    """Map every pinned extension to text/plain, the way a bad Windows
    registry does, and restore the pins afterwards so no other test sees
    the damage."""
    for ext in server.WEB_MIME_TYPES:
        mimetypes.add_type("text/plain", ext)
    yield
    server.pin_web_mime_types()


def _type(client, url):
    r = client.get(url)
    try:
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        return r.headers["Content-Type"].split(";")[0]
    finally:
        r.close()


def test_pdfjs_modules_are_javascript_even_when_the_registry_says_text_plain(
        client, hostile_registry):
    """Catches the Windows black-viewer bug: without the pin, these come
    back `text/plain` and the browser will not run them."""
    server.pin_web_mime_types()   # what server import does on startup
    for url in VIEWER_MODULES:
        assert _type(client, url) == "text/javascript", url


def test_without_the_pin_the_registry_wins(client, hostile_registry):
    """Proves the simulation reproduces the failure, so the test above is
    testing something. If this starts failing, Flask stopped reading
    `mimetypes` and the hostile fixture no longer models Windows."""
    assert _type(client, VIEWER_MODULES[0]) == "text/plain"


def test_importing_the_server_pins_types_over_an_earlier_registry():
    """Catches deleting the import-time `pin_web_mime_types()` call. On
    Windows the registry is read before any request, so the pin must run
    at startup; a fresh interpreter models that order (registry first,
    then `import server`)."""
    import subprocess
    import sys
    code = (
        "import mimetypes, sys\n"
        "mimetypes.add_type('text/plain', '.mjs')\n"
        "mimetypes.add_type('text/plain', '.js')\n"
        f"sys.path.insert(0, {str(SRC.parent / 'python')!r})\n"
        "import server\n"
        "print(mimetypes.guess_type('a.mjs')[0], mimetypes.guess_type('a.js')[0])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True).stdout.split()
    assert out[-2:] == ["text/javascript", "text/javascript"]


def test_every_browser_enforced_extension_under_src_is_pinned():
    """Catches adding a new kind of asset (say a `.wasm` pdf.js decoder)
    without pinning its type — it would work on macOS and break only on
    some Windows machines."""
    shipped = {p.suffix.lower() for p in SRC.rglob("*")
               if p.is_file() and "dev_only" not in p.parts}
    missing = (shipped & BROWSER_ENFORCED) - set(server.WEB_MIME_TYPES)
    assert not missing, f"unpinned browser-enforced types: {sorted(missing)}"


def test_pins_hold_real_javascript_types():
    """Catches a typo in the table itself (e.g. `text/js`), which would
    break every platform at once."""
    for ext in (".js", ".mjs"):
        assert server.WEB_MIME_TYPES[ext] == "text/javascript"
    assert mimetypes.guess_type("x.mjs")[0] == "text/javascript"
