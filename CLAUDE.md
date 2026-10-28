# Corpus — dev workflow (rejacktor)

Read this before every change. If a section here is wrong, fix it in
the same commit as the code change that made it wrong.

## What Corpus is

A macOS desktop app (pywebview + Flask) that extracts structured
metadata from research PDFs and stores it as one YAML-frontmatter
Markdown file per paper in a user-chosen corpus directory. No LLM,
no cloud, no login. Optional enrichment via Crossref (no key),
OpenAlex (mailto), Semantic Scholar (bearer token).

Corpus is **not** Paper Machine. It ships to real users; Paper
Machine is a private research workspace. Do not read, copy, or
refer to Paper Machine files during Corpus work.

## Where to look first

| Question | File |
|---|---|
| Which files own feature X? | `CODE_MAP.md` (kept current — feature→files table) |
| What runs when the user clicks Y? | `CODE_MAP.md` "User action → log signature" table |
| What's planned but not built? | `ROADMAP.md` |
| Test commands + what each test covers | `TESTING.md` |
| Doc/log/CHANGELOG contract | `CONTRIBUTING.md` |
| How releases are cut | `SHIP_PLAN.md` + `build_ship.py` |
| Intra-corpus citation links | `CODE_MAP.md` § "Intra-corpus citation links"; code in `python/citations.py` |
| YAML frontmatter schema | writer: `python/extract/prefill_summary.py::render_frontmatter`; reader: `python/extract/_fm.py::parse_frontmatter` |
| Rolling history | `CHANGELOG.md` (newest at top) |

`CODE_MAP.md` is the map. Read it first when opening any file you
don't already own. Line numbers in it drift — the section markers
inside each file are the authoritative internal index.

## How to run

```
cd Corpus/dev
python3 -m venv .venv                     # first time only
.venv/bin/pip install -r requirements.txt # first time only
.venv/bin/python launcher.py              # boots pywebview + Flask
```

Falls back to opening `http://127.0.0.1:<ephemeral>` in the default
browser if pywebview isn't available. Ctrl-C in the terminal stops
the server.

**Never** launch against the user's live corpus during development
work. Jack's corpus moved out of iCloud on 2026-09-24 and now lives at
`Paper Machine/CorpusTest` (`../../CorpusTest` from here). **As of
2026-09-25 `~/.corpus/config.json` still points at `~/CorpusTest`, an
EMPTY scaffold** — so the app opens blank until Jack re-points it in
Settings. Check the current value if unsure: it has drifted before —
once to a Paper Machine folder, once to `corpus/dev` itself — each time
producing a blank app. Tests never touch that path;
they use `tmp_path` via `tests/conftest.py`, and an autouse
`scratch_config` fixture redirects `config_api.CONFIG_PATH` so no test
can write the real `~/.corpus/config.json` even when the code under
test is broken.

Since 2026-09-17 the source tree specifically cannot be selected:
`_paths.is_corpus_source_tree` rejects it at `POST /api/config` and
again in `ensure_corpus_layout`. Set `corpus_dir` through the app
(Settings, or `POST /api/config`) — never by hand-editing the JSON,
which skips both guards.

If the app looks empty, check `corpus_dir` FIRST. Corpus scaffolds
`papers/` `summaries/` `inbox/` into whatever folder it is pointed at,
so a wrong path yields a valid-looking but empty corpus.

That scaffolding is invisible to git when it lands in the repo — git
does not track empty directories, so `git status` stays clean and
nothing reports it. `tests/test_corpus_dir_guard.py::
test_the_repo_has_no_scaffolded_corpus_directories` is the only thing
that catches it; if it fails, `corpus_dir` was aimed at the source tree
and the empty dirs it names should be removed.

## Seeing what the running app is doing

**Read this before asking Jack what happened.** A long job is visible
from outside the window; it just needs the port.

```
python3 -c "import json,pathlib;print(json.load(open(pathlib.Path.home()/'.corpus/server.json'))['url'])"
# -> http://127.0.0.1:<port>
curl -s $URL/api/progress | python3 -m json.tool
```

`/api/progress` reports the job name, which of its phases is running,
the phase index, per-phase done/total, elapsed seconds and any error.
An import moves through six phases: Reading PDFs → Backfilling
summaries → Fetching citers → Resolving papers → Gathering citers → Finding bridges →
Naming connecting papers. Phase 1 is the PDFs; the last four are the
bridge search that now runs automatically after every import, and on a
400-paper corpus they take longer than the import itself.

