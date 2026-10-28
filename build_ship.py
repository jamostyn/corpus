#!/usr/bin/env python3
"""Corpus ship builder — one command from source to a shippable zip.

Preflight gates (all must pass before anything is built):
  A. Dev git tree is clean — otherwise the shipped bits don't
     correspond to any commit, and "which version is the user running?"
     has no answer.
  B. Test suite is green.
  C. CHANGELOG.md has a section naming this exact version.
  D. The target zip is not already committed in the ship repo — a
     released artifact is immutable.

Then the build pipeline:
  1. Wipe prior build outputs (`dist/`, `build/`)
  2. Run PyInstaller against `pyinstaller_corpus.spec`
  3. Ad-hoc code-sign the .app (deterministic re-sign, even though
     PyInstaller signs during BUNDLE — this is idempotent + belt-
     and-braces)
  4. Write the tester README into `../ship/`
  5. Zip the .app into `../ship/Corpus-v<version>.zip` via `ditto`
     (macOS-native, preserves resource forks + xattrs)
  6. Zip the Windows BUILD SOURCE into
     `../ship/Corpus-v<version>-windows-src.zip`

Why two artifacts. PyInstaller cannot cross-compile, so a Windows .exe
must be built on Windows. Rather than shipping nothing for Windows, the
second zip carries the same source this build used plus
`build_windows.bat`, which sets up a venv and runs the same spec file.
The spec is dual-platform (see `IS_WINDOWS` in it) — one recipe, so the
hidden-import list cannot drift between platforms.

Reads the version from `python/_version.py`. Runs on macOS only (it
builds the .app); the Windows zip it produces is buildable anywhere.

Run from the `dev/` directory:
    .venv/bin/python build_ship.py

Only flag: `--skip-tests`, for iterating on bundling problems when the
suite has already been run this session. Gates A, C, and D have no
override — bypassing them would defeat the point of having them.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

DEV_ROOT   = Path(__file__).resolve().parent
SHIP_ROOT  = DEV_ROOT.parent / "ship"
SPEC_PATH  = DEV_ROOT / "pyinstaller_corpus.spec"
APP_PATH   = DEV_ROOT / "dist" / "Corpus.app"
CHANGELOG  = DEV_ROOT / "CHANGELOG.md"

# Everything the Windows build needs, and nothing else. Directories are
# copied wholesale minus the exclusions below; files are copied as-is.
#
# This list is deliberately EXPLICIT rather than "everything except a
# denylist". A denylist silently ships whatever new top-level directory
# someone adds (scratch dirs, notes, a corpus someone dropped in the
# repo); an allowlist fails loudly by omitting a file the build needs,
# which surfaces immediately as a build error on Jack's machine rather
# than as leaked data on a tester's.
WINDOWS_SRC_DIRS  = ["python", "src", "dist_assets"]
WINDOWS_SRC_FILES = [
    "launcher.py",
    "pyinstaller_corpus.spec",
    "build_windows.bat",
    "requirements.txt",
    "requirements-build.txt",
]

# Pruned from the copied directories, matched by NAME at every depth.
# `dev_only` mirrors the spec's own exclusion (see `_collect_frontend`
# and `excludes=` there) — a shipped build must not carry the bug
# reporter, planning modal or tooltip editor. The rest is VCS/cache
# noise.
#
# `build` and `dist` must NOT be here. PyInstaller's output dirs live at
# the dev root, outside every allowlisted directory, so they are never
# copied anyway — but a name match also hit `src/vendor/pdfjs/build/`,
# which holds pdf.mjs and its worker. Every Windows zip from v0.2.0 to
# v0.4.1 shipped without them, and the viewer never started on Windows.
WINDOWS_SRC_PRUNE = {
    "dev_only", "__pycache__", ".git", ".venv", ".pytest_cache", ".DS_Store",
}


def _read_version() -> str:
    """Single source of truth: `python/_version.py`."""
    ns: dict = {}
    exec((DEV_ROOT / "python" / "_version.py").read_text(), ns)
    return ns["__version__"]


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    """Run a shell command, print it first, raise on nonzero exit."""
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _fail(gate: str, problem: str, fix: str) -> None:
    """Stop the build with a message that says which gate tripped, what
    is wrong, and the exact way out. Raises SystemExit."""
    raise SystemExit(
        f"\nBUILD REFUSED — {gate}\n"
        f"  problem: {problem}\n"
        f"  fix:     {fix}\n"
    )


def _git(args: list[str], *, cwd: Path) -> str:
    """Run a git command and return stdout. Empty string if git fails
    (e.g. not a repo) — callers decide whether that's fatal."""
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd),
                           capture_output=True, text=True, check=True)
        return r.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


