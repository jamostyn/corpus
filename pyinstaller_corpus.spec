# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Corpus — macOS .app bundle AND Windows .exe.
#
# ONE spec, two platforms. PyInstaller cannot cross-compile, so the
# Windows build runs this same file on a Windows machine (see
# build_windows.bat in the windows-source zip). Keeping it as one file
# rather than forking a second spec is deliberate: the hidden-import
# list, the dev_only exclusions and the frontend collector are the
# parts that actually rot, and two copies would drift the moment a
# module is added.
#
# Platform differences, all keyed off IS_WINDOWS below:
#   icon        .icns vs .ico
#   backends    cocoa/PyObjC + Keychain vs edgechromium + Windows Credential Locker
#   packaging   BUNDLE (.app) is macOS-only; Windows stops at COLLECT
#
# Layout at build time (repo root = cwd when running pyinstaller):
#   ./launcher.py            entry point (imports server + boots pywebview)
#   ./python/                blueprints + server composition root
#   ./python/extract/        extract-pipeline modules (imported by bare name)
#   ./src/                   static frontend (JS/CSS/HTML) — Flask static_folder
#   ./dist_assets/Corpus.icns  bundle icon (Step 4)
#
# What we DO NOT ship (matches SHIP_AUDIT.md):
#   python/dev_only/, src/dev_only/, tests/, scripts/, .venv/, .git/
#
# Iteration expected during Step 6 — first build almost always turns up
# a missing hidden import (PyMuPDF, pywebview backends, or keyring backends
# most commonly). Add them here and re-run.
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith('win')

# Single source of truth for version (Step 3).
_ns = {}
exec(open('python/_version.py').read(), _ns)
VERSION = _ns['__version__']

BLOCK_CIPHER = None


def _collect_frontend(src_root: str = 'src') -> list[tuple[str, str]]:
    """Enumerate every file under `src/` EXCEPT anything inside
    `src/dev_only/`. Returns PyInstaller's (src_path, dest_dir) tuples.

    Bare `datas=[('src', 'src')]` would copy the whole tree — including
    the dev-only frontend bundle (bug-reporter, planning modal, tooltip
    editor). Those files never execute in a shipped build because the
    IS_DEV gate is False (python/dev_only/ is excluded, so BOTH-dirs
    check fails), but shipping unused code is still gross — a user
    poking at the .app internals shouldn't see UI they can't reach.
    """
    out: list[tuple[str, str]] = []
    root = Path(src_root)
    for f in root.rglob('*'):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        if rel.parts and rel.parts[0] == 'dev_only':
            continue
        # PyInstaller wants (source, dest_directory) — dest is the dir
        # inside the bundle, source is the file on disk.
        dest_dir = str((Path('src') / rel.parent))
        out.append((str(f), dest_dir))
    return out


a = Analysis(
    ['launcher.py'],
    # pathex tells PyInstaller where to look for the hiddenimports below
    # AND for anything the static walker discovers. Mirrors the sys.path
    # tweaks that launcher.py + server.py do at runtime.
    pathex=['python', 'python/extract'],
    binaries=[],
    # LICENSE + notices travel inside the app (AGPL: a copy of the licence
    # goes with every copy of the program). They land in the bundle root.
    datas=_collect_frontend('src') + [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')],
    hiddenimports=[
        # ----- Extract-pipeline modules -----
        # These use bare-name imports (`from _api_http import ...`) which
        # PyInstaller's static walker can miss when they're only referenced
        # from dynamically-imported blueprints.
        '_paths', '_fm', '_api_http', '_version',
        'crossref_client', 'openalex_client', 'semanticscholar_client',
        'oa_enrichment', 'window_fallback',
        'prefill_summary', 'extract_metadata', 'extract_references',

        # ----- Blueprint modules -----
        # server.py `import config_api` etc. — usually auto-detected,
        # listed here for safety since they live outside a package.
        'config_api', 'entities_api', 'extract_api',
        'notes_api', 'papers_api',

        # ----- PyMuPDF (fitz) -----
        # Compiled extension; the hooks-contrib package normally handles
        # this but the top-level module hint doesn't hurt.
        'fitz',

        # ----- pywebview + keyring backends (platform-specific) -----
        # Both libraries discover backends through entry_points, which
        # PyInstaller's static walker cannot follow — hence the explicit
        # names. Listing the WRONG platform's backend is harmless (the
        # import just fails and PyInstaller warns), but listing NEITHER
        # produces a bundle that builds fine and then dies at launch.
        'webview',
        *(['webview.platforms.edgechromium', 'webview.platforms.winforms',
           'clr_loader', 'pythonnet',
           'keyring.backends.Windows', 'win32timezone']
          if IS_WINDOWS else
          ['webview.platforms.cocoa',
           'objc', 'AppKit', 'WebKit', 'Foundation',
           'keyring.backends.macOS']),
        'keyring', 'keyring.backends',

        # ----- werkzeug/Flask stragglers -----
        # These are usually auto-detected. Listed for safety.
        'werkzeug', 'werkzeug.serving', 'flask',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev-only surfaces (belt-and-suspenders — the source dirs are
        # already outside pathex, but excluding here catches transitive
        # imports too).
        'dev_only',
        # The extractor benchmark's stack (requirements-bench.txt). It
        # lives in dev/.venv-bench, never the build venv; listed here so
        # a stray install there still cannot ride into the app. The
        # pymupdf-layout wheel installs INTO the pymupdf package
        # (pymupdf/layout, features, tgif — checked in its RECORD
        # 2026-10-21); there is no top-level `pymupdf_layout` module.
        'pymupdf4llm', 'pymupdf.layout', 'pymupdf.features', 'pymupdf.tgif',
        'onnxruntime',
        # Test-only dep (PyYAML per requirements.txt: "used by tests").
        'yaml',
        # Anything a shipped user won't need.
        'pytest', 'pytest_lazyfixture', 'setuptools',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Corpus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX + macOS has been known to break signed bundles; ad-hoc sign
    # (Step 8) is happier without it.
    upx=False,
    # No terminal window when the user double-clicks Corpus.app.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    # We ad-hoc sign in build_ship.py (Step 9), not here — so PyInstaller
    # doesn't spend time on it and we can iterate faster during Step 6.
    codesign_identity=None,
    entitlements_file=None,
    icon=('dist_assets/Corpus.ico' if IS_WINDOWS else 'dist_assets/Corpus.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Corpus',
)

# BUNDLE wraps COLLECT's output in a .app directory. It is a no-op on
# Windows (PyInstaller ignores it) but referencing the .icns would fail
# there, so it is skipped outright. The Windows deliverable is the
# COLLECT folder: dist/Corpus/Corpus.exe plus its _internal/ payload.
app = None if IS_WINDOWS else BUNDLE(
    coll,
    name='Corpus.app',
    icon='dist_assets/Corpus.icns',
    bundle_identifier='com.jackmostyn.corpus',
    version=VERSION,
    info_plist={
        'CFBundleName':               'Corpus',
        'CFBundleDisplayName':        'Corpus',
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion':            VERSION,
        # Render on Retina displays instead of pixel-doubling a 1x asset.
        'NSHighResolutionCapable':    True,
        # Explicitly declare no doc types / URL schemes for now.
    },
)
