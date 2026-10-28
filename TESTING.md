# Corpus Testing

Smoke test suite. 216 Python tests + 71 JS tests, runs in under a second, catches the most
common regressions after a refactor. Not a full unit-test suite — see
"Known gaps" at the bottom for what it does not cover.

## Run

```sh
cd Corpus/dev
.venv/bin/python -m pytest tests/ -q
```

Or point-and-shoot at one file:

```sh
python3 -m pytest tests/test_note_sanitizer.py -v
```

The Python suite has zero external deps beyond what's already in the
`.venv` (`pytest` + `flask`'s test-client + stdlib). The frontend
suite (see below) needs `node` (`brew install node`) — it's skipped,
not failed, when node is missing, so the Python suite always runs.

## What each test covers

### Python (`tests/*.py`)

| File                            | What it verifies                                        |
|---------------------------------|---------------------------------------------------------|
| `tests/test_server_boot.py`     | Server module imports cleanly, all expected routes are registered, `_paths.notes_dir()` etc. resolve without a corpus set (once one is set) |
| `tests/test_note_sanitizer.py`  | Note HTML sanitizer allow-list works: keeps p/strong/table/etc., drops script/img/style hacks, clamps font-size + table dims to safe ranges |
| `tests/test_note_endpoints.py`  | Round-trips a note through POST /api/notes → PUT /api/note/<id> → GET → DELETE; sanitizer runs on write |
| `tests/test_metadata.py`        | `extract_metadata.py` helpers: DOI candidate ranking, title-candidate filtering, `_looks_like_container_title` heuristic |
| `tests/test_script_load_order.py` | index.html loads scripts in the required order (feature modules before app.js; provenance.js before detail modules) |
| `tests/test_frontend.py`        | Shells out to `node --test` over each `tests/src/*.test.js`. Skips when node isn't installed. |
| `tests/test_highlights_endpoints.py` | Highlight + anchored-note round-trip: every field survives a save/load, and the note tri-state (absent / `""` / content) stays distinguishable |
| `tests/test_bridge_contract.py` | `launcher.py`'s `_Bridge` methods match the `window.pywebview.api.*` calls in `src/*.js`, in both directions |
| `tests/test_version_contract.py` | `_version.py` stays the single source of truth for `/api/version`, `build_ship.py`, and the bundle stamp |
| `tests/test_ref_line_roundtrip.py` | `Reference.to_md_line()` and `parse_ref_line()` stay exact inverses across all 8 rendered shapes — the property intra-corpus links depend on |
| `tests/test_pdf_refs.py`        | PDF reference extraction (APA + Vancouver styles, split DOIs, hyphenation, unreadable-vs-no-section) and the merge rule: PDF fills blanks and appends but never overwrites an API value |
| `tests/test_detached_layout.py` | Detached-window header compaction: Pop out hidden (dead control), actions laid out as a row, base rule left as a column, source path compacted rather than hidden |
| `tests/test_note_gutter_stability.py` | The note gutter updates in place while typing: unchanged card sets are not rebuilt, a focused textarea is never written to, a real rebuild restores scroll without echoing it to the viewer, and the ResizeObserver survives in-place updates |
| `tests/test_empty_corpus_state.py` | An empty corpus keeps the empty state up and names the configured path, the two empty reasons stay distinguished, the ids the JS writes to exist, and `ensure_corpus_layout`'s docstring matches its behaviour |
| `tests/test_windows_build.py`   | Dual-platform spec (icon, BUNDLE, per-platform webview/keyring backends) and the Windows source zip (every build input present, every pdf.js module the viewer loads present, the verifier rejects a dropped file, no dev_only/.venv/.git leak, spec byte-identical to the mac build's) and that git ignores no shipped source |
| `tests/test_note_shortcuts.py` | Note formatting chords: resolved from `_NOTE_TOOLBAR` not a second list, dispatched via the toolbar button (so history/save are not skipped), force-save moved to ⌘⇧S without being dropped |
| `tests/test_highlight_undo.py` | Single-step undo: every highlight mutation sits inside the `commitHighlights` funnel, the clone is deep enough to capture a recolour, undo is one level, note edits invalidate the snapshot |
| `tests/test_highlight_overlap_geometry.py` | The overlap rule, EXECUTED: extracts `rectsOverlap` + `highlightsOverlapping` from the real source and runs them in node. Pins that a selection sharing no glyphs with an existing highlight leaves it alone (the 2026-09-09 bug), that a genuine overlap is still found, that later rects on both sides are tested, that the page filter holds, and that touching edges are not an overlap |
| `tests/conftest.py` | `scratch_config` — AUTOUSE, redirects `config_api.CONFIG_PATH`/`CONFIG_DIR`/`TOOLTIPS_PATH` to `tmp_path` for every test. Without it a test that POSTs to `/api/config` writes the real user config whenever the endpoint's validation is broken — which is precisely when such tests run |
| `tests/test_slug_collision.py` | Import identity: two papers with no DOI get separate slugs rather than overwriting each other, the same paper re-imported keeps its slug (url-form and mixed-case DOIs, on either side), a different DOI gets a suffix, gaps in the numbering are filled not skipped, an unreadable or undecodable existing summary never licenses an overwrite, and the filename-fallback path still resolves collisions |
| `tests/test_progress.py` | The shared job channel and the auto-bridge hook: phase/detail/counts are all reported, a second job cannot evict a running one, a finished job lingers then goes quiet, errors survive, a post-finish write cannot resurrect a job; plus the import side — an empty scan closes its job and runs no network search, `added` is derived from what actually landed, the search fires once per BATCH reusing the import's job, and a failed search does not look like a failed import |
| `tests/test_note_workspace.py` | The popped-out note workspace: the detached key round-trips kind+id and still reads a bare slug as a paper (including the adversarial slug `notes`), every Map lookup uses `detachKey`, the panel has its own post helper, paper links are intercepted BEFORE `switchMode` and only paper links are, the note editor renders into a host rather than being duplicated, `data-open-highlight` survives the sanitizer and rejects a traversal value without entering the MODES entity list, the link always carries its paper, pick mode precedes the Note Mode guard, a missed pick stays armed, and an unknown highlight id does not jump |
| `tests/test_nav_history.py` | Back/forward, EXECUTED: extracts `_currentPlace` + `_recordPlace` from app.js and replays move sequences in node. Pins that places record in order, that revisiting the same place doesn't stack duplicates, that a tab switch with no selection still counts, that moving through history records nothing, that the forward branch is truncated on a new move, that history is capped, that recording happens at exactly two call sites, that the arrows disable at both ends, and that create-then-select goes through the wrap |
| `tests/test_bridges.py` | Citation bridges, network fully stubbed: the intersection runs the right way round, direct pairs aren't duplicated as bridges, pairs are oriented newer→older, an unknown year never drops a pair, middles are capped and sorted; plus the endpoints — paper detail never hits the network, compute/read round-trips, a failed citer lookup is reported rather than read as "nothing cites it", corpus changes mark the cache stale, a corrupt or old-format cache degrades instead of 500ing |
| `tests/test_caching.py` | Both derived-data caches and, mostly, their INVALIDATION: an edited summary is re-read (including a same-size edit and a pinned-mtime edit), deletions disappear and leave no cache entry, new summaries appear, repeat requests don't re-parse, a mutated result can't poison the cache, and the citation index rebuilds on add / remove / reference-edit (including same-size and same-mtime edits) while not rebuilding for an unchanged corpus |
| `tests/test_country_display.py` | No pane renders a bare ISO country code: no module `escHtml()`s a raw `country_code`, every module referencing one uses the shared helper, `countries.js` loads before all five of them, and the institutions filter searches the country NAME it displays |
| `tests/src/countries.test.js` | `Countries.name`/`withCode`, EXECUTED in the vm harness: real names for codes a reader can't decode, empty/null/alpha-3 inputs degrade to a renderable string instead of throwing, lower-case codes resolve, unresolved codes come back unrewritten, `withCode` never prints "USA (USA)", the whole module falls back to raw codes when `Intl.DisplayNames` is missing or throws, the formatter is built once, and empty input never reaches Intl |
| `tests/test_corpus_dir_guard.py` | The corpus dir cannot be Corpus's own source tree: the predicate recognises the real repo and its subdirectories, allows ordinary folders and plain git repos, needs both markers; the config endpoint 400s and writes nothing; the scaffolder raises independently; and one test asserts the repo currently holds no scaffolded corpus dirs — the pollution git cannot see |
| `tests/test_list_search.py` | List filtering, EXECUTED: extracts `modeRowMatches` + each mode's real `searchFields` arrow from app.js and runs them in node. Pins that a paper is findable by author (the 2026-09-14 report), that title/year/ISSN/institution/snippet search all survived the consolidation, that fields are matched element-wise rather than joined, that missing fields don't match "null"/"undefined", case-insensitivity, and that no sidebar or picker kept an inline filter |
| `tests/test_projects.py` | Projects behaviour through the Flask client: a paper in several projects at once, adding never moves the .md, membership survives a summary rewrite (the re-extract case), deleting a project spares its contents, dangling members filtered-not-pruned, PUT can't clobber the member list, path-traversal + unknown-kind + ghost-member rejected, malformed project files degrade |
| `tests/test_project_member_kinds.py` | JS↔Python parity on `memberKind` / `_PROJECT_MEMBER_KINDS`, that each member mode declares the nouns and the loadable list the picker needs, that the picker reuses MODES labels rather than copying them, and that member rows don't use the `data-open-*` delegation (which excludes notes) |
| `tests/test_mode_action_buttons.py` | The top-right action slot is MODES-driven, not a per-tab if-else; Add/Scan hide exactly when a mode owns the slot; every declared `actionBtnId` exists in the HTML and starts hidden; every MODES entry's filter/list/detail ids and tab button exist |
| `tests/test_highlight_erase_mode.py` | PDF eraser invariants: erase keeps the text layer interactive, dispatches before the highlight-mode guard, is mutually exclusive with Highlight, confirms only for note-carrying highlights, notifies the parent gutter, and shares one copy of the selection geometry |
| `tests/test_note_link_attrs.py` | Note entity links: JS MODES `linkAttr` list matches the Python sanitizer allow-list, `data-open-*` and the marker class survive a save, malformed identifiers are dropped whole |
| `tests/test_citations.py`       | Citation index: DOI normalization, links appearing without rewriting summaries, duplicate DOIs surfaced, self-loops dropped, and both endpoints' payload shape |

### Frontend (`tests/src/*.test.js`)

Real JS tests — each `*.test.js` uses node's built-in `node:test`
runner. The harness (`tests/src/harness.js`) loads a browser JS file
into a `vm` sandbox with fakes for `window`, `SRC_ABBR`, `escHtml`,
`escAttr`, `tt`, so pure helpers can be exercised without a DOM.

| File                                   | What it verifies                             |
|----------------------------------------|----------------------------------------------|
| `tests/src/provenance.test.js`         | `Provenance.badgeFromArr` / `badgeFromField`, `Coverage.inSource` / `cell` / `renderTable` — the shared helpers used by all four detail modules |
| `tests/src/note-shortcuts.test.js`     | `_NOTE_TOOLBAR` chord declarations: all four formatting commands bound, no duplicate chords, every keyed entry has a `cmd`, tooltips advertise the chord |
| `tests/src/corpus-links.test.js`       | `CorpusLinks.render` — both citation directions always present, empty-state wording, the no-DOI explanation, and the reference-count breakdown |

Run just the JS side directly with:

```sh
node --test tests/src/*.test.js
```

**Use the glob, not the directory.** `node --test tests/src/` treats
the argument as a module path and dies with `MODULE_NOT_FOUND` — which
looks exactly like a failing suite. `test_frontend.py` enumerates the
files explicitly for this reason.

## When to run

- Before committing a refactor: **required**.
- After merging any change touching `server.py`, `extract_metadata.py`, or the note sanitizer: **required**.
- After a change to `provenance.js` or any detail module: **required** (frontend suite catches drift).
- After a UI-only cosmetic change: optional (frontend suite covers pure helpers, not layout).

## Adding tests

Follow the existing pattern — one file per concern, one Python module,
plain `def test_*` functions. Use the Flask test client for endpoint
tests. Avoid hitting the real Crossref/OA/SS APIs — those tests
belong in a separate integration suite (not built yet).

**Every test's docstring names the concrete mistake it catches.** If
you can't describe a realistic code change that would make the test
fail, don't write it — a test that asserts something true by
construction is noise that erodes trust in the suite.

Corpus root: tests that need a corpus_dir should use `tmp_path` (pytest
fixture) and pass it to `_paths.set_corpus_root(...)`. See
`test_note_endpoints.py` for the pattern. Tests must never touch the
user's real corpus directory (`~/.corpus/config.json` → `corpus_dir`).

## Mutation evidence

Suite value is answered empirically, not by counting tests: plant a
plausible bug, confirm the suite goes red, revert. Results from the
2026-08-24 onboarding pass and the 2026-08-25 citation-links work — **26 planted, 25 killed**.

Against the pre-existing 60 tests:

| Planted bug | Tests that caught it |
|---|---|
| Sanitizer allow-list admits `<script>` (stored XSS in notes) | 2 |
| `_author_key` drops the given-name token (desyncs the JS mirror in `entity-keys.js`) | 5 |
| Shipped builds stop silencing the `corpus.*` logger (privacy guarantee broken) | 1 |
| `app.js` loaded before the feature modules it depends on | 3 |
| Frontmatter emitter renames a field's output key | 1 |

Against the 20 tests added during onboarding, covering contracts that
previously had **no** guard at all:

| Planted bug | Tests that caught it |
|---|---|
| `save_highlights` stops copying the `note` field (every anchored note lost on reload) | 3 |
| Note tri-state collapsed to an unconditional assignment (empty card beside every un-annotated highlight) | 2 |
| `note: null` leaks through as the literal string `"None"` | 1 |
| A 2000-char cap added to notes (silent truncation) | 1 |
| Non-empty-`rects` guard dropped (invisible, undeletable highlights) | 1 |
| Project members appended without a dedupe check | 1 |
| Dangling project members rendered instead of filtered | 1 |
| PUT /api/project/<id> allowed to write `members` | 1 |
| Member remove clears the whole kind | 1 |
| Member-id regex loses its alphanumeric lookahead (".." accepted) | 1 |
| Member existence check skipped (ghost members storable) | 1 |
| Action slot hard-coded back to `id === "notes"` | 1 |
| Papers lose `memberKind` (JS↔Python parity break) | 3 |
| Member rows revert to `data-open-*` (dead note links) | 1 |
| Author dropped from the papers search fields | 3 |
| `searchFields` joined into one string (filters silently widen) | 1 |
| `String()` coercion dropped (numeric year throws) | 3 |
| `v != null` guard dropped ("nu" matches every row with a blank field) | 1 |
| Query no longer lowercased (search becomes case-sensitive) | 1 |
| Notes lose snippet / journals lose ISSN from their fields | 1 each |
| A picker reverts to filtering the rendered label | 1 |
| A sidebar reverts to its own inline filter | 1 |
| `searchHint` stops promising what `searchFields` delivers | 1 |
| A filter box dropped from the shared styling rule | 1 |
| `navigating` guard dropped (back records itself) | 1 |
| Duplicate places stack | 1 |
| Forward branch appended instead of truncated | 1 |
| History uncapped | 1 |
| Back / forward arrow never disables | 1 each |
| A place requires an id (tab switches lost) | 1 |
| Bare detached hash no longer means paper | 1 |
| Unknown detach kind not coerced | 1 |
| Panel interception placed after switchMode | 1 |
| Every link kind redirected to the panel | 1 |
| detachedWindows keyed by a raw slug | 1 |
| `data-open-highlight` not allowed / not value-checked | 1-2 |
| Highlight link drops its paper attribute | 1 |
| Pick branch after the Note Mode guard | 1 |
| A missed pick click disarms | 1 |
| Scroll jumps on an unknown highlight id | 1 |
| Note editor duplicated instead of taking a host | 1 |
| `set_config` source-tree check removed | 2 |
| Guard checks the path but not its ancestors | 1 |
| Either marker suffices instead of both | 1 |
| `ensure_corpus_layout` scaffolder guard removed | 2 |
| Guard widened to reject any git repo | 6 |
| Rejected corpus_dir written to config.json anyway | 2 |
| Marker filenames renamed so the guard matches nothing | 6 |
| Empty-state markup reverts to "Pick a corpus directory" | 1 |
| Loading state shown after loadPapers() instead of before | 1 |
| Loading state drops the corpus path | 1 |
| Folder picker left visible while loading | 1 |
| Folder picker never restored for the other reasons | 1 |
| autouse `scratch_config` fixture removed (tests can write the real config) | 1 |
| Summary cache validated on size only / mtime only / not at all | 1-4 |
| Cached frontmatter dict handed out instead of a copy | 1 |
| Deleted-summary cache entries never pruned | 1 |
| Summary cache never stores (always a miss) | 1 |
| Citation fingerprint ignores mtime / ignores size | 1 each |
| Citation index memo never invalidates / never stores | 1-2 |
| Bridge intersection run forward-vs-forward | 5 |
| Direct citations duplicated as bridges | 1 |
| Both orientations of a pair emitted | 1 |
| Unknown year treated as 0 (drops real pairs) | 1 |
| Middles uncapped / unsorted | 1 each |
| `bridges_for` matches only the src end | 1 |
| Citer-lookup failure counted as "no citers" | 1 |
| Bridge cache version / corrupt-JSON guard removed | 1 each |
| Stale flag hard-coded False | 1 |
| Empty-corpus 400 removed | 1 |
| `oa_short_id` stops stripping the URL prefix | 2 |
| Second job evicts a running one | 1 |
| Finished job never goes quiet / cleared instantly | 1-5 |
| Post-finish step applied to a done job | 1 |
| Error dropped on finish | 2 |
| Bridge search kicked with nothing added | 1 |
| Background search starts its own job instead of reusing | 2 |
| Bridge failure left unreported | 1 |
| `added` hard-coded rather than derived | 1 |
| Slug identity compares raw DOI strings (the original overwrite bug) | 1 |
| Only one side of the DOI comparison normalised | 1 |
| Empty-DOI guard dropped (no-DOI papers collapse together) | 2 |
| Parse/read failure treated as "same paper" | 1 |
| Suffix search counts existing files instead of the first free | 1 |
| Filename-fallback path skips collision resolution | 1 |
| Institutions sidebar renders a raw country code | 1 |
| Institutions lose country-NAME search (display ≠ searchable again) | 2 |
| Institution detail renders a raw country code | 1 |
| `toUpperCase()` dropped (lower-case codes pass through silently) | 5 |
| try/catch around `Intl.of()` dropped (alpha-3 input throws) | 5 |
| `Intl.DisplayNames` rebuilt on every call | 3 |
| `withCode` prints the code twice when unresolved | 5 |
| `countries.js` script tag removed from index.html | 1 |
| Empty-code early return dropped | 1 (equivalent mutant until the suite was strengthened — see `countries.test.js`) |
| Overlap reverted to a bounding-box test (deletes untouched highlights on multi-line spans) | 1 |
| Only `rects[0]` of the selection compared | 1 |
| `some` → `every` on the selection side | 1 |
| Highlight page filter dropped | 1 |
| `rectsOverlap` `<=` → `<` (touching edges count as overlap) | 1 |
| `_Bridge.open_detached` renamed (pop-out dies silently behind `catch (_) {}`) | 4 |
| `/api/version` hard-codes a version string instead of reading `_version.py` | 1 |

Against the citation-linking code added 2026-08-25 — **8 planted, 7
killed, 1 survivor**:

| Planted bug | Tests that caught it |
|---|---|
| `doi_to_slugs` keeps one slug per DOI (drops links from duplicate imports) | 2 |
| Self-loops allowed (a paper cites itself via a duplicate DOI) | 1 |
| `"unknown"` treated as a real DOI (every unknown-DOI paper links to every other) | 1 |
| Reference-line parser loses the `(extracted)` marker | 2 |
| Section parser reads the whole body, not just `## References` | 1 |
| `resolve_references` never sets `linked_slug` (no "In corpus" chips) | 2 |
| A second DOI normalizer reintroduced in `citations.py` | 6 |
| **SURVIVOR** — dropping `normalize_doi()` on the reference side of the match | 0 |

**About the survivor.** It is unreachable, not untested.
`parse_ref_line` already normalizes every DOI before it reaches
`build_index`, so no real code path can deliver an unnormalized
reference DOI, and no test can construct one through the supported
API. The call is kept as defense-in-depth in case the parser stops
normalizing; the guarantee that both sides fold identically is pinned
instead by `test_one_doi_normalizer_shared_by_matcher_and_parser`,
which asserts they are the same function object.

That survivor is also what exposed a real duplication: two DOI
normalizers existed with different rules. They were consolidated into
`_api_http.normalize_doi`, verified behaviour-preserving by re-running
the index over the real 57-paper corpus (22 edges before and after).

Against `corpus-links.js` (the connections block), 2026-08-25 —
**6 planted, 6 killed**:

| Planted bug | Tests that caught it |
|---|---|
| Block returns "" when both directions are empty (looks like a missing feature) | 8 |
| A direction is omitted when its list is empty — **the original reported bug** | 5 |
| The "this paper has no DOI" explanation dropped | 1 |
| References with no DOI folded into the unmatched count | 1 |
| `data-open-paper` lost (links render as dead text) | 2 |
| "No reference list for this paper" message removed | 1 |

Re-run this exercise after any significant change to the suite. If a
plausible bug survives, that's the next test to write.

## Known gaps

Honest list of what the suite does not cover, so nobody reads green as
"everything works":

- **No integration tests.** Nothing exercises the real Crossref /
  OpenAlex / Semantic Scholar APIs, so a breaking change in their
  response shape would ship undetected.
- **The Windows build is unverified end-to-end.** `tests/test_windows_build.py`
  checks the spec's platform branching and the source zip's contents,
  but nothing here runs `build_windows.bat` — that needs a Windows
  machine. Whether the produced `Corpus.exe` launches is unknown until
  someone runs it.
- **No PyInstaller-bundle tests.** The suite runs against the source
  tree, never against `dist/Corpus.app`. Bundle-only failures (missing
  data file, wrong `sys._MEIPASS` path, missing hidden import) are
  caught only by launching the built app. That is what `SHIP_PLAN.md`
  Steps 10-11 are for, and both remain undone — see `ROADMAP.md`.
- **No DOM tests.** The frontend suite loads JS into a `vm` sandbox
  with fakes; it exercises pure helpers only.
  `src/vendor/pdfjs/web/corpus-highlights.js` is the worst case: it is
  an IIFE that returns early without a `?file=/pdf/<slug>` param and
  needs PDF.js's page DOM, a text layer, and a live selection.
  `tests/test_highlight_erase_mode.py` and `test_highlight_undo.py` pin
  structural invariants only, and whether a drag actually erases is
  verified by hand. The ONE exception is the overlap geometry: those two
  functions are pure, so `test_highlight_overlap_geometry.py` extracts
  them from the source and executes them in node. That gap was not
  academic — the 2026-09-09 bounding-box bug passed every structural
  test in the suite, because structure cannot distinguish a correct
  overlap rule from a wrong one. Where a helper in this file is pure,
  prefer extract-and-execute over another source assertion. Layout,
  event wiring,
  the PDF.js iframe bridge, and Note Mode's gutter positioning are all
  manual-test-only. `test_bridge_contract.py` closes part of this by
  checking the JS↔Python method names agree, but it cannot verify that
  a pop-out window actually opens.
- **No PDF-extraction accuracy tests.** `test_metadata.py` covers the
  ranking and filtering helpers, not end-to-end extraction against
  real PDFs.

Against PDF reference extraction and the merge rule, 2026-08-25 —
**6 planted, 6 killed** (one after a fix):

| Planted bug | Tests that caught it |
|---|---|
| PDF text overwrites an API-supplied title | 1 |
| Unreadable scan reported as "no_section" instead of "unreadable" | 1 |
| Vancouver / numbered entry style dropped (APA-only detector) | 1 |
| De-hyphenation removed (titles keep "ben- efits") | 1 |
| `pdf_only` stops marking its output as PDF-sourced | 1 |
| DOI dedupe removed — bare-DOI references appear twice | 1 |

The DOI-dedupe mutation initially SURVIVED: the existing dedupe test
supplied author+year as well, so the weaker guard covered for the
missing one. `test_bare_doi_reference_is_deduped_by_doi_alone` was
written to close that, and the mutation now fails it. This is the
reason mutations are run rather than assumed.