`~/.corpus/server.json` is written by `launcher.py` on start and
removed on clean shutdown (`python/dev_only/server_address.py`, dev
builds only — PyInstaller strips it). It carries the launcher's pid,
and `server_address.read()` returns None when that pid is gone, so a
file left behind by a crash cannot send you at a port the OS has since
reassigned to something else.

If the file is missing the app is not running, or it predates
2026-09-21. Last resort: `lsof -nP -p $(pgrep -f launcher.py) | grep LISTEN`.

Under load the endpoint is usually sub-second; one 10.4s response was
measured during a heavy import on 2026-09-21 and did not reproduce in
three immediate retries. Use a generous `-m` on curl rather than
concluding the server is wedged.

**Do not poll it in a shell wait-loop.** Two `until grep …; do sleep;
done` background waits were left spinning for 18 and 9 minutes on
2026-09-21 after the jobs they watched were killed. Check once, report
the phase, move on.

## How to test

```
.venv/bin/python -m pytest tests/ -q      # full suite; ~4s, 547 Python + 130 JS
.venv/bin/python -m pytest tests/test_note_sanitizer.py -v  # single file
node --test tests/src/*.test.js           # frontend suite alone
```

The Python suite has zero external deps beyond `.venv`. The frontend
suite needs `node` (`brew install node`); `test_frontend.py` skips
(does not fail) when node is absent.

**Rules for new tests** (see `CONTRIBUTING.md`):
- Every test's docstring names the concrete mistake it catches.
- If a change introduces a cross-module agreement (two files must
  agree on a schema / enum / key format), a test asserts it. See
  `tests/test_link_keys.py` for the pattern.
- Fixture-based, `tmp_path`-based. Never hit the real Crossref /
  OpenAlex / Semantic Scholar in tests.

## How to ship

```
.venv/bin/pip install -r requirements-build.txt  # first time
.venv/bin/python build_ship.py                   # produces ../ship/Corpus-v<VERSION>.zip
```

`build_ship.py` reads the version from `python/_version.py`
(single source of truth), wipes `dist/` + `build/`, runs
PyInstaller against `pyinstaller_corpus.spec`, ad-hoc codesigns
the .app, writes `../ship/README.txt`, `ditto -c -k`s the bundle
into `../ship/Corpus-v<VERSION>.zip`, and zips the Windows build
source into `../ship/Corpus-v<VERSION>-windows-src.zip`.

TWO artifacts per release. PyInstaller cannot cross-compile, so the
Windows `.exe` is built on Windows from that second zip via
`build_windows.bat`. `pyinstaller_corpus.spec` is dual-platform —
one recipe, branching on `IS_WINDOWS`; do NOT fork a second spec.

**Before shipping:**
1. Update `python/_version.py` (bump per SemVer).
2. Update `CHANGELOG.md` — add a section for the new version at the top.
3. Update `ROADMAP.md` — remove or update any entry the release closes.
4. Run the full test suite; must be all-green (559 Python + 147 JS as of 2026-10-15).
5. Commit source + docs together.
6. Run `build_ship.py`.
7. In the sibling `../ship/` repo, commit the new zip with a message
   matching the CHANGELOG section title.

The `ship/` repo is a release registry. Only `build_ship.py` writes
to it. No hand edits.

## The doc / log contract (from CONTRIBUTING.md)

If a user clicks a thing:
1. **CODE_MAP.md** predicts what code runs and what log lines fire.
2. **`~/.corpus/logs/server.log`** confirms it did (dev builds only).

Any change that adds a new user-facing action MUST update the
"User action → log signature" table in `CODE_MAP.md` AND emit an
event log at the state change point. Format: `<verb>_<noun> key=val`.

`corpus.*` logging is DEV-ONLY. Shipped users produce zero log
output — `_configure_logging` sets `logger.disabled = True` and the
access-log Flask hooks aren't registered. Verified by
`tests/test_logging_dev_only.py`.

## Do not touch

- `../../CorpusTest/` (or wherever `~/.corpus/config.json` points) —
  Jack's live corpus. Testing goes through `tmp_path`.
