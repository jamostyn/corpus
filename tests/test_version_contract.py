"""`python/_version.py` is the single source of truth for the version.

Three consumers read it, and they must never disagree:
  * `config_api.get_version`  -> GET /api/version, shown in the UI
  * `build_ship.py`           -> names the release zip Corpus-v<v>.zip
                                 and gates on a matching CHANGELOG section
  * `pyinstaller_corpus.spec` -> stamps the .app bundle

A drift between them means a user's "About" string, their .app, and the
zip filename disagree about what they are running — which is the exact
question the dev/ship split exists to answer.
"""
from __future__ import annotations

import re
from pathlib import Path

_DEV_ROOT = Path(__file__).resolve().parent.parent
_VERSION_PY = _DEV_ROOT / "python" / "_version.py"


def test_version_endpoint_returns_the_module_version(client, corpus_dir):
    """Catches: /api/version returning a hard-coded string, or being
    wired to something other than _version.__version__.

    Also catches the route being dropped outright — the route list in
    test_server_boot.py did not include /api/version, so before this
    test it could have vanished unnoticed."""
    from _version import __version__
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.get_json() == {"version": __version__}


def test_version_module_is_trivially_parseable():
    """Catches: adding imports or logic to _version.py.

    build_ship.py and pyinstaller_corpus.spec both read this file with
    `exec()` on its raw text, WITHOUT the package importable. Any
    import statement added here breaks the build with a confusing
    traceback far from the cause."""
    text = _VERSION_PY.read_text(encoding="utf-8")
    code = [ln for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    # Strip the module docstring (leading/trailing triple-quoted block).
    body = "\n".join(code)
    body = re.sub(r'^\s*""".*?"""\s*', "", body, flags=re.S)
    statements = [ln for ln in body.splitlines() if ln.strip()]
    assert len(statements) == 1, (
        f"_version.py should hold exactly one assignment; got: {statements}")
    assert statements[0].startswith("__version__"), statements[0]


def test_build_script_reads_the_same_version(client, corpus_dir):
    """Catches: build_ship.py's _read_version() drifting from the
    module the server serves — e.g. someone pointing it at a
    pyproject.toml or a hard-coded constant. A mismatch would ship
    Corpus-v0.2.0.zip containing an app that reports 0.1.1."""
    import importlib.util
    from _version import __version__

    spec = importlib.util.spec_from_file_location(
        "corpus_build_ship", _DEV_ROOT / "build_ship.py")
    bs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bs)
    assert bs._read_version() == __version__


def test_version_is_a_plain_dotted_release_string():
    """Catches: shipping a version still carrying a `-dev` suffix.

    build_ship.py gate C deliberately refuses to accept a
    `v<version>-dev` CHANGELOG entry as documenting release
    `<version>`. A `-dev` string in _version.py itself means the
    release zip would be named Corpus-v0.1.2-dev.zip. That is legal
    during development, so this test only asserts the shape is one of
    the two intended forms rather than banning `-dev` outright."""
    from _version import __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+(-dev)?", __version__), (
        f"unexpected version shape: {__version__!r}")
