"""Windows build path: the dual-platform spec and the source bundle.

PyInstaller cannot cross-compile, so the Windows .exe is built on
Windows from `Corpus-v<version>-windows-src.zip`. That makes the zip's
CONTENTS the contract: a missing file surfaces as a confusing
PyInstaller error on someone else's machine, hours later, with no
context. These tests check the contract here instead.

NOT COVERED, and it cannot be from macOS: whether `build_windows.bat`
actually produces a working Corpus.exe. That needs a Windows machine.
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

_DEV = Path(__file__).resolve().parent.parent
_SPEC = _DEV / "pyinstaller_corpus.spec"


def _load_build_ship():
    spec = importlib.util.spec_from_file_location("corpus_build_ship",
                                                  _DEV / "build_ship.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Stub(dict):
    """Stands in for PyInstaller's Analysis/EXE/etc. return values."""
    def __getattr__(self, name):
        return _Stub()


def _eval_spec(platform: str) -> dict:
    """Execute the spec file with a faked `sys.platform`.

    The spec is normally run by PyInstaller, which injects Analysis,
    PYZ, EXE, COLLECT and BUNDLE as globals. Stubbing them lets the
    platform branching be exercised without a two-minute build."""
    src = _SPEC.read_text(encoding="utf-8").replace("import sys\n", "")

    class FakeSys:
        pass
    FakeSys.platform = platform

    ns = {
        "Analysis": lambda *a, **k: _Stub(k),
        "PYZ":      lambda *a, **k: _Stub(),
        "EXE":      lambda *a, **k: _Stub(k),
        "COLLECT":  lambda *a, **k: _Stub(),
        "BUNDLE":   lambda *a, **k: _Stub(k),
        "sys":      FakeSys(),
    }
    import os
    cwd = os.getcwd()
    os.chdir(_DEV)          # _collect_frontend walks a relative 'src'
    try:
        exec(compile(src, "pyinstaller_corpus.spec", "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns


# ---------- the dual-platform spec ----------

def test_spec_selects_the_right_icon_per_platform():
    """Catches: hardcoding one platform's icon.

    PyInstaller refuses an .icns on Windows and vice versa, so a wrong
    icon is a hard build failure — but only on the platform nobody is
    testing on."""
    assert _eval_spec("darwin")["exe"]["icon"].endswith(".icns")
    assert _eval_spec("win32")["exe"]["icon"].endswith(".ico")


def test_bundle_is_macos_only():
    """Catches: leaving BUNDLE unconditional.

    BUNDLE produces a .app and references the .icns. On Windows it
    would fail on a file that platform's build does not even ship."""
    assert _eval_spec("darwin")["app"] is not None
    assert _eval_spec("win32")["app"] is None


def test_each_platform_gets_its_own_webview_and_keyring_backends():
    """Catches: shipping only the macOS backends.

    pywebview and keyring both discover backends via entry_points,
    which PyInstaller's static walker cannot follow. Omitting them
    produces a bundle that BUILDS cleanly and then dies at launch with
    no window or no saved API keys — the worst failure shape, because
    the build looks successful."""
    mac = _eval_spec("darwin")["a"]["hiddenimports"]
    win = _eval_spec("win32")["a"]["hiddenimports"]

    assert "webview.platforms.cocoa" in mac
    assert "keyring.backends.macOS" in mac
    assert "webview.platforms.edgechromium" in win
    assert "keyring.backends.Windows" in win

    # And each must NOT carry the other's — a stale cocoa import on
    # Windows is a warning, but it signals the branch was not applied.
    assert "webview.platforms.edgechromium" not in mac
    assert "webview.platforms.cocoa" not in win


def test_dev_only_stays_excluded_on_both_platforms():
    """Catches: the Windows branch skipping the dev_only exclusions.

    The bug reporter, planning modal and tooltip editor must not reach
    a user on either platform."""
    for platform in ("darwin", "win32"):
        ns = _eval_spec(platform)
        assert "dev_only" in ns["a"]["excludes"], platform
        datas = ns["a"]["datas"]
        assert not any("dev_only" in str(d) for d in datas), platform


# ---------- the source bundle ----------

@pytest.fixture(scope="module")
def staged() -> Path:
    """Stage the Windows source tree once, into a temp dir."""
    bs = _load_build_ship()
    tmp = Path(tempfile.mkdtemp()) / "stage"
    tmp.mkdir(parents=True)
    bs._stage_windows_source("0.0.0-test", tmp)
    bs._verify_windows_source(tmp)
    yield tmp
    shutil.rmtree(tmp.parent, ignore_errors=True)


def _rel_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_bundle_carries_every_build_input(staged):
    """Catches: dropping a file the Windows build needs.

    Each of these is load-bearing: the .bat is the entry point, the
    spec is the recipe, launcher.py is the program, the requirements
    files are the dependency list, and the .ico is what the spec's
    Windows branch points at. A missing one fails on a tester's machine
    with a PyInstaller traceback, not here."""
    files = _rel_files(staged)
    for required in ("build_windows.bat", "pyinstaller_corpus.spec",
                     "launcher.py", "requirements.txt",
                     "requirements-build.txt", "dist_assets/Corpus.ico",
                     "python/_version.py", "python/server.py",
                     "src/index.html"):
        assert required in files, f"missing from the Windows bundle: {required}"


def _pdfjs_runtime_files() -> list[str]:
    """Every pdf.js file the viewer loads by URL, read from the viewer's
    own source rather than listed by hand, so a new module script or a
    moved worker is picked up without editing this test."""
    import re
    web = _DEV / "src" / "vendor" / "pdfjs" / "web"
    html = (web / "viewer.html").read_text(encoding="utf-8")
    urls = re.findall(r'<script src="([^"]+)" type="module"', html)
    mjs = (web / "viewer.mjs").read_text(encoding="utf-8")
    worker = re.search(r'workerSrc: \{\s*value: "([^"]+)"', mjs)
    assert urls and worker, "viewer.html / viewer.mjs layout changed; update the parser"
    urls.append(worker.group(1))
    return [(web / u).resolve().relative_to(_DEV).as_posix() for u in urls]


def test_bundle_carries_the_pdf_viewer_modules(staged):
    """Catches: pruning pdf.js out of the Windows bundle.

    `build` was in the prune set (meant for PyInstaller output) and
    matched `src/vendor/pdfjs/build/` by name, so v0.2.0–v0.4.1 shipped
    without pdf.mjs and its worker. The app built and opened; only the
    viewer was dead, reporting `pdf.mjs: HTTP 404` (seen on Windows,
    2026-10-15)."""
    files = _rel_files(staged)
    needed = _pdfjs_runtime_files()
    assert "src/vendor/pdfjs/build/pdf.mjs" in needed      # parser sanity
    for rel in needed:
        assert rel in files, f"missing from the Windows bundle: {rel}"


def test_verify_rejects_a_bundle_with_a_dropped_file(staged):
    """Catches: the verifier only checking for leaks, not losses.

    An over-broad prune removed a whole directory and the verifier,
    which looked only for things that should NOT be there, passed it.
    Dropping any one source file must now fail the build."""
    bs = _load_build_ship()
    tmp = Path(tempfile.mkdtemp()) / "stage"
    try:
        shutil.copytree(staged, tmp)
        (tmp / "src" / "vendor" / "pdfjs" / "build" / "pdf.worker.mjs").unlink()
        with pytest.raises(SystemExit, match="dropped"):
            bs._verify_windows_source(tmp)
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def test_no_runtime_source_is_git_ignored():
    """Catches: a .gitignore pattern that swallows shipped source.

    The same unanchored `build/` in .gitignore kept pdf.mjs out of git,
    so no release tag could rebuild the app it named. Caches and OS
    junk are the only files under the shipped directories git may
    ignore."""
    import subprocess
    if shutil.which("git") is None or not (_DEV / ".git").exists():
        pytest.skip("not a git checkout")
    bs = _load_build_ship()
    out = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard",
         *bs.WINDOWS_SRC_DIRS],
        cwd=_DEV, capture_output=True, text=True, check=True).stdout.split("\n")
    junk = ("__pycache__/", ".DS_Store", ".pyc")
    ignored = [f for f in out if f and not any(j in f for j in junk)]
    assert not ignored, f"git ignores shipped source: {ignored[:10]}"