# ---------- Preflight gates ----------

def _gate_clean_tree() -> None:
    """Gate A — refuse to build from a dirty dev tree.

    A zip built from uncommitted edits corresponds to no commit, so
    there is no way to reconstruct exactly what a user is running.
    Untracked files count: `pyinstaller_corpus.spec` ships whatever is
    on disk under `src/`, not whatever is in git."""
    status = _git(["status", "--porcelain"], cwd=DEV_ROOT)
    if status.strip():
        n = len(status.strip().splitlines())
        _fail("gate A (clean git tree)",
              f"{n} uncommitted change(s) in {DEV_ROOT}",
              "commit or stash them, then re-run. `git status` to see them.")


def _gate_tests_green() -> None:
    """Gate B — refuse to build on a red test suite.

    Runs the suite with this same interpreter so it picks up the venv
    the build is running from."""
    print("\n$ pytest tests/ -q   (gate B)", flush=True)
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=str(DEV_ROOT))
    if r.returncode != 0:
        _fail("gate B (tests green)",
              f"pytest exited {r.returncode}",
              "fix the failures, or pass --skip-tests if you have already "
              "run them green this session and are only iterating on bundling.")


def _gate_changelog_section(version: str) -> None:
    """Gate C — refuse to build a version with no CHANGELOG section.

    Matches `v<version>` not followed by another version-ish character,
    so shipping `0.1.1` is NOT satisfied by a `v0.1.1-dev` entry. That
    exact case is why this gate exists: v0.1.1 shipped on 2026-08-19
    with only a `v0.1.1-dev` step-1 entry in the changelog, and the
    release's actual contents went unrecorded until 2026-08-24."""
    if not CHANGELOG.exists():
        _fail("gate C (changelog section)",
              f"{CHANGELOG} does not exist",
              f"create it with a section titled 'v{version} — <summary>'.")
    text = CHANGELOG.read_text(encoding="utf-8")
    if not re.search(rf"v{re.escape(version)}(?![\w.-])", text):
        _fail("gate C (changelog section)",
              f"CHANGELOG.md has no section naming v{version} "
              f"(a 'v{version}-dev' entry does not count)",
              f"add a section titled 'v{version} — <summary>' describing "
              f"what changed since the previous release.")


def _gate_zip_not_released(version: str) -> None:
    """Gate D — refuse to overwrite an already-released zip.

    A zip that is committed in the ship repo has been handed out; it is
    immutable. A zip sitting untracked in the ship working tree is just
    a build artifact from an aborted attempt — that one may be replaced,
    with a warning.

    Before this gate existed, `_zip_app` called `unlink()` on any
    existing zip, so re-running the build without bumping the version
    silently replaced a released artifact in place."""
    # Checks EVERY artifact this build produces. The Windows source zip
    # is as immutable as the .app zip once released: a tester who was
    # handed it must be able to rebuild the same bits.
    for name in (f"Corpus-v{version}.zip",
                 f"Corpus-v{version}-windows-src.zip"):
        zip_path = SHIP_ROOT / name
        if not zip_path.exists():
            continue
        tracked = _git(["ls-files", "--error-unmatch", name],
                       cwd=SHIP_ROOT).strip()
        if tracked:
            _fail("gate D (release immutability)",
                  f"{name} is already committed in the ship repo",
                  f"bump python/_version.py — v{version} has shipped and cannot "
                  f"be rebuilt in place. Fixes go into the next version.")
        print(f"  note: replacing uncommitted {name} "
              f"(build artifact, not a release)")


def _preflight(version: str, *, skip_tests: bool) -> None:
    print("\nPreflight")
    _gate_clean_tree()
    print("  gate A  clean git tree ....... ok")
    if skip_tests:
        print("  gate B  tests ............... SKIPPED (--skip-tests)")
    else:
        _gate_tests_green()
        print("  gate B  tests green ......... ok")
    _gate_changelog_section(version)
    print(f"  gate C  CHANGELOG v{version} ..... ok")
    _gate_zip_not_released(version)
    print("  gate D  release immutability  ok")