- `~/.corpus/` — user config + dev-only planning + Keychain access.
  Read via the app; never hand-edit during dev work.
- Paper Machine (`../../scripts/`, `../../summaries/`, `../../projects/`,
  `../../inbox/`, `../../papers/`) — separate project. Do not crawl,
  copy, or reference. If Jack asks about a Paper Machine feature by
  name during Corpus work, ASK before pulling anything from there.
- `../ship/*.zip` — release artifacts, never edited after cutting.
- `src/vendor/pdfjs/` — Mozilla's PDF.js; the only Corpus-authored
  file inside it is `web/corpus-highlights.{js,css}`.

## Rejacktor discipline (see the skill for the full protocol)

- Every change: consult `CODE_MAP.md`, run tests first, list every
  touched file/doc/test up front, hunt for duplication before adding a
  copy of any fact.
- Every deferred / newly-planned item lands in `ROADMAP.md` in the same
  commit as the change that deferred / planned it.
- Every commit includes docs updated alongside code, with the Claude
  co-author trailer.
- No CLI scripts. All user-facing features are buttons. Debug helpers
  go under `python/dev_only/` (stripped from ship).

## Facts verified (2026-08-24 onboarding, updated 2026-09-17)

- Full test suite: 547 Python + 130 JS tests, all green, ~1.4s.
- Mutation-tested: 129 planted bugs, 128 killed, 1 documented
  unreachable survivor. See `TESTING.md`.
- End-to-end boot verified against a scratch corpus dir: all 9 GET
  endpoints 200, note create/read/update round-trips, the HTML
  sanitizer strips `<script>` live, highlights persist with anchored
  notes, `POST /api/scan` succeeds, missing note 404s, clean shutdown.
- Node 26.7.0 present; frontend suite ran (not skipped).
- Server module boots with 44 routes; `IS_DEV=True` in dev.
- `extract_metadata` and `fitz` are NOT imported at server boot — PDF
  machinery loads lazily on first extract.
- Version: 0.4.2 (in `python/_version.py`), shipped 2026-10-15 — puts
  pdf.js back in the Windows source zip (a `build` prune rule had
  dropped `src/vendor/pdfjs/build/` from every Windows zip since 0.2.0).
  0.4.1 (2026-10-01) was a patch on 0.4.0 (Windows viewer content types,
  current pickers, pop-out scroll place, note Settings menu). 0.1.1
  was the last macOS-only release; 0.2.0 added the Windows source zip;
  0.3.0 added Projects, citation bridges, visible job progress and the
  derived-data caches, and is the first release carrying a git tag;
  0.4.0 adds Documents, the note workspace, stored citers and note
  revisions.
- Shipped `dist/Corpus.app`: arm64, adhoc-signed, 418 sealed resources,
  bundle id `com.jackmostyn.corpus`.
- `~/.corpus/config.json`: `{corpus_dir: "/Users/jackmostyn/Documents/CorpusTest", mailto: ""}`
  (re-set 2026-09-17 after drifting to `corpus/dev`). That corpus holds
  59 papers, 6 notes, 2 projects.
- Both `python/dev_only/` and `src/dev_only/` present on disk (so
  `IS_DEV` resolves True).
- `python/enrich/` directory removed — was empty and unreferenced.
- Windows build path: spec verified to evaluate in its `IS_WINDOWS`
  branch from the extracted source zip (icon `.ico`, `BUNDLE` skipped,
  edgechromium + keyring.backends.Windows). NOT verified: that
  `build_windows.bat` produces a working `.exe` — no Windows machine
  here. See `ROADMAP.md`.
- Endpoint timings measured 2026-09-17 after adding the derived-data
  caches (best-of-5, warm): on the real 59-paper corpus every list
  endpoint is 1-7ms; on a synthetic 590-paper corpus, 10-42ms. Before
  the caches: 21-65ms and 198-618ms. `parse_frontmatter` had been 76%
  of server time. Cold (post-change) requests are ~11% slower.
- Citation linking measured on the real 57-paper corpus: 55 papers with
  a usable DOI, 2929 references (2544 carrying a DOI), 22 intra-corpus
  edges, 1 duplicate-DOI pair. `/api/citations` responds in ~130ms.

Anything else claimed here is subject to code drift — re-verify
before relying on it.
