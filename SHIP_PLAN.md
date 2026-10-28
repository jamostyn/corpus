# Ship Plan — Corpus v0.1 (macOS)

Bite-sized steps toward a `Corpus-v0.1.zip` (containing `Corpus.app`)
that any macOS user can double-click without installing Python or
touching a terminal.

Constraints already decided:
- macOS only for v1
- Ad-hoc code sign (no $99/yr Apple Developer ID)
- Blank white app icon
- Distribute as `.zip` containing a `.app`

Each step below has: **what**, **why**, **how to verify done**.
Steps go in order; don't skip.

---

## Phase 1 — pre-build audit + minor fixes

### Step 1. Ship-readiness audit

**What.** Grep the codebase for anything that would break, misbehave,
or leak dev-only surface in a shipped build. Produce a written report
with pass/fail per item.

**Why.** Free — no code changes. Cheapest way to find deferred bugs
before PyInstaller quirks start hiding them.

**Verify done.** Report exists (chat message + committed as
`docs/SHIP_AUDIT.md`). Every item is either "pass" or has a linked
follow-up in Step 2.

Checks to run:
- `python/dev_only/` and `src/dev_only/` never imported from non-dev
  code (a shipped build won't have those dirs)
- `IS_DEV=False` code path has no broken references (logging disabled,
  bug reporter absent, planning routes absent)
- Nothing at runtime needs `.venv/`, `.git/`, or Jack's
  `~/Organized Files/...` paths
- No `sys.argv` handling that expects CLI args
- `Corpus.command` and `requirements.txt` not read at runtime
- No hard-coded `localhost:5051` references (launcher uses ephemeral
  port; verify frontend/backend don't assume 5051)
- No absolute paths anywhere in Python or JS that assume dev layout

### Step 2. Fix whatever Step 1 found

**What.** Address every non-pass item from the audit.

**Why.** Do it before bundling so PyInstaller quirks don't get
confused with actual bugs.

**Verify done.** All Step 1 items pass on a re-run.

### Step 3. Version stamp

**What.** Create `python/_version.py` with `__version__ = "0.1.0"`.
Expose via new endpoint `GET /api/version` returning
`{"version": "0.1.0"}`.

**Why.** So future bug reports can include the version. So the
frontend can display "Corpus 0.1.0" somewhere subtle. So the
build script can read the version instead of hard-coding.

**Verify done.** `curl 127.0.0.1:<port>/api/version` returns the
correct JSON. `_version.__version__` importable from Python.

### Step 4. App icon

**What.** Generate a blank 1024x1024 white PNG, convert to a proper
multi-resolution `.icns` (16, 32, 128, 256, 512, 1024 sizes) via
`iconutil` (built into macOS). Save at
`dist_assets/Corpus.icns`.

**Why.** PyInstaller needs an `.icns` for the bundle. Without one
the app icon is a generic gear.

**Verify done.** `file dist_assets/Corpus.icns` shows a valid
`Mac OS X icon` file with multiple sub-images.

---

## Phase 2 — build tooling

### Step 5. PyInstaller spec

**What.** Write `pyinstaller_corpus.spec`:
- Entry: `launcher.py`
- Data files: `python/templates/`, `python/static/`, `src/`,
  `python/extract/`, tooltips defaults
- **Excludes**: `python/dev_only/`, `src/dev_only/`, `tests/`,
  `scripts/`, `.venv/`, `Corpus.command`, `requirements.txt`,
  `.git/`, `__pycache__/`
- Hidden imports: any PyMuPDF / pywebview submodules PyInstaller
  misses (usually detected on first build failure — iterate)
- `console=False` (no terminal window)
- `windowed=True`, macOS `.app` bundle target
- Bundle ID: `com.jackmostyn.corpus`
- Icon: `dist_assets/Corpus.icns`

**Why.** Declarative build recipe — reproducible, version-controlled.

**Verify done.** File exists, `pyinstaller pyinstaller_corpus.spec
--noconfirm --clean` runs without a syntax error (may still fail
with missing-import errors — that's Step 6).

### Step 6. First successful build

**What.** Run PyInstaller. When it fails (it will), read the error,
add the missing hidden-import or data-file hint, re-run. Iterate
until it produces `dist/Corpus.app`.

**Why.** PyInstaller's autodiscovery misses ~5% of dependencies for
compiled-extension-heavy projects like PyMuPDF. This step is
inherently iterative.

**Verify done.** `dist/Corpus.app` exists. Size is reasonable
(50-200 MB, mostly PyMuPDF + Python + Flask). `du -sh
dist/Corpus.app` reports.

### Step 7. First launch test

**What.** Double-click `dist/Corpus.app`. Verify the pywebview
window opens and the Corpus UI renders.

**Why.** Catches PyInstaller-specific runtime errors (missing
data files, wrong `sys.path`, native library not found) before
we invest in packaging + signing.

**Verify done.** Window opens. Sidebar tabs render. Log any errors
in the macOS Console (search for "Corpus" or the PID).

### Step 8. Ad-hoc code sign

**What.** Add `codesign --deep --force -s - dist/Corpus.app` to
the build flow. This does an ad-hoc sign (empty identity `-`) —
not real signing, but macOS is friendlier to signed-with-nothing
than to unsigned-at-all.

**Why.** Reduces the number of Gatekeeper hoops for testers. Users
still need to right-click → Open on first launch (unavoidable
without a $99/yr Developer ID).

**Verify done.** `codesign -dv dist/Corpus.app` shows
`Signature=adhoc`. Double-click the signed app; verify it launches
(no signature-mismatch error).

### Step 9. Build-script wrapper

**What.** Write `build_ship.py`:
1. Delete `dist/` and `build/`
2. Run `pyinstaller pyinstaller_corpus.spec --noconfirm --clean`
3. Run `codesign --deep --force -s - dist/Corpus.app`
4. Write `../ship/README.txt` (see Step 12)
5. Run `ditto -c -k --keepParent dist/Corpus.app
   ../ship/Corpus-v<version>.zip`

Output lands in the sibling `Corpus/ship/` repo — a separate git repo
whose stub README declares itself the "release repo that receives
release builds from `../dev/`." Its purpose is to hold shipped
artifacts (zip + tester README) so they can be tagged, committed, and
handed to alpha testers without carrying the whole dev history.

**Why.** Single command → shippable zip in the release repo. No manual
copy step to forget. Two-repo layout keeps release history clean.

**Verify done.** `python3 build_ship.py` produces
`../ship/Corpus-v0.1.0.zip` (and `../ship/README.txt`).

---

## Phase 3 — verification + polish

### Step 10. Smoke-test golden paths on the shipped build

**What.** Launch `dist/Corpus.app`. Walk through:
- First-launch folder picker (delete `~/.corpus/config.json` first
  to simulate a fresh user)
- Add a PDF via the button
- Scan the inbox
- Click a paper → paper detail + PDF viewer
- Type a note, quit, relaunch → note still there
- Author / institution / journal panes load
- No crashes on window close

**Why.** Automated tests don't cover PyInstaller-bundled runtime.
Only manual smoke testing catches things like missing font files
or wrong data-file paths.

**Verify done.** Every path in the checklist works. Any failure
= go back to Step 6 with a specific fix in mind.

### Step 11. Fresh-account test

**What.** Log into the macOS Guest account (or `su` to a fresh
user). Copy `../ship/Corpus-v0.1.0.zip` into their Downloads.
Unzip, drag to `/Applications`, right-click → Open, walk through
Step 10's checklist again.

**Why.** Your normal user has decades of dev crud in `$PATH` and
`~/`. Only a clean account proves the bundle doesn't have hidden
"works on my machine" dependencies.

**Verify done.** Same as Step 10, but on the fresh account.

### Step 12. Tester README in the ship repo

**What.** Write a short `README.txt` alongside the zip in
`../ship/`. Content:

```
Corpus v0.1.0
--------------
1. Drag Corpus.app to /Applications.
2. First launch only: right-click Corpus.app -> Open, then
   confirm the "Apple cannot check for malicious software" dialog.
   (Regular double-click works after that.)
3. First launch will ask where to keep your papers. Pick any folder.

Bug reports: (Jack decides the address later.)
```

**Why.** Right-click-Open is not obvious. One README avoids a
support thread with every tester.

**Verify done.** `../ship/README.txt` and `../ship/Corpus-v0.1.0.zip`
exist side by side.

### Step 13. Ship-ready commit + optional tag

**What.** Two commits — one per repo:
- In `dev/`: commit final source state on `main`. Optional
  `git tag v0.1.0`.
- In `ship/`: commit the new `Corpus-v0.1.0.zip` + `README.txt`.
  Optional `git tag v0.1.0`.

**Why.** Cheap point-in-time marker in each repo so you can (a)
rebuild the exact shipped bits from `dev/` and (b) hand a stable
`ship/` git URL to testers.

**Verify done.** `git log --oneline -1` in both repos shows the
ship commit.

---

## Not in v1 (deferred)

- Windows / Linux builds
- Apple Developer ID signing + notarization
- Auto-update mechanism (`latest.json` fetch on boot)
- Sparkle / Squirrel integration
- CI-driven builds
- Debug symbols / crash reporting

Add them to Planning if/when they become needed.

## Progress tracker

- [x] Step 1 — audit (`docs/SHIP_AUDIT.md`, 6/6 pass)
- [x] Step 2 — fix (no-op; audit found nothing to fix)
- [x] Step 3 — version stamp (`python/_version.py`, `GET /api/version`)
- [x] Step 4 — icon (`dist_assets/Corpus.icns`, all 10 Apple sizes)
- [x] Step 5 — spec (`pyinstaller_corpus.spec`; parses cleanly; iterate in Step 6)
- [x] Step 6 — build (`dist/Corpus.app`, 81 MB, dev_only fully stripped)
- [x] Step 7 — first launch (Jack verified 2026-08-18)
- [x] Step 8 — codesign (PyInstaller signs during BUNDLE; `build_ship.py` re-signs for determinism)
- [x] Step 9 — build script (`build_ship.py`; produces `../ship/Corpus-v0.1.0.zip` + `README.txt`)
- [ ] Step 10 — smoke test (own user)
- [ ] Step 11 — smoke test (fresh user)
- [x] Step 12 — README in ship dir (`build_ship.py` writes it every build)
- [~] Step 13 — ship commit done (`413c675`); git tags still missing in both repos

Steps 10, 11, and the tagging half of 13 are tracked in `ROADMAP.md`
(§ Committed) — they were skipped for both v0.1.0 and v0.1.1.

## Process changes since this plan was written

`build_ship.py` now runs four preflight gates before building
(2026-08-24). They enforce, mechanically, what this document previously
only described:

- **Gate A** — dev git tree must be clean.
- **Gate B** — test suite must be green (`--skip-tests` overrides, for
  iterating on bundling problems only).
- **Gate C** — `CHANGELOG.md` must have a section naming the exact
  version. A `v<version>-dev` entry does not satisfy it.
- **Gate D** — refuses to overwrite a zip already committed in the ship
  repo. Releases are immutable; fixes go into the next version.

Release recipe and the ship registry now live in `../ship/CLAUDE.md`
and `../ship/SHIPS.md`.