def _wipe_prior_builds() -> None:
    for d in ("dist", "build"):
        p = DEV_ROOT / d
        if p.exists():
            print(f"  removing {p}")
            shutil.rmtree(p)


def _pyinstaller_build() -> None:
    """Run PyInstaller via `python -m PyInstaller` so this works whether
    or not `pyinstaller` is on the shell's PATH — the module is always
    resolvable from the same interpreter that's running this script."""
    _run([sys.executable, "-m", "PyInstaller",
          str(SPEC_PATH), "--noconfirm", "--clean"])
    if not APP_PATH.exists():
        raise SystemExit(f"PyInstaller finished but {APP_PATH} was not produced.")


def _codesign_adhoc() -> None:
    """Ad-hoc re-sign — `-s -` is Apple's shorthand for `--sign -`, the
    empty identity. Idempotent; PyInstaller signed already during
    BUNDLE, but re-running here means any future post-BUNDLE tweak
    (e.g. patching Info.plist) still ends up signed."""
    _run(["codesign", "--deep", "--force", "-s", "-", str(APP_PATH)])
    # Verify.
    _run(["codesign", "--verify", "--deep", "--strict", str(APP_PATH)])


def _write_ship_readme(version: str) -> None:
    """Tester-facing instructions. Lives NEXT TO the zip in ../ship/,
    not INSIDE the zip — testers who download from a Drive folder see
    it before unzipping."""
    SHIP_ROOT.mkdir(exist_ok=True)
    readme = SHIP_ROOT / "README.txt"
    body = (
        f"Corpus v{version}\n"
        f"{'-' * (len('Corpus v') + len(version))}\n"
        f"\n"
        f"MAC — Corpus-v{version}.zip\n"
        f"\n"
        f"1. Unzip Corpus-v{version}.zip.\n"
        f"2. Drag Corpus.app to /Applications.\n"
        f"3. First launch only: right-click Corpus.app -> Open, then\n"
        f"   confirm the \"Apple cannot check for malicious software\"\n"
        f"   dialog. Regular double-click works after that.\n"
        f"4. First launch will ask where to keep your papers. Pick any\n"
        f"   folder (or an existing corpus dir if you're upgrading).\n"
        f"\n"
        f"WINDOWS — Corpus-v{version}-windows-src.zip\n"
        f"\n"
        f"There is no prebuilt Windows .exe: the build tool cannot make a\n"
        f"Windows app from a Mac. This zip builds one on your machine.\n"
        f"\n"
        f"1. Install Python 3.11+ from python.org (NOT the Microsoft Store\n"
        f"   version). Tick \"Add python.exe to PATH\" in the installer.\n"
        f"2. Unzip Corpus-v{version}-windows-src.zip.\n"
        f"3. Double-click build_windows.bat and wait a few minutes.\n"
        f"4. Run dist\\Corpus\\Corpus.exe. Keep that folder together.\n"
        f"   Windows SmartScreen may warn the app is unrecognised (it is\n"
        f"   unsigned): More info -> Run anyway.\n"
        f"\n"
        f"Bug reports: <address TBD>\n"
    )
    readme.write_text(body, encoding="utf-8")
    print(f"  wrote {readme}")


def _zip_app(version: str) -> Path:
    """`ditto -c -k --keepParent` = the macOS-native zipper that
    preserves the .app bundle's directory structure (and any resource
    forks or xattrs codesign put there). Plain `zip` on the CLI would
    destroy the signature."""
    zip_path = SHIP_ROOT / f"Corpus-v{version}.zip"
    # Safe to unlink: gate D already established this zip is either
    # absent or an uncommitted build artifact.
    if zip_path.exists():
        zip_path.unlink()
    _run(["ditto", "-c", "-k", "--keepParent", str(APP_PATH), str(zip_path)])
    return zip_path


def _stage_windows_source(version: str, staging: Path) -> None:
    """Copy the Windows build inputs into `staging`.

    Raises if anything on the allowlist is missing — a source zip that
    silently lacks a file produces a confusing PyInstaller failure on
    the user's Windows machine, hours later and with no context."""
    def _ignore(_dir, names):
        return {n for n in names if n in WINDOWS_SRC_PRUNE}

    for d in WINDOWS_SRC_DIRS:
        src = DEV_ROOT / d
        if not src.is_dir():
            raise SystemExit(f"windows source: missing directory {src}")
        shutil.copytree(src, staging / d, ignore=_ignore)
    for f in WINDOWS_SRC_FILES:
        src = DEV_ROOT / f
        if not src.is_file():
            raise SystemExit(f"windows source: missing file {src}")
        shutil.copy2(src, staging / f)

    # The icon the Windows spec branch points at. Generated from the
    # .icns on macOS (see docs/WINDOWS_BUILD.md); assert it made the cut
    # rather than letting PyInstaller fail on the user's machine.
    if not (staging / "dist_assets" / "Corpus.ico").is_file():
        raise SystemExit("windows source: dist_assets/Corpus.ico is missing — "
                         "regenerate it (see docs/WINDOWS_BUILD.md)")