def test_bundle_does_not_leak_dev_or_private_material(staged):
    """Catches: shipping dev-only surfaces, the venv, git history, or a
    corpus someone left in the repo.

    This zip goes to testers. `dev_only/` mirrors the spec's own
    exclusion; the rest is build noise that would bloat the zip and, in
    `.git`'s case, hand over the entire project history."""
    files = _rel_files(staged)
    for banned in ("dev_only", "__pycache__", ".venv", ".git",
                   "tests/", "summaries/", "papers/"):
        offenders = [f for f in files if banned in f]
        assert not offenders, f"{banned} leaked: {offenders[:5]}"


def test_the_staged_spec_is_the_same_one_the_mac_build_uses(staged):
    """Catches: the bundle carrying a forked or stale copy of the spec.

    One spec for both platforms is the whole design — a second copy
    would drift the moment a hidden import is added, and the drift
    would only show up on Windows."""
    assert (staged / "pyinstaller_corpus.spec").read_bytes() == _SPEC.read_bytes()


def test_zip_has_a_single_top_level_folder():
    """Catches: a zip that scatters files across the user's Downloads
    when double-clicked."""
    bs = _load_build_ship()
    tmp = Path(tempfile.mkdtemp())
    try:
        bs.SHIP_ROOT = tmp
        z = bs._zip_windows_source("0.0.0-test")
        with zipfile.ZipFile(z) as zf:
            roots = {n.split("/")[0] for n in zf.namelist()}
        assert roots == {"Corpus-v0.0.0-test-windows-src"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_release_immutability_covers_the_windows_zip():
    """Catches: gate D guarding only the mac artifact.

    A released Windows source zip is as immutable as the .app zip — a
    tester handed it must be able to rebuild the same bits. Before this,
    gate D checked one filename."""
    src = (_DEV / "build_ship.py").read_text(encoding="utf-8")
    fn = src[src.index("def _gate_zip_not_released"):
             src.index("def _preflight")]
    assert "windows-src" in fn, (
        "gate D must check the Windows source zip too")


def test_batch_file_uses_the_shipped_requirements_not_a_hardcoded_list():
    """Catches: the .bat pinning its own dependency list.

    A second copy of the dependency set drifts from requirements.txt
    silently, and the Windows build would install the wrong versions."""
    bat = (_DEV / "build_windows.bat").read_text(encoding="utf-8")
    assert "-r requirements.txt" in bat
    assert "-r requirements-build.txt" in bat


def test_the_ship_readme_gives_the_same_mac_first_launch_step_as_the_readme(tmp_path, monkeypatch):
    """Catches the ship README.txt telling testers "right-click -> Open",
    which current macOS no longer offers for an unsigned app, while
    README.md says System Settings -> Open Anyway."""
    bs = _load_build_ship()
    monkeypatch.setattr(bs, "SHIP_ROOT", tmp_path)
    bs._write_ship_readme("9.9.9")
    ship = (tmp_path / "README.txt").read_text(encoding="utf-8")
    assert "Open Anyway" in ship and "right-click" not in ship.lower()
    assert "Open Anyway" in (_DEV / "README.md").read_text(encoding="utf-8")