def _verify_windows_source(staging: Path) -> None:
    """Fail the build if the staged tree carries anything it shouldn't,
    or lacks anything it should.

    Checked here rather than trusted from the prune set: `copytree`'s
    ignore callback only sees names at each level, so a nested
    `dev_only/` or a stray `.venv` deeper in the tree would slip past a
    top-level-only check. This walks the result."""
    # RELATIVE parts only. The staging dir itself lives under
    # `dev/build/windows-src/…`, so walking absolute `p.parts` matches
    # "build" for every single file and reports the whole tree as
    # leaked — which is exactly what happened the first time.
    leaked = []
    for p in staging.rglob("*"):
        rel = p.relative_to(staging)
        if any(part in WINDOWS_SRC_PRUNE for part in rel.parts):
            leaked.append(str(rel))
    if leaked:
        raise SystemExit("windows source: excluded files leaked into the "
                         f"bundle: {leaked[:10]}")

    # The other direction: everything in an allowlisted directory that
    # is not deliberately pruned must have arrived. Without this, an
    # over-broad prune drops runtime files silently — the leak check
    # above cannot see a file that is absent.
    missing = []
    for d in WINDOWS_SRC_DIRS:
        for p in (DEV_ROOT / d).rglob("*"):
            rel = p.relative_to(DEV_ROOT)
            if not p.is_file() or any(part in WINDOWS_SRC_PRUNE for part in rel.parts):
                continue
            if not (staging / rel).is_file():
                missing.append(rel.as_posix())
    if missing:
        raise SystemExit("windows source: files dropped from the bundle: "
                         f"{missing[:10]}")


def _zip_windows_source(version: str) -> Path:
    """Build `Corpus-v<version>-windows-src.zip`.

    Plain `zip` is fine here (unlike the .app, which needs `ditto` to
    preserve its signature) — this is ordinary source text.
    """
    zip_path = SHIP_ROOT / f"Corpus-v{version}-windows-src.zip"
    if zip_path.exists():
        zip_path.unlink()
    staging_root = DEV_ROOT / "build" / "windows-src"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    # One top-level folder inside the zip, so unzipping doesn't scatter
    # files across the user's Downloads.
    staging = staging_root / f"Corpus-v{version}-windows-src"
    staging.mkdir(parents=True)

    _stage_windows_source(version, staging)
    _verify_windows_source(staging)
    shutil.make_archive(str(zip_path.with_suffix("")), "zip",
                        root_dir=str(staging_root),
                        base_dir=staging.name)
    print(f"  wrote {zip_path}")
    return zip_path


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("build_ship.py is macOS-only for v0.1.")
    skip_tests = "--skip-tests" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--skip-tests"]
    if unknown:
        raise SystemExit(f"unknown argument(s): {' '.join(unknown)}\n"
                         f"usage: build_ship.py [--skip-tests]")

    version = _read_version()
    print(f"Building Corpus v{version}")
    print(f"  dev root:  {DEV_ROOT}")
    print(f"  ship root: {SHIP_ROOT}")

    _preflight(version, skip_tests=skip_tests)

    _wipe_prior_builds()
    _pyinstaller_build()
    _codesign_adhoc()
    _write_ship_readme(version)
    zip_path = _zip_app(version)
    win_zip = _zip_windows_source(version)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    win_mb  = win_zip.stat().st_size / (1024 * 1024)
    print(f"\nDONE — {zip_path} ({size_mb:.1f} MB)")
    print(f"      + {win_zip} ({win_mb:.1f} MB)")
    print(f"      + {SHIP_ROOT / 'README.txt'}")
    print("\nNext:")
    print(f"  cd ../ship")
    print(f"  git add -A && git commit -m 'v{version} — <summary>'")
    print(f"  git tag v{version}")
    print(f"  # then add the v{version} row to ../ship/SHIPS.md and commit it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
