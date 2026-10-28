# Corpus Changelog

Manual change log — appended by hand, one section per session or per commit
cluster. Only the notable changes; git log has the full record.

Newest entries at the top.

Release sections are titled `v<version> — <summary>`. `build_ship.py`
refuses to build unless a section naming the exact version exists.

---

## v0.4.2 — Windows PDF viewer: ship pdf.js in the Windows source

Patch release on 0.4.1 (2026-10-01).

### Fixed

**Windows: the PDF viewer never started.** On v0.4.1 the viewer's own
readout said `pdf.mjs: HTTP 404` (Jack, Windows, 2026-10-15). Every
Windows source zip from v0.2.0 to v0.4.1 was missing
`src/vendor/pdfjs/build/` — `pdf.mjs` and `pdf.worker.mjs`. The zip
builder dropped every directory named `build`, a rule meant for
PyInstaller's output, and that also matched pdf.js's folder. The
macOS app was never affected. This was most likely the black viewer
reported on v0.4.0 as well; the 0.4.1 content-type fix is real (the
readout now shows `viewer.mjs` served as JavaScript) but was not the
whole problem.

The zip builder now also fails if any file in a shipped directory is
missing from the zip, not only if something extra is in it.

**The same pattern in `.gitignore` kept the two pdf.js files out of
git**, so no release tag could rebuild the app it named. Both files are
now committed and the ignore rules are anchored to the repo root.

### Numbers

- Tests: 3 new Windows bundle tests (pdf.js modules present, verifier
  rejects a dropped file, no shipped source is git-ignored); each was
  confirmed to fail with its original bug planted back.

## v0.4.1 — Windows PDF viewer fix, current pickers, and notes that keep your place

Patch release on 0.4.0 (2026-09-29). Details in the dated sections below.

### Fixed

**Windows: the PDF viewer showed its toolbar over a black page.** The
server took each file's content type from the operating system, and
Windows can report JavaScript as plain text, which stops pdf.js's modules
from running. Content types for scripts, styles, pages, SVG, JSON and PDF
are now fixed by Corpus. If the viewer still fails to start, it now says
so and lists the type each viewer module was served with. Not yet
confirmed on Windows.

**The note link picker and the project member picker now show papers
added after the window opened**, including in popped-out notes. Both
refetch their list every time they open.

**A popped-out note opens where you were reading** instead of at the top.

### Changed

**Deleting a note moved into a Settings menu** in the note header (×,
Escape or a click outside closes it).

### Numbers

- Tests: 556 Python + 147 JS (was 547 + 130 at 0.4.0).

### Known limitations, unchanged

- The Windows build is still source plus `build_windows.bat`; this is the
  first release whose Windows fix needs confirming there.
- No fresh-account smoke test (SHIP_PLAN Steps 10-11).

---

## 2026-09-29 — A popped-out note opens where you were reading

Jack: "when i pop out a note i lose my place where i was scrolling."

The pop-out is a new window that loaded the note at the top. Now **Pop
out** records which paragraph (top-level block) is at the top of the view
and how far into it you are, passes that in the pop-out's URL, and the
pop-out scrolls to the same spot once it has drawn the note.

- Anchored to a block, not a pixel offset: the pop-out is a different
  width, so the text reflows and pixels would land elsewhere.
- A note at the top, or a note that got shorter, opens at the top.
- Only on popping out; the main window's position when the pop-out
  closes is unchanged.
- Tests: `tests/src/note-scroll-place.test.js`; five planted bugs caught.
- Not clicked through in the app.

---

## 2026-09-29 — Pickers show papers added after the window opened

Jack: "it seems like when a note is popped out, the link paper feature
doesnt update when new papers are added to the corpus".

Cause, from the code: the note link picker read the window's own paper
list and fetched it only if it was empty. After an import, only the
window that ran it reloads its papers, so a popped-out note kept the list
from when it opened. The project member picker had the same rule.

- Both pickers now refetch the chosen type's list every time they show
  it, in every window. What the window already has is shown at once and
  replaced when the fresh list arrives.
- The refetch does not re-render the tab that owns the list, so an open
  document's PDF is not reloaded.
- Each list's endpoint is now written once, as `listUrl` on its MODES
  entry, and read by both the tab and the pickers.
- Tests: `tests/src/fetch-mode-list.test.js`,
  `tests/test_picker_fresh_lists.py`; five planted bugs caught.
- Not clicked through in the app.

---

## 2026-09-29 — Note delete moves into a Settings menu

Jack: "make the delete button on a note hidden behind a settings button
that opens a drop down with settings with and x to close settings. only
option there is delete for now".

- The note header's **Delete** button is replaced by **Settings**, which
  opens a small menu titled "Settings" with a × to close it. Its one
  item is **Delete note**, which closes the menu and then asks for
  confirmation exactly as before.
- The menu also closes on Escape or a click outside it.
- Same header in the docked note and the popped-out note window.
- The old button's tooltip is gone with it.
- Tests: `tests/src/note-settings.test.js`; five planted bugs caught.

---

## 2026-09-29 — Windows PDF viewer: pin script types; say why when the viewer fails

Jack, on the Windows build: "the windows pdf viewer is completely black.
it shows the controls but no PDF".

**Most likely cause, not confirmed on Windows.** Flask serves each file
with the type Python's `mimetypes` reports, and on Windows that table is
overridden from the registry. A registry mapping `.mjs`/`.js` to
`text/plain` makes the browser refuse pdf.js's ES modules (`pdf.mjs`,
`viewer.mjs`, the worker) while the main app, which is all classic
scripts, keeps working. That matches the report exactly: the toolbar is
static HTML and still draws; the page area stays at pdf.js's dark-mode
background. Reproduced on macOS by simulating that registry: the modules
came back `text/plain`.

- **Fix:** `server.WEB_MIME_TYPES` pins `.js`, `.mjs`, `.css`, `.html`,
  `.svg`, `.json`, `.pdf` at startup, over whatever the OS says.
- **Readout:** if pdf.js still does not start, the viewer now shows "The
  PDF viewer did not start." plus the type each viewer module was
  served with, instead of a silent black pane. If that box appears on
  Windows after this fix, the cause is something else, and the box says
  what.
- Tests: `tests/test_web_mime_types.py` (hostile-registry simulation,
  startup order, a walk of `src/` for unpinned types),
  `tests/src/viewer-failure.test.js`. Three planted bugs caught.
- Not verified in a real browser or on Windows.

---

## v0.4.0 — Documents, stored citers, and notes that cannot lose edits

First release since 0.3.0 (2026-09-18). Each item below is described in
detail in the dated sections underneath; this is the release-level
summary.

### New

**Documents tab.** Upload a PDF that is not a paper — a book chapter, a
handout — and read, search, highlight and annotate it with the same
viewer and note gutter papers use. No online lookups. Documents can be
renamed, popped out into their own window, linked from notes, and added
to projects. They live in `<corpus>/documents/`, apart from papers.

**Note workspace.** A note can be popped out with a PDF panel beside it.
The panel's Info view is the full paper view. Links in a note can point
at one highlight, and clicking one scrolls to that highlight.

**Link picker sorting.** Every kind of link target (papers, authors,
institutions, journals, documents) can be sorted by any of its fields,
e.g. papers by date added, newest first.

**Stored citers.** Every paper's known citers are fetched on import,
stored, and shown in the info panel. A resumable backfill fetches them
for the whole corpus.

**Title lookup for papers whose DOI never resolved**, in Crossref,
OpenAlex and Semantic Scholar.

**Back and forward navigation**, and **add to project from the paper
pane**.

### Fixed

**A note edited in a pop-out could be overwritten by the main window's
older copy** — real data loss, reproduced from the event log. Notes now
carry a revision counter; a stale save is refused with a choice to load
the saved version or keep yours.

**Re-extract no longer orphans papers.** Popped-out notes no longer sit
blank for minutes after a restart. Adding a note link keeps your scroll
position. Supplementary PDFs are no longer taken for the paper.

**OpenAlex requests now carry the saved API key and email.** They were
stored but never sent.

**The app stopped telling you it had no corpus while it was still
loading one.**

### Faster

The bridge search reads the stored citers instead of refetching them,
and skips citer stores that have not changed since the last run. Imports
run one at a time, with a progress banner whose counters tick in place.

### Numbers

- Tests: 547 Python + 130 JS (was 349 + 82 at 0.3.0).

### Known limitations, unchanged

- The Windows build path still has not been run on Windows. The Windows
  zip is build source plus `build_windows.bat`, not a ready `.exe`.
- No fresh-account smoke test (SHIP_PLAN Steps 10-11).
- Documents cannot be deleted from the app yet (ROADMAP).

---

## 2026-09-28 — Sort the note link picker, for every kind of link

Jack: "when i link a paper to a note, i want to be able to change what is
being sorted by for all the options. so i can sort by most recent added
papers for example."

- The link picker has **Sort by** and a direction toggle beside the
  filter. Papers: Author · Year · Title · Date added. Authors: Name ·
  Papers in corpus. Institutions: Name · Papers in corpus · Country.
  Journals: Name · Papers in corpus. Documents: Title · Date added.
  Picking a field starts it in its natural direction (dates newest
  first, counts largest first, names A→Z). The choice is remembered per
  type.
- One definition: each tab's options live on its MODES entry (`sorts`)
  and one pure sorter (`src/sorting.js`) serves both the picker and the
  Papers sidebar, whose menu is now built from the same list. The
  sidebar's private `_sortPapers` is removed.
- Sorting happens before the picker's 200-row cap, so "newest first"
  finds the newest paper in a 1,000-paper corpus. Blank / "unknown"
  values sort last in both directions.
- Tests: `tests/src/sorting.test.js`, `tests/test_link_picker_sort.py`;
  three planted bugs caught.

## 2026-09-28 — Corpus.command closes its Terminal window once Corpus is up

Jack: "when i use the corpus command it should close the terminal after
corpus has been opened". The script now starts Corpus detached from the
terminal (its own session, via Python's `os.setsid` — macOS has no
`setsid` command), checks after 3 s that it is still running, then exits
and closes its own window: a detached helper asks Terminal, via
AppleScript, to close the window whose tty matches. No Terminal setting
is needed. (An intermediate version relied on Terminal's "close if the
shell exited cleanly" setting instead; Jack rejected needing a setting,
and `8d95afc` restored the self-closing version. This entry said
otherwise until 2026-09-29.) Output goes
to `~/.corpus/logs/launcher.out`. If Corpus dies during startup the
window stays open with the last 30 lines. Quit Corpus by closing its
window; Ctrl-C in Terminal no longer applies. Not testable from the
suite — verified by double-clicking.

## 2026-09-28 — A note edited in a pop-out can no longer be overwritten by the main window

Jack: "when i am editing a note in the popped out form, it doesnt save it.
i just spent a little while on the prelims table notes and when i closed
that tab and went back to the notes page, it wasnt updated".

The pop-out DID save (server.log: 11,385 chars at 12:59–13:05). When it
closed, the main window unlocked the note and re-drew it from the copy it
held from before the pop-out; its next autosave sent that copy back
(11,374 chars, the exact pre-pop-out length, at 13:06:12). Data loss. No
backup existed to restore from.

- **Unlock reloads from disk.** When a popped-out note closes, the main
  window fetches the note again instead of re-drawing its old copy.
- **Stale saves are refused.** Notes carry a `revision` counter; every
  save names the revision it was edited from, and the server answers 409
  instead of writing if the note has moved on. The editor then stops
  autosaving and shows a banner — "Load the saved version" or "Keep
  mine" — so neither version is discarded without a choice. A counter,
  not `updated_at`: that has one-second resolution.
- **Closing a window no longer drops the last keystrokes.** A save still
  inside the 800ms debounce is sent with `keepalive` on `pagehide`.
- Tests: `tests/test_note_stale_writes.py`; three planted bugs (guard
  off, unlock from memory, client omitting its revision) all caught. The
  JS harness now models `window.addEventListener`.

## 2026-09-25 — Documents: note links, rename, pop-out, projects

Jack: "should be able to link documents from notes. also renaming should
be enabled. document pop out should also be implemented. and documents
can also be added to projects".

- **Note links.** Documents appear in a note's link picker; clicking one
  opens it (in a popped-out note, in the side panel). "Link highlight"
  works on a document open in the panel — the link names the document
  (`data-open-document`), not a paper. The note sanitizer allows the new
  attribute; its parity test with MODES keeps the two lists together.
- **Rename** in place: the title becomes an input; Enter or leaving the
  field saves. Only the title changes — the id, which links, projects
  and highlights point at, never does.
- **Pop out ⧉** opens the document in its own window with the full
  viewer and note gutter; the main pane shows the usual "open in a
  separate window" placeholder.
- **Projects** accept documents as members, listed and linked like
  papers and notes.
- **One lock for both kinds.** A note panel's claim is now the same
  `<kind>:<id>` key a pop-out window uses (it was a bare paper slug), so
  a document in a panel and the same document popped out refuse each
  other, and a paper slug that equals a document id is not a collision.
- Delete is still missing — ROADMAP.

## 2026-09-25 — Documents tab: read and annotate PDFs that are not papers

Jack: "i want to add an another documents tab. for now i will just be
uploading a pdf of a book chapter. i dont want any fancy integrations
aside from all the text, highlight, and note features for the paper
pdfs. but none of the api stuff."

- New **Documents** tab with **Add document…**. The PDF opens in the same
  viewer as a paper: text selection and search, highlights, Note Mode,
  anchored notes in the gutter, undo/erase. Title is the filename,
  tidied. Nothing is looked up online.
- Stored in `<corpus>/documents/<id>/` — outside papers/ and summaries/,
  so Scan, citers, bridges and the paper list never see a document.
- Shared rather than copied: the highlight cleaner moved to
  `highlights_store.py` (papers and documents), the PDF-pane markup to
  `app.js::pdfPaneHtml`, and every note-gutter / viewer lookup now finds
  the live pane through `_pdfPaneRoot()` instead of a hard-coded
  `#paper-detail`. The viewer picks its highlights endpoint from the PDF
  URL (`highlightsApiFor`).
- Left for later (ROADMAP "Documents tab"): linking a document from a
  note, delete/rename, pop-out, projects.
- 7 Python + 3 JS tests; planted bugs (viewer ignoring documents, a
  document written into papers/) both caught.

## 2026-09-25 — Adding a link keeps your place; supplements are not the paper

Jack: "when i add a paper via a link it scrolls up to the top of the
document. also did taatgen import".

- **Adding a link no longer jumps to the top of the note.** The link
  picker takes focus, and the editor took it back with a plain
  `focus()`, which scrolls to a fresh caret at the top before the saved
  position is restored. `_restoreCaret` focuses with `preventScroll` and
  replaces the three copies of that pattern (paper/entity link,
  highlight link, font-size input). `tests/src/note-caret.test.js`
  checks the helper and that no scrolling `focus()` remains.
- **Taatgen 2013 had imported as its own supplement** — slug
  `2013-19654-001`, title "Supplemental Material for The Nature and
  Transfer of Cognitive Skills", DOI `10.1037/a0033138.supp`. APA
  supplement DOIs now collapse to the paper's (`.supp` stripped, like
  Crossref's `/-/`), and a record titled "Supplemental Material for…"
  is refused as not the paper on every path. Re-extracted: now
  `taatgen-2013`, `10.1037/a0033138`.
- **A stored citer list now counts only for the DOI it was fetched
  for.** Taatgen's store had followed the rename but held the
  supplement's citers, and the fetch step skipped it as done. Refetched:
  296 citers. Any re-extract that changes a DOI would have kept stale
  citers the same way.

## 2026-09-25 — The note panel shows the full paper info

Jack (bug report): "i should be able to see all the paper info here. not
just this limited info" — the Paper info tab in a popped-out note's side
panel showed title, authors, year, venue, DOI and abstract only.

- The panel had its own compact renderer because the full one wrote into
  `#paper-detail` throughout. `renderDetail` is now a thin wrapper around
  `renderPaperInto(host, d, opts)`, whose every element lookup is scoped
  to `host`; the panel calls the same function. The compact copy
  (`_infoHtml`) and its five CSS rules are deleted.
- Panel mode leaves out the Paper info / PDF subtabs (the panel has its
  own), pop-out, Re-extract and Add to project — the last two re-select
  the paper in the main pane.
- `Citers.load` takes the host to paint into, and Find bridges reloads
  whichever view it was clicked in (`opts.reload`) instead of always the
  main pane.
- `tests/test_paper_view_single_renderer.py` pins both regressions: the
  panel growing its own renderer again, and the renderer reaching for
  `#paper-detail`. Both planted, both caught.

## 2026-09-25 — Papers whose DOI never resolved are found by title

Jack: "revisit whether it is feasible to get the cross ref, ss, or oa
specific id from the title if the doi isnt found … look at the unknown
ones in corpus". A read-only probe of the 11 `doi: unknown` papers showed
the services had nearly all of them (with correct titles: OpenAlex 10,
S2 9, Crossref 8) but Corpus's own extracted titles found only 2. Both
halves fixed:

- **Title extraction groups page-1 LINES, not spans.** Titles set in
  mixed sizes lost words ("A New Theory of Disuse and an Old Theory of
  Stimulus Fluctuation" → "Theory Disuse Theory and Stimulus
  Fluctuation"). Lines within 12% of a size tier stay together, and word
  breaks come from the gap between spans — some PDFs store no spaces
  ("TheLearningofCategories:").
- **Title lookup tries OpenAlex and Semantic Scholar after Crossref**
  (`_resolve_by_title`), by the method ROADMAP verified in August:
  OpenAlex `filter=title.search`, S2 `/search/match`, similarity ≥ 0.90.
  A DOI from any of them gets the normal three-source lookup.
- **Works with no DOI are recorded from their own ids.** bjork-1992 and
  snow-1980 now carry OpenAlex / S2 ids, title, year and counts. They
  are not yet LINKED (citations match on DOI) — see ROADMAP.
- **/Info and page-1 titles are both tried.** Page 1 used to be skipped
  whenever /Info held any plausible title, which is why Guadagnoli & Lee
  (filed as `download`) never resolved.
- **Guards added after they failed on real papers:** 1–2 word seeds are
  never searched ("Considerations" is how Bjork 1994 became
  DeLucia-Waack 2006); journal front matter ("…: Editors.") is refused on
  every path — snow-1996 was renamed `noauthorshipindicated-2002` twice
  during this work, restored both times from backup.
- **Result on the corpus:** 6 of 11 recovered, none mis-identified —
  guadagnoli-2004, karni-1991, knowlton-1993, lehmann-2016 by DOI;
  bjork-1992, snow-1980 by OpenAlex / S2 id. Citers fetched for the four
  with DOIs. Left: 3 scans (OCR), 2 whose title is not the largest type.
- 11 new tests in `tests/test_title_resolution.py`; 8 planted bugs, all
  killed (one survived the first version of the near-miss test, which
  was fixed to sit between 0.5 and 0.90).

## 2026-09-24 — The bridge search stops re-reading citer stores that did not change

Jack (bug report): "even tho it has most citers stored, it still loops
through them. seems like could be smarter".

Measured on the live import that prompted it: ~0.6s per stored paper
(70 papers in 44s), so ~10 minutes to walk 1,038 stores that had
changed for a handful of papers — every paper's ids, DOIs, years and
titles parsed on every run.

- `citers.citer_ids_for` keeps a derived index of citing ids,
  `<corpus>/bridges/citer_ids.json`, keyed on each store's mtime and
  size. Unchanged stores cost a stat; changed ones are parsed. The
  first run after this change still reads everything once to build it.
- Parsed without going through `read_citers`, which would have held
  every paper's full payload in the server's memory.
- Progress counts only stores actually read, then only papers actually
  fetched. The phase is renamed "Fetching citations" → "Gathering
  citers", since on a normal run it fetches nothing.
- Replaces `stored_citer_ids`, now unused, with `citer_ids_for`.
- New totals: `citer_stores_read`. After an import it should be about
  the number of papers added; near the corpus size means the index has
  stopped working.
- Mutation-checked: disabling the index, dropping the mtime check, and
  trusting partial stores each turn the suite red.

## 2026-09-23 — The bridge search reads the citer store instead of refetching

Jack: "can you cache the results so it doesnt need to redo this stuff
every time? whatever can be done to speed up the import process".

Measured on the 99-paper import that prompted it: 39.5 minutes total,
**26.6 of them the bridge search** — one paginated OpenAlex request per
paper for all 935 papers, repeated in full on every import, for data the
per-paper citer store already held on disk.

- `citers.stored_citer_ids(slug)` returns the citing OpenAlex ids, or
  None when nothing COMPLETE is stored. `bridges_api` uses it for the
  `backward` map and falls back to `openalex_citers_of` only for the
  None cases. After an import that is none of them: the import fetches
  citers for what it added before the bridge search runs.
- A PARTIAL store is deliberately not trusted — an interrupted fetch
  would otherwise produce a short bridge graph with nothing saying so.
- **Behaviour change, not just speed:** `openalex_citers_of` capped at
  2,000 citers per paper; the store does not. Papers above that cap now
  contribute their full citer list, so bridge counts rise.
- **New limit, stated plainly:** bridges are now as fresh as the citer
  store. A paper cited since its citers were fetched is invisible to the
  search until it is refetched.
- `totals.citers_from_store` records how much came off disk, so a
  regression shows up as a slow run with that number at 0.
- Reverses the 2026-09-22 instruction to keep the two apart; Jack
  cleared it. The test that pinned that instruction is replaced by three
  that pin the new behaviour (store used, missing store fetched, partial
  store refetched), all mutation-checked.

## 2026-09-22 — One import at a time; progress readouts stop sliding

Jack, after a 100-paper import: "its still shifting the text as the
characters change. make each text its own thing that is anchored. also,
for the last batch it kept jumping between 100 and 98 papers total".

- **The 100/98 flicker was two scans running at once** (server.log,
  16:49:34 `added=64` and 16:49:36 `added=37`). Each counted the inbox at
  a different moment and both wrote into the one progress slot; they also
  raced over the same files. `/api/scan` and `/api/extract` now answer
  409 while a job is running, and the UI reports it as "already running"
  rather than a failure.
- **Progress writes are owned.** `progress.start()` returns a `Job`
  handle (or None = refused) and writes go through it; a write from a
  handle that does not own the slot is dropped and logged
  (`progress_foreign_write`). Replaces the module-level `step()` that
  wrote to whatever was in the slot. `compute_bridges_now(own_job=…)` is
  now `compute_bridges_now(job=…)`; the import hands its handle down
  through `_after_import`.
- **Each readout is anchored.** Step, count and elapsed each render into
  their own fixed-width right-aligned slot instead of one shared string,
  so a value changing width no longer moves its neighbours. The phase
  name is the only elastic part and truncates.
- Mutation-checked: removing the 409, removing the foreign-write guard,
  and rejoining the three slots each turn the suite red.

## 2026-09-22 — Coverage table matches what is collected, and is held to it

Jack: "it still seems to suggest that citer information is not being
collected by choice. can you verify that the list of information streams
is up to date and do what you can to make sure that information stays
updated going forward?"

- Fixed: "List of citing papers" OpenAlex cell now reads the stored citer
  list (✓ stored / ✗ not yet) instead of ⊘. SS stays ⊘ (not used).
- Fixed: "Versions across sources" (OpenAlex) was ⊘ but `versions` has
  been written all along — now a normal ✓/✗ cell.
- Audit of the remaining 14 ⊘ cells: none are written; they stay ⊘.
- New: `/api/paper/<slug>` returns `stores: {citers: bool}` from
  `papers_api.PAPER_STORES`; `STORE:<name>` cells read it.
- New guard: `tests/test_coverage_rows.py` parses both the table and the
  frontmatter writer. Fails if a row checks a key never written, a ⊘ row's
  key IS written, or a written field has no row and no recorded reason.
  Mutation-checked (re-⊘ versions, drop citer store, rename a key, start
  writing MeSH: all red). Known gap: it checks keys, not which column —
  moving a key to the wrong source column is not caught.

## 2026-09-22 — Citers are fetched on every import, and for the whole corpus

Jack: "can you fetch the citations for all the papers curently in corpus
and if its not the default to fetch that when a paper is imported, make
it so." It was not the default — only the bridge search ran after an
import.

Every import now runs **Fetching citers** for the papers it just added,
before the bridge search (which is next in line to use them). Only the
added papers: the whole corpus was ~3,000 OpenAlex requests at 742
papers. A citer failure never stops the bridge search or makes the import
look failed. Scan and Add PDFs had two hand-built phase lists; both now
come from `extract_api.import_phases`, and the phase name is one constant
(`citers.PHASE`) because the step counter matches phases by exact name.

`citers.backfill` does the corpus-wide run: lookups batched 50 DOIs per
request (~15 instead of 742), papers already stored skipped so an
interrupted run resumes, one paper failing never stops the rest.
`POST /api/citers/fetch-all` runs it in the background under its own job.

Fixed on the way: a per-paper "Find citers" started during an import
wrote its steps into the import's banner, because the single progress
slot silently refused the second job and the fetch reported anyway. It
now returns 409 "another job is running".

## 2026-09-22 — Progress banner: steps that move, text that holds still

Jack: "it always stays on step 1/6 … and the position of the text showing
the 1/6 keeps shifting as the seconds tick up."

**The stuck step.** The server's step number was right all along —
checked live mid-import: `phase_index: 4`, and the real `progress.js`
rendered "step 4 of 6". Earlier imports never reached step 3: their
bridge search failed within ~5s every time (`bridge_compute_no_papers`)
because OpenAlex was rejecting every lookup — the missing-key problem
fixed earlier today — and backfill (step 2) rarely has work. So the
banner went from step 1 straight to done. This import resolved 736
papers and runs through the bridge steps; **0 new rate-limit errors**
against 741 before, which also confirms the OpenAlex fix live.

One real weakness fixed anyway: polls were fired every 500ms whether or
not the last had answered, and under load a reply has taken 10s, so an
old snapshot could land after a new one and roll the step back. Now one
poll is in flight at a time, with `cache: "no-store"`.

**The jitter.** Elapsed time showed tenths, so the string changed width
ten times a second. Now whole seconds, then m:ss; the meta line uses
tabular digits and a fixed minimum width so counters tick in place.

## 2026-09-22 — Highlight links scroll to the highlight

Jack: "clicking on these links doesnt actually bring me to the place
where it is highlighted."

PDF.js renders pages lazily and a highlight's box is only drawn when its
page renders. `scrollToHighlight` looked for the box and gave up when it
was missing — which is every highlight on a page not yet scrolled to —
so a link opened the paper and stayed on page 1. The note window also
stopped re-sending after ~1.2s, often before the viewer was listening.

Now the viewer keeps one pending request per link: if the box is not
drawn it jumps to the highlight's page (from the stored highlight) and
finishes on `pagerendered`; a request that arrives before the document
or the highlights have loaded is kept for `pagesinit`. The jump happens
once and the request expires after 10s, so an unresolved link cannot
drag the viewer back later; repeats of a just-completed scroll are
ignored, so the sender can safely re-post for ~6s. Applies to highlight
links in the main paper pane too, which go through the same viewer.

The old test pinned the literal line that was the bug; it is replaced
by behavioural tests against the viewer's real functions
(`tests/src/highlight-scroll.test.js`, 5 of 5 mutations killed).

## 2026-09-22 — Stored citers, in the paper info panel

Jack: "implement a storage for the citers of each paper. integrate it
into the info panel and have clear distinctions like for references
about which citers are in the corpus. dont integrate the citers list
into any kind of bridge finder yet."

A new **Citers** section sits directly under References and reads as its
mirror. `Find citers` fetches every citer from OpenAlex (cursor paging —
page numbers stop at 10,000 and PRISMA has ~105k) into
`<corpus>/citers/<slug>.json`, never the summary: re-extract drops
unknown frontmatter keys, and a fatter summary slows every cold paper
list. Before fetching, the panel warns how many requests a big paper
will take.

Citers are split into **In your corpus**, each carrying the References
list's own "In corpus: <slug>" marker, and **Not in your corpus**, paged
50 at a time. The split is computed on every read from the citation
index's DOI map, so a paper imported tomorrow moves into the corpus
group with no refetch. A fetch that dies halfway is stored and labelled
partial rather than passed off as complete. The store moves with the
paper on a slug rename. Not wired into the bridge search — next in
ROADMAP.

## 2026-09-22 — OpenAlex requests finally carry the API key and email

Jack had an OpenAlex API key saved in Settings; it was stored in Keychain
and exported as `CORPUS_OPENALEX_KEY`, and no code ever read it. Every
OpenAlex request went out keyless, and the email (`mailto`) only reached
the User-Agent — while OpenAlex rate-limited 355 requests in one
afternoon. `oa_enrichment.py` also hard-coded a fake `mailto=x`.

`_api_http.with_openalex_auth` now appends `api_key` and `mailto` to
OpenAlex URLs only — the one function all six OpenAlex call sites
already pass through, so a new call site gets the key without anyone
remembering. The host check is exact so the key never reaches Crossref
or Semantic Scholar, batch filters are not re-encoded, and failure logs
print the un-keyed URL so neither the key nor the email lands in
server.log. 8 tests, 3 of 3 planted mutations killed.

---

## 2026-09-21 — Popped-out notes no longer blank for minutes after a restart

Jack: "when i clicked pop out on a note it is completely blank."

Nothing threw. After a restart, `/api/papers` took **251 seconds**: three
copies ran at once (main window, the pop-out, a reload), each reading
~620 cold summaries, and all finished together at 16:55:32. The note
window awaited that whole list before even fetching the note, so it sat
blank for four minutes. `~/Documents` is iCloud-synced (File Provider),
which makes each file's first read slow — the underlying cause, recorded
in ROADMAP.

Fixed: the pop-out loads the note first and the papers list in the
background (it only feeds panel titles). Concurrent cold reads of a
summary now share one read instead of each paying for it.

Also added while diagnosing: a boot failure now stays on screen instead
of a 3.5s toast over an empty window, and in dev every frontend error is
written to server.log (`client_error where=… msg=…` with the stack) via
`python/dev_only/client_errors.py`. The pywebview window has no visible
console, so until now a frontend exception left no trace anywhere. A
new `tests/src/boot.test.js` loads every script in index.html's order
and runs boot() in both a main and a popped-out-note window.

---

## 2026-09-21 — One editor per paper and note; progress banner; viewer URL; bug-report screenshots

Six bug reports from one afternoon, five of them in the note workspace.

**Double editing.** A popped-out note stayed fully editable in the main
window — papers had an "open in a separate window" placeholder, notes
never did — so two editors autosaved over each other. Notes now lock the
same way, and popping a note out first lands any pending autosave, so the
last ~800ms of typing is not lost to the window that loads before it
saves. A paper shown in a note window's PDF panel is now locked
everywhere else too. Separate windows share no JS state, so the lock
lives in launcher.py's `_Bridge` (`set_panel_paper`), the only process
that sees every window; it refuses a paper already popped out or held by
another note's panel, and tells the main window so its paper pane shows
the placeholder.

Found along the way: the paper placeholder's "Bring to front" / "Close
that window" sent the bare slug to the launcher, which has keyed windows
as `paper:<slug>` since notes became detachable — both buttons silently
did nothing. One shared placeholder now serves papers and notes and sends
the full key.

**Info / PDF switch** in the note window's panel. The info view is
compact (title, authors, year, venue, DOI, abstract); reusing the full
paper-info tab needs paper-detail's renderer to stop writing into
`#paper-detail` directly — ROADMAP.

**Table of contents open on load.** The paper pane's viewer URL carried
`pagemode=none`; the note panel's and the Testing tab's, each built
separately, did not. One `pdfViewerSrc()` now builds all three.

**Import progress banner.** It only appeared on the SECOND Scan press —
the first poll could beat the server's `progress.start()`, saw no job,
and stopped for good — and it never went away, because polling stopped
with the "done" line still drawn. Now: an 8s grace period for the job to
register, auto-hide 4s after done (15s after an error), and it floats
bottom-right instead of sitting in the layout, where it pushed the
paper count off-screen.

**"?" instead of a screenshot.** The report saved a 0-byte PNG. The
reporter un-clipped the sidebar before capturing; at ~600 papers that
is taller than WebKit's maximum canvas, which comes back unusable rather
than throwing. The sidebar is no longer un-clipped, the capture scales to
fit, and an empty capture is refused instead of filed.

The two remaining reports ("PDFs not loading", the highlight link that
errors) were the orphaned-slug bug, fixed in the entry below.

Suite 449 → 463 Python, 95 → 98 JS.

---

## 2026-09-21 — Re-extract stops orphaning papers; dev Testing tab

**Re-extract renamed Jack's working paper out from under him.** At
16:18:46 Re-extract on `pan-2025-1` resolved a canonical slug of
`pan-2025` and renamed the PDF and summary — and nothing else. 177
highlights, the paper's project membership and every note link stayed
keyed to `pan-2025-1`, which now 404'd. It surfaced as three separate
bug reports: "none of the pdfs are loading here" (note workspace), a
highlight link that "jumps to the paper but has an error", and the
missing highlights. Nothing was deleted; the data was restored by moving
the PDF and summary back.

Two fixes. Re-extract no longer renames for a collision suffix alone —
dropping `-1` changes a paper's identity for a cosmetic reason. And a
genuine rename now goes through `slug_migration.migrate_paper_slug`,
the one list of everything a slug owns. The suffix check first shipped
with a regex that also matched the YEAR (`pan-2025` → `pan`), the same
trap as the 2026-09-17 probe; a test caught it.

**Dev Testing tab.** Jack: "a list of features being tested … when you
click on one, it shows you side by side view of the extracted text and
the pdf. independently scrollable." The extractor prototype moved into
`python/dev_only/paperclean/` (stripped from ship) with its 13-paper test
set; each paper carries a note saying what it tests. Every click runs
the current extractor. A second pdf.js viewer in one window exposed a
latent bug — the paper pane trusted messages from ANY frame — so the
listener now accepts only its own viewer.

Suite 395 → 449 Python (54 new: extractor, Testing tab, rename).

---

## 2026-09-21 — File a paper into a project from the paper; the red box stops lagging

Jack, one report, two bugs: "can you add a button somewhere in the paper
view up here to add a paper to a project. also, dragging the red box is
super laggy."

**Add to project.** Membership was only ever editable from the project
side — open a project, add papers to it. The paper pane now carries an
`Add to project` button in the header action group (the area the report's
red box was drawn around). It lists EVERY project with the current ones
ticked and toggles on click, so one control both files and unfiles; an
add-only list would have left removal reachable only from the project
side, which is the asymmetry being fixed. It stays open between picks,
because filing a paper into two projects at once is the common case.

No backend work: `GET /api/member-projects/<kind>/<id>` and
`POST /api/project/<pid>/members` were both built for this and already
tested. The paper pane only renders the button and calls
`window.ProjectMembership.openFor` — every membership rule stays in
`projects.js`. Three seams fail silently if renamed (the exported name,
the `"paper"` kind literal, the two URLs), so all three are pinned.

The second picker also forced the modal markup to be shared:
`_pickerShell` now owns the overlay, filter and list for both. That was
a ROADMAP item; `notes.js`'s entity-link picker is still separate and
still noted there.

**The red box.** The bug reporter's annotation canvas is sized to the
screenshot's natural pixels, and a Corpus screenshot is the whole
scrolled page — 3422 x 16760, 57 MEGAPIXELS, in the report that raised
it. Every `pointermove` called `clearRect` over all of it and re-stroked
every committed box: roughly 230 MB of pixel writes per mouse movement,
several times per frame.

It now repaints only the dirty region — the union of where the preview
box was last frame and where it is now — coalesced to one
`requestAnimationFrame`, with the canvas rect cached for the drag
instead of a forced layout per move. Dragging a 200x100 box costs about
20k pixels instead of 57M. The maths that decides the region is pure and
lives in `src/dev_only/draw-geometry.js`, because getting it wrong is
silent: red smears where an old box was not erased. Undo and Clear still
do a full redraw, which is correct — they are not on a drag path.

Also fixed while in there: a pointer capture lost mid-drag left a stale
preview on the canvas, and dev-only scripts now load with `async = false`
so execution order is deterministic.

20 tests (13 JS, 7 Python), 11 of 12 mutations killed — the survivor was
a no-op comment insertion, not a behaviour change. Suite 388 → 395
Python, 82 → 95 JS.

## 2026-09-21 — The running server writes down its own address

Jack: "what are we waiting on? you keep getting stuck like this. fix
whatever you need to for this not to happen."

The cause was not judgement, it was a missing fact. `launcher.py` binds
an ephemeral port — a different one every launch — and that number was
recorded nowhere: not in `~/.corpus/`, not in `server.log`, not on
stdout unless the pywebview path failed. `/api/progress` has existed
since 0.3.0 and reports exactly which of six phases a long import is
on, and it was unreachable in practice because nothing knew its
address. So every long job ended in "press Scan and tell me what
happened" — a question the app could already answer.

`launcher.py` now writes `~/.corpus/server.json` on start and removes
it on both clean-shutdown paths. It carries the launcher's pid, and
`server_address.read()` returns None once that pid is gone: a file
orphaned by a crash cannot send the next reader at a port the OS has
since handed to an unrelated process.

Dev only. It lives in `python/dev_only/server_address.py`, which
PyInstaller strips, and `launcher.py` guards the import behind both
`srv.IS_DEV` and a try/except — an unguarded import would be an
ImportError on launch for every shipped user.

The durable half is documentation: `CLAUDE.md` gains "Seeing what the
running app is doing" with the two commands, the six import phases, and
an explicit ban on shell wait-loops (two were left spinning for 18 and
9 minutes that day after the jobs they watched were killed).

Also recorded, not fixed: OpenAlex returned 355 `Too Many Requests` in
one hour across two bulk imports, and `mailto` is empty in the config —
see ROADMAP. And a 10.4s `/api/progress` response was measured once
under heavy import load; three immediate retries came back in 0.19-1.1s,
so it is noted rather than diagnosed.

8 tests, all 8 mutations killed. Suite 380 → 388.

## 2026-09-21 — Note workspace: note left, PDF right, links to one highlight

Jack logged it as one bug; it was four features, all built.

**Pop a note out.** The detached-window machinery was paper-slug-shaped
end to end — the Map key, the pywebview bridge, the close event. It is
now `"<kind>:<id>"`. `launcher.py` needed no change at all: it only
ever used that string as a dict key. A hash with no colon still reads
as a paper, so windows popped out by an older build keep working.

**A PDF panel beside it.** `#note-workspace` splits the window. The
panel has its own post helper — app.js's `_postToViewer` targets
`#paper-detail .pdf-viewer`, which does not exist in this window, so
reusing it would have sent every message nowhere silently.

**Paper links load the panel instead of navigating.** Intercepted
BEFORE `switchMode`: switching tabs in a detached window tears down the
split layout, so intercepting afterwards would flash a broken pane on
every click. Only paper links redirect; an author link has nowhere to
go here and is ignored rather than blanking the window.

**Link to one highlight.** `Link highlight` arms a pick, the next
highlight clicked in the panel reports back, and the note gets a link
labelled with the highlight's own text — the "linked full quote".
Clicking it later opens the paper and scrolls there, in the panel or in
the docked Notes tab.

Three details that would each have been a silent bug:

* The link carries BOTH `data-open-paper` and `data-open-highlight`, so
  it degrades to an ordinary paper link wherever highlights aren't
  understood, and a highlight the user has since erased still opens its
  paper.
* `data-open-highlight` had to join the notes sanitizer allow-list or
  the link would survive until the next autosave and then vanish. It is
  deliberately NOT in `_NOTE_LINK_ATTRS` — that tuple mirrors the MODES
  entries declaring `linkAttr`, is parity-tested against app.js, and a
  highlight is a position inside a paper, not a tab.
* The pick branch runs before the Note Mode guard. Behind it, a pick
  armed from the workspace could never fire, because Note Mode is off
  by default.

### Tests

14 new. Twelve mutations planted, twelve killed — one only after
adding an adversarial case: splitting the detached key by anything
other than the colon survives almost every input, because the
unknown-kind fallback catches the garbage, but a paper slugged `notes`
would then open as a note.

Suite: 380 Python + 82 JS.

### Not done

Panel resize, a list of every paper a note links to, a `viewer-ready`
bridge message instead of retrying, and any view of which notes point
at a given highlight. All in ROADMAP. **None of it has been seen
running in a real window** — every assertion here is source-level or
sanitizer-level.

---

## 2026-09-21 — Back and forward

Jack: "can you add back and forward arrows somewhere up here so you can
navigate easily between different places?"

Two arrows left of the tabs, plus ⌘/Ctrl-[ and ⌘/Ctrl-] and Alt+←/→.

A "place" is `{mode, id}` — the pair every navigation already produces,
since each MODES entry declares the state key holding its selection.
Nothing new had to decide what a place is.

Recording hangs off ONE choke point: every mode's `select` is wrapped
at MODES-construction time. The alternative was adding a call inside
the six select functions, the deep-link handler, the arrow-key handler
and the project member list — five copies of one rule, and the copy
someone forgets is a place you cannot go back from. Two call sites
exist in total (the wrap and `switchMode`) and a test fails if a third
appears.

Browser semantics where they matter: revisiting the same place does not
stack duplicates, moving through history is not itself a move, and a
new move after going back discards the forward branch.

Tests execute the real recorder rather than asserting on source —
`_currentPlace` and `_recordPlace` are pure over `state`, so they are
extracted from app.js and replayed in node. Seven mutations planted,
seven killed.

Suite: 366 Python + 82 JS.

---

## 2026-09-20 — Corpus stops telling you it has no corpus

Jack: "i just re ran the command and it forgot my corpus location."

Nothing had forgotten anything. `~/.corpus/config.json` was correct and
untouched since 2026-09-17, and the corpus was whole — 209 summaries,
209 PDFs, no orphans. The app was SAYING it had no corpus.

### The message was the bug

`#empty-state` is visible from first paint and its markup read
"Welcome to Corpus — Pick a corpus directory to get started". `boot()`
cannot choose between that and the other states until `loadPapers()`
returns, and on a cold corpus that measured **19.86s**. So for twenty
seconds Corpus displayed setup instructions, complete with a "Choose
corpus directory…" button, to a user whose corpus was fine.

`showEmptyState` now has a third reason, `"loading"`, shown by `boot()`
BEFORE the read. It names the configured folder and hides the picker —
offering to change the folder mid-load is precisely what made a working
corpus look lost.

The first two reasons are CONCLUSIONS. Rendering one before the app can
reach it is the general form of this bug.

### The migration script had the identical flaw

`stage_batch.py --status` printed nothing until it had parsed every
summary, and the first line it printed was the corpus path. Twenty
seconds of silence, then the proof it had found the corpus. It now
prints the path, batch count and inbox state immediately, then the
counts.

### Measured, and NOT fixed

| | cold | warm |
|---|---|---|
| read 209 summaries (5.4 MB) | 19.86s | 0.04s |
| parse frontmatter | — | 0.08s |

About 95ms per file on first access — per-file latency, not bandwidth.
Parsing is not the cost (0.9ms typical). `/api/papers` needs only the
frontmatter but reads whole files, so 5.4 MB is read where ~0.5 MB
would do. Recorded in ROADMAP rather than fixed: `_read_summary` caches
`(fm, body)` as one unit and a head-only read needs a second cache
shape, which is real surgery on a cache with 13 tests — for a path
that is slow only on the first request after a cold start.

Checked and ruled out: iCloud (`~/Documents` is a real local dir, no
placeholders, no dataless flags). The disk is 96% full; whether that is
related is not established, and it is not something Corpus can fix.

### Tests

5 new, 5 mutations planted, 5 killed. The existing suite had six tests
on this exact element and caught none of it — every one asserted what
the states SAY, none asserted what shows before a state is chosen.

Suite: 354 Python + 82 JS.

---

## v0.3.0 — Projects, citation bridges, and a corpus that keeps up

First release since 0.2.0 (2026-09-01). Everything below is already
described in detail in the dated sections underneath; this is the
release-level summary.

### New

**Projects.** Folders of papers and notes that do not move anything. A
paper or note can belong to any number of them. Membership is stored on
the project rather than in each summary's frontmatter, because
`render_frontmatter` emits a fixed field list and would silently drop a
`projects:` key on the next re-extract — verified by probe before the
design was settled.

**Citation bridges.** Two papers with no citation between them are
often linked through a third that is not in the corpus. The connections
block now shows those, with hop count and each connecting paper's
title, year and citation count. Found by intersecting one paper's
references with the other's citers — measured ~3000x cheaper than
searching outward, and it answers every pair at once. On a 56-paper
corpus: 71 requests, ~21s, 71 bridges against 22 known direct links.

**Bridges run themselves after an import**, once per batch, in the
background.

**Visible progress for long jobs.** Scan, Add PDFs and the bridge
search all report into one channel: which step, which function, which
file, how much is left. Before this a 25-paper import showed one toast
and then 47 seconds of silence.

**Country names** instead of ISO codes, in all nine places one was
rendered.

### Fixed

**Two papers with no DOI could overwrite each other on import.** Slug
identity compared raw strings, so `doi: unknown` matched itself and the
second paper replaced the first — summary and PDF. Identity now uses
`normalize_doi`, which also stops re-imports forking duplicates when a
DOI is spelled differently.

**The corpus directory can no longer be pointed at Corpus's own source
tree.** It had drifted there, scattering empty `papers/ summaries/
inbox/` into the repo where git cannot see them. Refused now both when
the folder is picked and when the layout is scaffolded.

**Highlights stopped erasing each other.** The overlap test compared a
multi-line selection's bounding box instead of its actual glyph rects,
so highlighting lines 2-3 deleted an untouched highlight on lines 1-2.
The eraser shared the bug.

**Lists search what they display.** Six filters had their own idea of
what made a row findable, and the two pickers searched only the
rendered label — so a paper was not findable by author.

### Faster

Every list endpoint re-read and re-parsed the whole corpus on every
request; `parse_frontmatter` was 76% of server time. Parsed summaries
and the citation index are now cached and invalidated off the
filesystem. Warm requests are 6-50x faster; the first request after a
change costs ~11% more.

### Numbers

- Tests: 349 Python + 82 JS (was 216 + 71 at 0.2.0).
- Mutation-tested: 105 planted bugs, 104 killed.
- Routes: 44 (was 33).
- Exercised against a real 109-paper corpus during a 1108-paper
  migration from Paper Machine.

### Known limitations, unchanged

- The Windows build path still has not been run on Windows.
- No fresh-account smoke test (SHIP_PLAN Steps 10-11).
- `normalize_doi` does not collapse a double slash; measured as
  theoretical (8 such DOIs across two corpora, none clashing).

---

## 2026-09-17 — Visible progress, and bridges that run themselves

Jack, right after importing 25 papers: "whenever new papers are added
can you automatically search for bridges? and can you make sure that
the loading process is incredibly transparent so you can know what step
it is on, what function is being performed, and how much is left."

The log for that import is the whole argument: `POST /api/scan` took
26.6s, the bridge search another 21.4s, and the UI said "scanning
corpus…" once and then nothing for the remaining 47 seconds.

### The two halves depend on each other

Auto-running the bridge search was DECLINED three days ago and recorded
as declined — hanging a silent ~40s network call off Add PDFs is a bad
trade. Asking for visible progress in the same breath is what removes
the word "silent", so the two ship together. The ROADMAP entry has been
updated rather than left contradicting the code.

### One progress channel, not three

Scan, Add PDFs and the bridge search are three long jobs, and the
obvious move is three bits of progress plumbing that drift apart. There
is instead a single server-side job slot (`python/progress.py`) that
whatever is running writes into, and one endpoint the frontend polls.

Three levels, because Jack named three: the JOB, the PHASE ("what
function is being performed"), and the DETAIL (which file). Units are
per-phase — a job's phases count files, then papers, then requests, and
a single combined bar jumps backwards.

Scan declares its own phases plus the bridge phases, so the strip reads
"step 4 of 6" continuously instead of one job ending and another
appearing from nowhere. Measured on a 3-paper scan:

    [1/6] Reading PDFs              1/3  865.full.pdf
    [1/6] Reading PDFs              3/3  abir-2026.pdf
    [3/6] Resolving papers               reading summaries and matching to OpenAlex
    [4/6] Fetching citations        3/3  citations of abir-2026
    [6/6] Naming connecting papers       0 connecting papers

Polling rather than SSE: `launcher.py` runs werkzeug with
`threaded=True` (verified before building on it), so a poll is answered
while the scan still holds its request thread.

### Once per batch, in the background

The search runs after the whole batch, never per paper — a 25-file
import recomputing per file would spend 25x21s on an answer discarded
24 times. It runs in a background thread so `/api/scan` returns as soon
as the papers exist; the list appears immediately and bridges fill in
behind it, still reporting into the same job.

A failure there cannot look like a failed import: the papers are
already on disk, so the error names the bridge search specifically.

### Also

`compute_bridges_now()` was extracted out of the Flask view so the
import path can call it — a view function is not callable without
faking a request. `/api/scan` now returns `added`, because both the
frontend and the auto-bridge hook need it and deriving it client-side
would be a second copy of the rule.

### Tests

13 new. Nine mutations planted, nine killed — three only after
strengthening. The instructive one: the test for "don't run a search
when nothing was added" mocked the very function whose guard it was
checking, so the guard was never reached and removing it changed
nothing.

Suite: 349 Python + 82 JS.

---

## 2026-09-17 — Import identity: two DOI-less papers no longer overwrite each other

Jack, with 25 papers staged in the inbox and 1108 queued behind them:
"is corpus prepared to handle slug collisions? or if a slug is entered
as name-year-2 when no 1 is present?"

### The second half: yes

A `-2` with no `-1` correctly yields `-1`. The suffix search returns the
first FREE number rather than counting past what exists, so it fills
gaps. Corpus attaches no meaning to the number — "-1 = published first"
is Paper Machine's convention, not this project's. Now pinned by a test
so it stays true.

### The first half: no, and it lost data

`_resolve_slug_collision` decided "is this the same paper?" by
comparing `.strip().lower()` on both DOIs. Probed, not inferred:

| case | before | after |
|---|---|---|
| both `doi: unknown` | **same slug → overwrite** | `-1` |
| stored `10.1000/a`, incoming `https://doi.org/10.1000/a` | `-1` duplicate | same slug |
| stored url-form, incoming bare | `-1` duplicate | same slug |
| mixed case | `-1` duplicate | same slug |

The first row is the serious one. `doi: unknown` is what the extractor
writes when it cannot resolve one, and the literal string compares
equal to itself — so two DIFFERENT papers with no DOI, same first
author, same year, resolved to the same slug and the second silently
overwrote the first. Summary and PDF.

Rows two through four are how duplicate-DOI pairs get created, which is
a known open issue.

All four share one cause: a second, ad-hoc DOI comparison living next
to `normalize_doi`, which CODE_MAP already names as the single source
of truth. The fix deletes the ad-hoc one.

### A second gap in the same function

`final_slug = canon or temp_slug` — when metadata is too thin for a
canonical slug the inbox FILENAME becomes the slug, and that branch
skipped collision resolution entirely. The filename is deliberately
never an input to `canonical_slug_for`, but it is the last resort here,
and a last resort still needs the guard.

### Deliberately not fixed

`normalize_doi` still does not collapse a double slash, so
`10.1037//…` and `10.1037/…` compare unequal. Measured before
deciding: 8 such DOIs across both corpora, none clashing with a
single-slash twin. It is the single source of truth for the citation
index, the reference matcher and bridges, and a DOI suffix may
legitimately contain slashes — a general collapse risks merging two
different papers everywhere. Recorded in ROADMAP.

### Tests

13 new. Six mutations planted, six killed — two only after
strengthening the suite. Both instructive: every fixture wrote an
already-clean DOI into the existing summary, so normalising only ONE
side of the comparison passed; and the "corrupt file" fixture wrote
plain text, which `parse_frontmatter` handles without raising, so the
except branch was never exercised. Invalid UTF-8 is what actually
throws.

Suite: 336 Python + 82 JS.

---

## 2026-09-17 — Citation bridges

Jack: "how feasible would it be to check for bridges between papers in
the corpus? … can you make it so the corpus searches for the shortest
paper connection between papers like this?"

Two papers can both be in the corpus, have no citation between them,
and still be linked through a paper that is NOT in the corpus. That
middle paper is often the thing that explains why two lines of work
belong together. The connections block now shows those, with the hop
count and each connecting paper's title, year and citation count.

### The proposed algorithm was the expensive one

Jack's plan was to walk outward: take the new paper's references, then
their references, and so on. Measured on the real corpus, that is **64
requests and 18.4s for a single pair** (hop 1 expands to 58 papers, hop
2 to 3054) and it found nothing; a third hop would be ~2000 requests
per pair.

Meeting in the middle is ~3000x cheaper and answers every pair at once:

    forward(A)  = A's references        (already on disk, free)
    backward(B) = everyone citing B     (one request)
    bridge      = forward(A) & backward(B)

The asymmetry is what makes it work — median 58 references per paper
against median 24 citers. On the real corpus: **71 requests, ~43s, 71
bridges** against the 22 direct links already known. Those 22 matched
the existing DOI index exactly, which is what validates the method.

### Jack's termination rule is correct, and redundant here

"If the papers are older than the target there can be no connection" is
sound — citations point backwards in time. At depth 2 it does nothing,
because everything in `backward(B)` cites B and is therefore already
newer. It is recorded in ROADMAP for depth-3 work, where the frontier
does need pruning: measured effective branching is 4.0 for a 2020
target against 36.0 for a 2001 one.

### On demand, never on load

`/api/paper/<slug>` reads the cache and never touches the network — it
runs on every sidebar click, and a 43s call there would make the app
feel broken. `Find bridges` does the work; a test pins that the detail
path stays offline.

Three states the panel keeps distinct: not computed, computed-and-
empty, and stale. "No bridges" and "nobody pressed the button" are very
different claims.

### Semantic Scholar cannot serve this

Tried first. `/paper/batch` with `fields=references.externalIds`
returned `referenceCount: 67` next to an EMPTY references array, and
429'd even with a key set. OpenAlex returns complete `referenced_works`
inline, 5 papers per 504ms request, counts matching exactly. Also
measured: only 70% of local reference lines carry a parseable year
against 100% of works returned by the API.

### A bug in my own prototype, worth recording

The first run reported "no bridges found" across a 25-year gap in 0
requests. The cause was an id-format mismatch — reference ids come back
as `https://openalex.org/W123` but a filter needs the bare `W123`, and
a mixed filter matches nothing rather than erroring. `oa_short_id()`
now exists so every id crossing a boundary is short, and a mutation
test covers it. A zero-cost negative result is a bug until proven
otherwise.

### Tests

16 new, network fully stubbed — CLAUDE.md forbids live API calls in
tests and this is the feature where that is easiest to break. Thirteen
mutations planted, thirteen killed, three only after strengthening the
suite: the sort test's fixture happened to be in sorted order already,
the unknown-year test used two unknowns where the failure needs one,
and the corrupt-cache test passed through `bridges_for_slug`'s own
try/except without ever exercising the endpoint.

Suite: 323 Python + 82 JS.

---

## 2026-09-17 — Stop re-parsing the whole corpus on every request

Jack: "can you do a refactor to future proof the code and optimize
efficiency?"

### What was measured first

Profiled against a 590-summary corpus rather than guessed at.
`parse_frontmatter` was **76% of total server time** — 8,730 parses
across 9 requests where 590 would have done. Every list endpoint read
and re-parsed the entire corpus on every request, and `/api/citations`
walked it twice within a single request.

Scaling was already linear, so there was no algorithmic blow-up to
find. The waste was repetition.

### Two caches

`_api_common._read_summary` caches parsed frontmatter + body, validated
on **(mtime_ns, size)**. Both halves earn their place: mtime alone
misses a rewrite landing inside one clock tick, size alone misses a
same-length edit. It hands back a shallow copy — no caller mutates
frontmatter today, but one that did would otherwise poison every later
reader in the process.

`citations.build_index` memoises on (file count, newest mtime, total
size). Links stay derived and unstored, as the module docstring
promises; this only skips recomputing an identical answer.

Best-of-5, warm:

| Endpoint | 59 papers | 590 papers |
|---|---|---|
| `/api/papers` | 35.1 → 1.1ms | 198.5 → 10.2ms |
| `/api/authors` | 28.9 → 4.5ms | 229.4 → 32.1ms |
| `/api/institutions` | 46.9 → 7.0ms | 439.8 → 41.5ms |
| `/api/journals` | 20.9 → 1.1ms | 202.8 → 11.4ms |
| `/api/citations` | 65.1 → 1.3ms | 617.7 → 12.3ms |

The cold path costs ~11% more (an extra stat and copy per file),
measured over 7 runs. Paid once per change, against 6-50x on every
request after it.

### Three readers became one

Adding the cache surfaced that summaries were read three different
ways: `list_papers` globbed for itself, `paper_detail` did a raw
`read_text` + `parse_frontmatter` bypassing everything, and the rest
used `_walk_summaries`. All now go through `summary_paths()` +
`_read_summary()`.

That was not cosmetic. Cache pruning had been living inside
`_walk_summaries`, which `/api/papers` never calls — so entries for
deleted summaries leaked for the life of the process. Slug
canonicalisation renames files on re-extract, so deletions are routine.
Pruning now hangs off the single lister.

An orphaned `parse_frontmatter` import in `papers_api` was removed.

### Verified behaviour-preserving

All 10 endpoints hashed before and after against the real corpus:
byte-identical output.

### Tests

13 new tests, almost all about INVALIDATION — a cache returning stale
data is worse than the cost it saves. Speed is never asserted (flaky);
what is asserted is that work is skipped, by counting calls.

Ten mutations planted, ten killed — four only after strengthening the
suite. The most instructive: removing the defensive copy survived,
because the test mutated the result of a cache MISS, which is copied on
the store path anyway. Mutating a HIT is what catches it.

### What was NOT done

The "future-proof" half. Seven files exceed the 400-line smell
threshold, `src/app.js` at 1375. Splitting a file because it is long,
with no next feature pushing on it, produces two incoherent halves
rather than a better design. Measured and recorded in `ROADMAP.md`
under "Oversized modules — measured, not split"; three already have
plausible seams as existing expansion points.

Suite: 307 Python + 82 JS.

---

## 2026-09-17 — Countries show their names, not their codes

Jack: "can you also have it show the full name of the country? not sure
which one this is."

### Nine places, not one

OpenAlex stores ISO 3166-1 alpha-2 codes, and Corpus rendered them raw
in the institutions sidebar, three spots on the institution detail
(Country row, Location line, subtitle), three on the author detail
(last-known institution, institution list, subtitle), the journal
detail's Country of publication, and the per-institution meta in the
paper detail. Jack saw one of them. All nine now show the name.

Two of those — the rows explicitly ABOUT the stored field — show
"Netherlands (NL)"; the rest show the name alone, since repeating the
code in a sidebar line adds width without telling the reader anything.

### No country table

`Intl.DisplayNames` is ICU/CLDR data built into the runtime, so the
names come from the platform. A hand-written ISO 3166-1 list would be
~250 rows of fact sitting unverified in this repo, drifting as
countries are renamed — "CZ" became Czechia, "MK" became North
Macedonia. The alternative was to type it from memory and hope.

It is ES2021 (Safari 14+, so present in both the WKWebView pywebview
uses and the Edge WebView2 runtime on Windows). Every path falls back
to the raw code if it is absent or throws, so the worst case is exactly
the behaviour this replaced.

### Display and search kept together

The institutions list now displays "Netherlands", so `searchFields`
gained `Countries.name(r.country_code)`. Without it, typing what is
visible on screen would find nothing — the same defect fixed in the
Add-papers picker three days ago, which this change would otherwise
have reintroduced. The raw code still matches for anyone who types it.

### Tests

`tests/src/countries.test.js` executes the module in the vm harness —
it is self-contained and pure, which most of this frontend is not. The
interesting cases are all in the wrapper: `of("")` throws, `of("nl")`
returns "nl" unchanged rather than throwing (so a missing
`toUpperCase` would be silent), and `of()` echoes unknown codes back.

`tests/test_country_display.py` is the propagation guard: no module may
`escHtml()` a bare `country_code`, any module touching one must use the
helper, and the script must load before all five callers. Fixing one of
nine sites is the failure mode this catches.

Nine mutations planted, nine killed — one only after strengthening the
suite. Dropping the empty-code early return is behaviour-preserving
(the try/catch returns the same value), so it survived until a test
asserted the thing that actually differs: that Intl is never consulted
for empty input.

Suite: 294 Python + 82 JS.

---

## 2026-09-17 — The corpus dir cannot be the source tree

Jack: "can you set the dev corpus directory to the one ive been working
with."

### What it was actually set to

`corpus/dev` — the Corpus source tree itself. `ensure_corpus_layout`
had therefore scaffolded `papers/`, `summaries/` and `inbox/` into the
repo. All three empty, and **invisible to git**: git does not track
empty directories, so `git status` read clean and nothing reported it.
The app would have shown an empty corpus.

Re-set to `/Users/jackmostyn/Documents/CorpusTest` through
`POST /api/config` (the app's own path, not a hand-edit). Verified: 59
papers, 6 notes, 2 projects. The three stray directories were removed.

### Second occurrence, so it now has a guard

2026-09-09 the same setting had drifted to a Paper Machine folder of
4288 files. That fix only made the symptom legible — the empty state
names the configured path — and never stopped the scaffolding, which is
why there was a second time.

`_paths.is_corpus_source_tree(path)` is true for the repo or anything
inside it, identified by `launcher.py` and `pyinstaller_corpus.spec`
together. Enforced in two places because they fail at different
moments: `set_config` 400s with a plain message when the user picks the
folder, and `ensure_corpus_layout` raises rather than scaffolding, so a
`corpus_dir` saved before this guard existed still cannot pollute on
boot.

Deliberately narrow. It does NOT reject any git repository — keeping a
corpus under version control is a reasonable thing to do.

### An except that hid exactly this

`_apply_env` wrapped `set_corpus_root` + `ensure_corpus_layout` in
`except Exception: pass`, commented "corpus dir might not exist yet on
first boot". True, but it also swallowed everything else, including the
new refusal. CONTRIBUTING.md requires a log on every swallowing except;
this one had none. It now logs `corpus_layout_skipped` with a
traceback.

### A test that did the thing it was testing against

Mutation-testing the scaffolder guard revealed that the test for it
pointed `ensure_corpus_layout` at the REAL repo. With the guard mutated
away, the test scaffolded three directories into the repo — the exact
pollution it exists to prevent. It now builds a fake source tree in
`tmp_path`. A test for destructive behaviour must not be destructive
when the guard is absent.

### The test for the guard overwrote the real config

Found by mutation-testing this change, and worth recording because it
bit twice in one session.

`test_setting_corpus_dir_to_the_source_tree_is_refused` POSTs a real
path to `/api/config`. That is harmless while the guard works. With the
guard mutated away to check the test had teeth, the POST succeeded and
wrote `corpus/dev` into Jack's actual `~/.corpus/config.json` — quietly
undoing the corpus directory he had just asked to have set, which is
how the setting appeared to revert on its own.

`config_api` has always carried a `CORPUS_CONFIG_PATH` override
commented "so tests can point at a scratch file instead of stomping on
the real user's ~/.corpus/config.json", and CLAUDE.md has always
promised "tests never touch that path". Nothing used the override; the
promise rested on each test author remembering. `tests/conftest.py`
now has an AUTOUSE `scratch_config` fixture redirecting
`CONFIG_PATH` / `CONFIG_DIR` / `TOOLTIPS_PATH` for every test, and
`test_no_test_can_write_the_real_user_config` fails if it is removed.

Verified: with the guard deliberately broken, a full suite run now
leaves the real config untouched.

That is the second test in this change found to be destructive exactly
when the thing it tests is broken — the other pointed
`ensure_corpus_layout` at the real repo. Both are now sandboxed. It is
a pattern worth watching for: a test asserting "X is refused" is unsafe
whenever X is not, in fact, refused.

### Tests

13 new tests plus an autouse isolation fixture. Seven mutations
planted, seven killed. Two of the tests are standing checks on the
environment rather than on code —
`test_the_repo_has_no_scaffolded_corpus_directories` (git structurally
cannot see the pollution) and `test_no_test_can_write_the_real_user_config`.

Suite: 281 Python + 71 JS.

---

## 2026-09-14 — Every list searches the same way

Jack, against the Projects tab's "Add papers…" picker: "should be able
to search by author here as well."

### Cause

That picker filtered the rendered LABEL. A paper's label is
"Title (year)" — the author isn't in it, so typing an author name
matched nothing. The notes entity-link picker had the identical defect.

Meanwhile each of the four sidebars had its own inline multi-field
filter (papers searched author+year+title; journals searched
name+publisher+type+ISSN). Six copies of "what makes a row findable",
two of them strictly weaker. Adding author to one picker would have
made a seventh.

### Fix

`modeRowMatches(mode, row, q)` is now the single definition, and each
MODES entry declares `searchFields`. All six call sites derive from it.

`searchFields` returns an ARRAY and each element is tested separately,
because that is what the sidebars already did. Joining into one string
is the obvious shortcut and silently widens every filter in the app —
a query could straddle a field boundary and match text that appears
nowhere in the data.

### Filter boxes now say what they search

Placeholders read "Filter by title, author, year…" instead of "Filter
papers…", driven from a `searchHint` that sits directly beside
`searchFields` in the MODES entry so the promise and the behaviour are
edited together. Part of this report was discoverability: the old box
gave no clue either way.

### Two things found on the way

The modal pickers' filter inputs declared only width and margin,
missing the `padding` and `font: inherit` the sidebar boxes get — the
placeholder rendered in the browser's default search font pressed
against the border, visible as clipped text in Jack's screenshot.
`.note-link-filter` had carried that since the notes picker was built.
One rule now styles all six filter boxes.

`modeRowMatches` lowercased the field but not the query, relying on
every caller pre-lowercasing. All of them did, so it worked; the next
one would have silently gotten case-sensitive search. Caught by a test,
fixed in the matcher.

### Tests

17 new tests in `tests/test_list_search.py`, executed rather than
asserted as text: the real matcher and the real `searchFields` arrows
are extracted from app.js and run in node. Eleven mutations planted,
eleven killed — one only after the suite was strengthened, because
dropping the `!= null` guard does not throw (`String(null)` is "null",
so "nu" would match every row with a blank field).

Suite: 268 Python + 71 JS.

---

## 2026-09-14 — Projects tab

Jack: "i want to add a tab for projects. these are essentially folders
of notes and papers. the notes and papers arent actually stored in
these folders, just organized that way. papers and notes can be in
multiple projects. make sure you can create new projects and edit the
title etc."

### What shipped

A Projects tab: create, rename, describe and delete projects; add and
remove papers and notes; click a member to jump to it. A paper or note
can be in any number of projects, and nothing it belongs to moves it.

New: `python/projects_api.py` (blueprint, 6 endpoints), `src/projects.js`,
`_paths.projects_dir()` → `<corpus>/projects/<id>.json`, plus the tab
scaffolding in `index.html` and `.pj-*` styles.

### Membership is stored on the project, and that was forced

The obvious alternative — a `projects:` key in each summary's
frontmatter — is not merely untidy, it loses data.
`prefill_summary.render_frontmatter` emits a FIXED field list with no
pass-through, so anything it doesn't recognise is dropped when a paper
is re-extracted. Verified by probe before designing around it: a
`projects` key passed into `render_frontmatter` does not appear in the
output. That is the same reason highlights, pdf_refs and notes already
live in sidecar directories.

The reverse direction ("which projects contain this paper?") is derived
by scanning project files, the way `citations.py` recomputes links —
no second copy to desync.

Dangling members are filtered on read but never pruned from disk. A
paper can be temporarily missing; pruning would permanently forget the
membership the first time anyone opened the tab.

### The top-right action slot is now MODES-driven

`switchMode` hard-coded `const isNotes = (id === "notes")` to swap
"New note" in for Add PDFs / Scan. Projects would have made that a
second hard-coded branch — the same shape as the four deep-link
branches consolidated on 2026-08-27. A mode now declares `actionBtnId`
and switchMode iterates. `tests/test_mode_action_buttons.py` fails if
anyone names a specific tab there again.

That test file also pins the HTML↔MODES contract CLAUDE.md has always
promised ("adding a new tab = one array entry + matching HTML") — until
now nothing checked that the ids actually lined up.

### Caught during the build

Member rows first emitted `data-open-note`, reusing app.js's deep-link
delegation. That handler iterates `LINKABLE_MODES`, which contains
papers but not notes, so every note row was a link that did nothing.
Found while writing the CODE_MAP row for it, not by a test. Rows now
go through `switchMode` + `mode.select`, and there is a test.

### Tests

30 new tests. `test_projects.py` is behavioural (Flask test client);
the other two are source-level contracts. Nine mutations planted, nine
killed.

Suite: 251 Python + 71 JS.

### Not built (recorded in ROADMAP.md)

Adding a paper to a project from the paper detail pane; extracting a
shared picker shell; projects as note link targets.

---

## 2026-09-09 — Highlights no longer erase each other across lines

Bug: "when i highlight two lines with the highlight ending early on the
second line, then i try to highlight starting further down the second
line and going into a third line, it erases the first highlight even
though they are not overlapping."

### Cause

`highlightsOverlapping` compared each STORED rect against `boundsOf(new
selection)` — a single bounding box. Glyph rects are per-line, so any
selection spanning more than one line has a bounding box much larger
than the text inside it. Selecting the end of line 2 through line 3
produces a box that also covers the whole START of line 2, so a
highlight living there was judged overlapping and removed.

### Fix

The overlap query now compares every stored rect against every
selection rect. `boundsOf` had no other caller and was deleted.

### The eraser had the same bug

Both callers went through this one query, so dragging the eraser could
also delete highlights the drag never touched — including their
anchored notes, which is destructive and was not reported because the
false positives look like an imprecise drag. Fixed by the same change.

### Tests

New `tests/test_highlight_overlap_geometry.py` — the first behavioural
coverage of `corpus-highlights.js`. The two functions are pure, so the
test extracts them from the real source and runs them in node against
Jack's exact three-line scenario. Five planted mutations, five killed,
including a straight revert to the bounding-box version.

`test_highlight_erase_mode.py` no longer requires `boundsOf` to exist;
it asserts the guarantee (one overlap query, two call sites) instead.
TESTING.md's "nothing behavioural is covered there" note was true when
written and is now corrected.

Suite: 221 Python + 71 JS.

---

## 2026-09-09 — Note gutter stops yanking the PDF to the top

Bug: "when i am writing a note on a paper, it randomly jumps up to the
top of the document every once and a while."

### The loop

    type in a note card
      -> 600ms input debounce -> postMessage "update-note"
      -> iframe scheduleSave() 200ms -> saveNow() -> POST
      -> saveNow's wrapper calls notifyParentHighlights()
      -> parent handler calls _renderNoteGutter() UNCONDITIONALLY
      -> gutter.innerHTML = ...  destroys the focused textarea
                                 and zeroes gutter.scrollTop
      -> the zeroing fires a scroll event
      -> the capture-phase sync listener forwards "set-scroll: 0"
      -> the PDF jumps to the top

Roughly a second after you pause typing, which is why it read as
random. The `_scrollSyncing` guard did not help: it exists to stop the
two panes echoing each other, and nothing had set it — the scroll
originated from the innerHTML wipe.

### The fix

`_renderNoteGutter` now records which note ids it rendered
(`gutter.dataset.noteSig`). When the incoming set matches, it updates
the existing cards in place — anchor position, colour, title, text —
and never touches the DOM structure. Only a genuine change to the card
set (adding or deleting a note) rebuilds.

Two details that matter as much as the main fix:

- **A focused textarea is never written to.** Assigning `value` moves
  the caret to the end even when the value is identical, and the note
  text round-trips back from the server on every save. Without the
  `document.activeElement` guard the caret would jump to the end of the
  note about once a second — a quieter version of the same bug.
- **A real rebuild preserves scrollTop**, and sets `_scrollSyncing`
  while restoring it, so the restore is not itself forwarded to the
  viewer as a new jump.

### A regression caught while fixing it

The ResizeObserver teardown sat at the top of the function, which was
correct while every call rebuilt. With an in-place path that never
re-observes, disconnecting unconditionally would have killed
resize-driven relayout after the first update — cards would stop
reflowing as their text grew. Teardown now belongs to the two paths
that actually replace nodes, and a test pins that.

Mutations: 6 planted, 6 killed.

Tests: 216 Python + 71 JS (was 209 + 71).

---

## 2026-09-09 — An empty corpus now says so

Bug: "when i load corpus on the dev end i cant see my papers and notes".

### Cause

`~/.corpus/config.json` had `corpus_dir` pointing at
`.../Paper Machine/papers` — a folder of 4288 unrelated PDFs, not a
Corpus corpus. No data was lost; `~/Documents/CorpusTest` still held
all 57 summaries, 57 papers, 5 notes and 3 highlights. The pointer was
restored (a backup of the old config sits beside it).

### The actual defect

The app gave no indication anything was wrong. `loadPapers()` succeeded
with `[]`, `hideEmptyState()` ran unconditionally, and the result was a
blank sidebar and a blank pane. A mis-pointed folder looked EXACTLY
like a working corpus that happens to be empty.

`showEmptyState()` now takes a reason:

- `"no-corpus"` — first run, unchanged wording.
- `"empty-corpus"` — a corpus IS set but holds no papers. Says so, and
  **names the configured path**, which is what makes a mis-point
  obvious without opening Settings.

One element, two states — the markup is parameterised rather than
duplicated into a second `#empty-state` div.

### A docstring that was lying

`ensure_corpus_layout()` claimed it creates subdirs "if the user-picked
root is empty". It never checked. That is how it quietly scattered
`papers/`, `summaries/` and `inbox/` into a folder of 4288 files.

The scaffolding BEHAVIOUR is kept — pointing at a fresh folder and
having it work is the common case, and refusing would break that. What
changed is the docstring now says UNCONDITIONAL, and the UI surfaces
the state instead of leaving it silent. A test asserts the docstring
cannot drift back.

Also caught by the tests, and worth noting because it is a repeat
offender in this codebase: `.empty-state-path` sets
`display: inline-block`, which beats `[hidden] { display: none }`, so
it needs an explicit `[hidden]` override or the empty grey box shows in
the first-run state too.

Mutations: 6 planted, 6 killed — one only after a fix. Removing the
lines that POPULATE the path initially survived, because the test
asserted the `corpus_dir` and `#empty-state-path` lookups existed
rather than that the value was assigned. Checking that plumbing is
declared is not the same as checking it is connected.

Tests: 209 Python + 71 JS (was 203 + 71).

---

## v0.2.0 — Windows build path

Ships two artifacts instead of one:

    Corpus-v0.2.0.zip              the macOS .app, as before
    Corpus-v0.2.0-windows-src.zip  source + build_windows.bat

### Why source rather than an .exe

PyInstaller cannot cross-compile — a Windows executable has to be built
on Windows. The alternatives were shipping nothing for Windows, or
shipping the ingredients plus a script. The zip carries the same source
this release was built from and a `build_windows.bat` that creates a
venv, installs from the SAME `requirements.txt`, and runs the SAME
spec file.

### One spec, two platforms

`pyinstaller_corpus.spec` now branches on `IS_WINDOWS` for the three
things that actually differ: the icon (`.ico` vs `.icns`), the
pywebview/keyring backends, and `BUNDLE` (which produces a `.app` and
is skipped on Windows).

Forking a second spec was the obvious alternative and was rejected: the
hidden-import list is the part that rots, and a Windows copy would
drift the moment a module is added — with the drift only visible on the
platform nobody develops on. A test asserts the zip's spec is
byte-identical to the one the mac build uses.

The backend branch matters more than it looks. Both libraries discover
backends through entry_points, which PyInstaller's static walker cannot
follow. Ship the wrong set and the build SUCCEEDS, then the app opens
no window (pywebview) or silently fails to save API keys (keyring) —
the worst failure shape, because nothing looks wrong until a user hits
it.

### The source zip is an allowlist

`WINDOWS_SRC_DIRS` / `WINDOWS_SRC_FILES` name what goes in, rather than
copying everything minus a denylist. A denylist silently ships whatever
new top-level directory appears later; an allowlist fails loudly by
omitting something the build needs, which surfaces on Jack's machine
instead of as leaked data on a tester's. A post-staging walk then
verifies nothing excluded slipped through nested paths — `dev_only/`,
`.venv`, `.git`, tests, or a corpus left in the repo.

Gate D now covers both zips: a released Windows source zip is as
immutable as the .app zip, since a tester handed it must be able to
rebuild the same bits.

`dist_assets/Corpus.ico` was generated from the existing `.icns` with
`sips` (already on macOS — no new dependency). Single 256×256 image;
Windows downscales for smaller contexts.

### NOT verified, and it cannot be from here

Whether `build_windows.bat` produces a working `Corpus.exe`. That needs
a Windows machine. What IS verified: the spec evaluates correctly in
its Windows branch when extracted from the built zip, every build input
is present, and nothing dev-only leaks. The runtime code was already
portable — `reveal_in_finder` has had an `explorer /select,` branch
since the blueprint split, and `keyring` picks its own backend.

Mutations: 7 planted, 7 killed.

Tests: 203 Python + 71 JS (was 193 + 71).

---

## 2026-08-27 — Formatting chords in the note editor

⌘B / ⌘U / ⌘I / ⌘S now apply bold, underline, italic and strikethrough
in the note editor. Force-flush save moved from ⌘S to ⌘⇧S.

### The field was already there

`_NOTE_TOOLBAR` has declared `key: "b"` / `"i"` / `"u"` on the
formatting entries since the toolbar was written — and NOTHING read it.
Strikethrough had no `key` at all. So this change is mostly wiring up
dormant intent: strikethrough gains its `key`, and the keydown handler
resolves `e.key` against the spec instead of carrying its own list.
The toolbar spec is now the single place a chord is declared.

### Chords dispatch by clicking the button

The handler does not call `execCommand` itself. It finds
`.note-tb-btn[data-cmd=…]` and clicks it, because the click path
already does focus restoration, the indent/outdent special-casing, the
history checkpoint and the save schedule. A keyboard path that called
`execCommand` directly would skip all of that — most visibly the edit
would land outside the undo history, so ⌘Z afterwards reverts the wrong
thing. Both routes now share one implementation and cannot diverge.

### ⌘S was taken, and the old binding was moved rather than dropped

⌘S was force-flush save. Jack asked for ⌘S = strikethrough, so save
moved to ⌘⇧S. Autosave already covers the common case (debounced on
input, flushed on blur), but silently removing a binding that was not
asked about is its own bug. The formatting branch is checked BEFORE the
save branch and excludes Shift/Alt, so ⌘S and ⌘⇧S cannot shadow each
other — both directions are tested.

### Two of these tests are behavioural, which is new for the editor

`notes.js` loads cleanly in the vm harness, so
`tests/src/note-shortcuts.test.js` reads the REAL `_NOTE_TOOLBAR`
(via `vm.runInContext`, since a top-level `const` is not a sandbox
property) rather than asserting on source text. The keydown handler
itself still cannot be exercised — it lives inside `_wireNoteEditor`
and needs the note DOM plus `document.execCommand` — so its wiring is
asserted structurally in `tests/test_note_shortcuts.py`.

Not changed: ⌘B/⌘I/⌘U previously worked via native contentEditable.
They now route through the toolbar instead, which is what makes their
behaviour identical to the buttons.

Mutations: 6 planted, 6 killed.

Tests: 193 Python + 71 JS (was 187 + 66).

---

## 2026-08-27 — Single-step undo for highlights

Undo button in the PDF toolbar, plus Cmd/Ctrl-Z inside the viewer.
Covers the last highlight or unhighlight action, one level, no redo.

### One funnel, not five snapshot calls

There are five places that change the highlight set: add, recolour,
same-colour remove, subsume-on-overlap, erase, and the right-click
remove. Snapshotting at each would guarantee that the sixth one added
later forgets, and a forgotten site is invisible — Undo would restore a
STALE state, or revert a different action than the one just performed.

So every mutation now goes through `commitHighlights(label, fn)`, which
clones, mutates, renders, saves, notifies the parent, and refreshes the
button. A test walks back from each `state.highlights =` / `.push(` and
fails if it is not inside that funnel, so a new site cannot skip it.

Two details that are easy to get wrong and are now pinned:

- **The clone is deep.** Recolouring mutates `highlight.color` on an
  object already in the array, so `[...state.highlights]` would
  snapshot the NEW colour and undo would be a silent no-op for that
  case specifically.
- **Note edits clear the snapshot.** It is a whole-array clone, so
  applying it after the user typed a note would revert the typing along
  with the highlight change. Nothing to undo beats undoing something
  the user did not ask about.

Cmd-Z excludes Shift so the conventional redo chord falls through
rather than being silently swallowed by an undo that has no redo.

### A test of mine was over-specified and this change caught it

`test_erase_notifies_the_parent_so_note_cards_are_removed` required
`notifyParentHighlights()` to appear literally inside `eraseSelection`.
Moving that call into the shared funnel preserved the behaviour exactly
and still broke the test. It now asserts the guarantee — erase reaches
the funnel, and the funnel notifies — instead of the call site.

Coverage is structural only, same as the eraser: this file is an IIFE
in the PDF.js iframe that the `vm` harness cannot load. Whether Undo
actually restores anything is verified by hand.

Mutations: 6 planted, 6 killed — one after a fix. Removing `clearUndo()`
from the update-note handler initially survived because the test window
overran into the delete-note handler, which still had its call. Each
handler is now bounded to its own branch and both fail independently.

Tests: 187 Python + 66 JS (was 179 + 66).

---

## 2026-08-27 — Compact the detached-window header

Bug 20260827-122449: "do what you can to reduce the height of this
panel up here", filed from a popped-out window at 1728x1048.

The header measured roughly 215px, from two things stacked in parallel:
five metadata rows on the left (~143px) and FOUR action buttons in a
vertical column on the right (~146px). A popped-out window exists to
read the PDF, so all of that is paper the user does not see.

Changes, all scoped to `body.corpus-detached`:

- **Action buttons lay out as a row.** `.pd-head-actions` is
  `flex-direction: column` by default; that single flip reclaims most
  of the height.
- **"Pop out" is hidden.** In an already-popped-out window it
  re-focuses the window you are looking at — a control that does
  nothing, which is worse than no control.
- **Source file / Summary / Last updated fold onto one line.** Kept,
  not hidden: the source path is how you identify a paper whose title
  fell back to the slug.
- Title, author line, padding and margins tightened.

Deliberately NOT changed: the shared `.pd-head-actions` rule. The
docked pane sits beside a 340px sidebar where a horizontal row of four
buttons squeezes the title, so the compaction is detached-only. A test
asserts the base rule is still a column, because "fix" it there and the
main window regresses with nothing pointing at it.

**The pixel reduction is estimated, not measured.** There is no layout
engine in the suite, so the ~90-100px figure comes from CSS box
arithmetic. Jack sees the real result.

Mutations: 5 planted, 5 killed — one only after a fix. The mutation
that HID the source path instead of compacting it initially survived,
because the test helper could not read grouped selectors (`A,\nB { }`)
and silently returned an empty rule body, making the assertion
tautological. The helper now raises on a missing rule instead.

Tests: 179 Python + 66 JS (was 173 + 66).

---

## 2026-08-27 — Eraser for PDF highlights

Drag across text with **Erase** armed and every highlight the drag
touches is removed. No colour condition, no start-point condition.

### Why the old removal was hard

Removal fired only when the drag STARTED inside an existing highlight
**and** the active swatch matched that highlight's colour. Miss either
and you got something else entirely: a different colour recoloured the
highlight, and starting outside created a new highlight that subsumed
the old one. Two simultaneous conditions, neither visible in the UI.

The original rules are **unchanged** — the eraser is an additional
path, not a replacement. Recolour-by-dragging-inside still works, and
so does the right-click Remove.

### Notes are confirmed, everything else is silent

A note lives on its highlight (single-record model), so erasing
cascades to it. Erasing is silent EXCEPT when the doomed set contains
notes, which are user-authored prose with no undo — that case confirms
first, naming the count. Confirming on every drag would make the
eraser as annoying as the thing it replaces.

### Geometry extracted rather than copied

The eraser needs exactly what the highlight path needs: selection →
page → glyph-aligned rects → bounding box → overlapping highlights.
That was inline in `handleSelection`, so it was pulled out into
`resolveSelection` / `boundsOf` / `highlightsOverlapping` and both
paths now use it. Design-doc §3 explains why rects must come from text
spans rather than `range.getClientRects()`; a second copy would have
drifted from that and produced misaligned erase targets.

Two consequences that were easy to miss and are now pinned by tests:
`refreshInteractionMode` had to learn about erase mode (Note Mode flips
`pointer-events` off for the text layer, which would leave the eraser
unable to select anything), and the erase path must call
`notifyParentHighlights()` or a note card stays in the gutter anchored
to a highlight that no longer exists.

The Erase toggle is red, not the amber shared by Highlight and Note
Mode — it is the only destructive toggle in that toolbar. While armed,
existing highlights get a dashed outline so what is erasable is visible
before dragging.

### Test coverage here is structural only, and that is a real gap

`corpus-highlights.js` is an IIFE inside the PDF.js iframe: it returns
early without a `?file=/pdf/<slug>` param and needs PDF.js's page DOM,
a text layer, and a live selection. The `vm` harness cannot supply any
of that. `tests/test_highlight_erase_mode.py` asserts source-level
invariants — the ones whose violation is silent rather than loud —
and whether a drag actually erases is verified by hand. Recorded in
TESTING.md § Known gaps.

Mutations: 6 planted, 6 killed.

Tests: 173 Python + 66 JS (was 165 + 66).

---

## 2026-08-27 — Entity links in notes

A note can now link to a paper, author, institution or journal.
Insert with the 🔗 button in the editor toolbar; right-click a link for
"Go to <entity>" or "Remove link".

### It reuses the existing deep-link plumbing

The inserted markup is an ordinary
`<a data-open-paper="turner-2024">…</a>` — the SAME attribute every
detail pane already emits. app.js's click handler navigates it with no
new routing, so a note link and a reference link behave identically.

### MODES became the single source for linkable entities

The deep-link handler used to hard-code four branches (paper / author /
journal / institution), and `CODE_MAP.md` flagged it as "not yet
MODES-driven — see Wave 3". Adding notes would have made a fifth and
sixth copy of that list (sanitiser allow-list, link picker), so the
list was consolidated first: a mode is linkable exactly when it
declares `linkAttr`, and the click handler now iterates
`LINKABLE_MODES`. Adding a linkable entity is one declaration.

The one copy that cannot be avoided is the sanitiser's, because it is
in Python. That gets the treatment `entity-keys.js` already gets — a
parity test asserting the two lists match.

### The sanitiser was the whole risk

`<a>` previously allowed only `href` and `title`, so `data-open-*`
would have been stripped on save: links working in-session and dying on
reload, with no error anywhere. The allow-list now carries the four
data attributes plus a value pattern (`[A-Za-z0-9._-]{1,200}`) matching
real slugs and keys. Malformed values are dropped WHOLE rather than
cleaned — a half-scrubbed identifier would navigate somewhere
unintended instead of failing.

A round-trip through the real API caught a second instance of the same
bug: `class="note-entity-link"` was also being stripped, so links would
have rendered styled until reload and as plain text afterwards. The
class is now allow-listed to that one value, mirroring how `li` allows
only `li-phantom`.

### Menu code merged rather than copied

`_showNoteMenu(x, y, actions)` was extracted from the table context
menu so the link menu reuses it. The two differ only in their action
list; a second copy of the build / position / dismiss logic would have
drifted.

Also noted, not shipped: `src/notes.js` has a dormant plain-URL link
branch that no toolbar entry reaches. Left alone and roadmapped —
silently shipping an unrequested feature and silently deleting a latent
one are both worse than asking.

Mutations: 5 planted, 5 killed, including JS↔Python drift.

Tests: 165 Python + 66 JS (was 148 + 66).

---

## 2026-08-25 — PDF reference extraction (part 2) + labelled references

References read from the PDF's own printed list, as a THIRD source
alongside Crossref and Semantic Scholar. Validated against the existing
corpus before being wired in, per Jack's staging.

### Validation first — measured before implementing

Built as a prototype and measured against papers that already have
Crossref reference lists (ground truth) before any of it touched the
dev tree. Three rounds of measurement drove the design:

| | recall vs Crossref |
|---|---|
| APA-only entry detector | 46.4% |
| + Vancouver / numbered styles | 81.1% |
| + Cf-character stripping, initials-first, content fallback | **85.8%** |

Final state across all 57 PDFs: **49 ok, 7 no locatable section, 1
unreadable**. 3066 entries extracted, **0.1% structurally malformed** (missing author
or year). That figure does NOT cover title quality — a later check found
10.4% of titles are parse fragments. See ROADMAP.

The 71% "precision" figure the harness first reported was misleading
and was NOT accepted at face value. Fourteen sampled disagreements were
read by hand: every one was a real reference that Crossref simply had
not deposited. One of them (`hu-2025` citing `don-2019`) is a paper
already in the corpus. The ground truth is incomplete, not the parser.

### PDF is additive and never authoritative

`python/pdf_refs_merge.py` holds the rule and the reason. PDF data can
do exactly two things:

1. **Fill blanks.** A reference deposited as a bare DOI gets its author
   and title from the PDF entry with the same DOI.
2. **Append.** A PDF reference no API reference accounts for is added
   at the end, marked `pdf`, never merged into an API entry.

It never overwrites a non-empty API field — a Crossref title is a
publisher's assertion, a PDF title is the output of a regex over a
page. `test_pdf_never_overwrites_an_api_supplied_title` pins this.

Merged at read time rather than written into summaries, for the same
reason citation links are derived: rewriting the stored list would
destroy the distinction between "Crossref said this" and "we read this
off the page".

### References now show names and authors, not bare DOIs

726 of 2929 reference lines rendered as nothing but a DOI. Two fixes:

- PDF text supplies author/title where the deposit had none.
- A reference resolving to a paper **in the corpus** is labelled from
  that paper's own summary — exact by construction, since the DOI
  matched. This is what fixes the most valuable rows: the references
  the user can actually click.

Result across the corpus: **4426 references shown (was 2929), with
unlabelled entries down from 726 (24.8%) to 579 (13.1%)**.

Per-reference source badges now come from the server (`sources`:
C / SS / PDF / IN). The frontend previously re-derived the Semantic
Scholar half from frontmatter, which put provenance logic in two
places.

### Honest gaps, all roadmapped with measurements

- **PDF references are not in the citation index.** Links stay at 22,
  not 25. The PDF cache is populated lazily on paper view, so indexing
  it would make the graph depend on which papers had been opened.
  Deterministic absence beats links that appear after a click. Needs a
  read-every-PDF pass first.
- **579 references still bare.** Their PDFs print no DOIs, so there is
  no join key. Fixing needs a Crossref lookup per DOI.
- **7 papers yield no section** (Nature/Science layouts). All 7 already
  have complete Crossref lists, so nothing is lost today.
- **catrambone-1995 is a scanned image** — a 12-character text layer.
  Reported as `unreadable`, never guessed at. That distinction is
  tested: an empty list and an unreadable scan must not look alike.

Also decided empirically: title matching should use a 0.90 similarity
floor. Thresholds of 0.80/0.85/0.90 give identical results on this
corpus because every real match scores 1.00 — there is no fuzzy middle
ground, so the conservative floor costs nothing.

Tests: 148 Python + 66 JS (was 127 + 66).

---

## 2026-08-25 — Connections block: always show both directions

Jack asked for "a section in paper info showing which papers in the
corpus cite it". That section already shipped earlier the same day —
which means it was failing to communicate, and that is the actual bug.

### Why it read as missing

Two conditionals:

- The whole block returned `""` when a paper had no links in either
  direction.
- Each direction's heading was omitted when its list was empty.

So on `turner-2024` — cites 2 papers, cited by 0 — the pane showed a
"Cites (2)" heading and nothing else. There was no way to tell "no
paper in your corpus cites this" apart from "the reverse direction was
never built". An omitted section is indistinguishable from a missing
feature, and "nothing cites it yet" is a real answer to the question
the user asked.

Both directions now always render, with explicit empty states. The
block was also moved from 14th position in the paper-info pane (below
every OpenAlex block) to directly after the metadata grid.

### Empty states say which corpus they mean

"No papers in this corpus cite it." — not "No papers cite it." Corpus
knows nothing about the wider literature; the narrower claim is the
only true one.

Two further explanations were added, because a blank section invites
the reader to assume breakage:

- A paper with `doi: unknown` now says so, and that references to it
  cannot be matched. Matching is DOI-only, so its "Cited by" is
  permanently empty by construction — 2 of the 57 papers in the corpus
  are in this state.
- Reference counts now separate "no DOI, unmatchable" from "has a DOI,
  not in your corpus". Those are a metadata gap and a collection gap
  respectively, and conflating them makes the number look wrong.
  Papers with no reference list at all say that outright.

### Extracted to make the empty states testable

Markup moved from an IIFE inside `renderDetail` to `src/corpus-links.js`
(`window.CorpusLinks.render`), following the existing one-module-per-file
convention. The bug was invisible precisely because it only manifested
when a list was empty; `tests/src/corpus-links.test.js` now has 16 tests,
most of them about empty and degenerate inputs.

This is one block extracted ahead of the roadmapped `renderDetail`
split rather than the whole thing — justified because the boundary is
real (it renders `citations.py`'s output and will change as citation
features grow, while the rest of the pane won't) and because the bug
demanded a test that was otherwise impossible to write.

Mutation-tested: 6 planted, 6 killed. The replay of the original bug
(omit a direction when empty) trips 5 tests.

### Also fixed

`TESTING.md` documented the frontend runner as `node --test tests/src/`.
That form treats the path as a module and dies with `MODULE_NOT_FOUND`,
which looks exactly like a failing suite — it cost time during this
change. `test_frontend.py` was always correct (it enumerates files);
only the doc was wrong.

Tests: 127 Python + 66 JS.

---

## 2026-08-25 — Intra-corpus citation links (part 1 of 2)

When a paper's reference list points at another paper you already have,
that connection is now visible and queryable. Part 2 (extracting
references from PDF text for papers with no DOI) is deliberately not in
this change — see `ROADMAP.md`.

### The finding that shaped the design: no storage change was needed

The request assumed references would have to be re-stored to support
linking. They don't. Reference DOIs already survive
`Reference.to_md_line()` verbatim, so links resolve against summaries
that are already on disk. Measured on the real 57-paper corpus:

    55 papers with a usable DOI · 2929 references (2544 with a DOI)
    22 intra-corpus edges · 18 papers citing · 13 papers cited

Zero re-extraction, zero migration.

### Links are derived, never stored

Nothing writes a link to disk. Whether reference #40 points at a paper
you own depends on which papers you own *right now* — an `in_corpus`
flag next to each reference would go stale the instant a PDF is added,
and something would have to sweep the corpus to repair it. The index is
rebuilt from disk instead, so it cannot go stale.
`tests/test_citations.py::test_link_is_not_stored_so_adding_a_paper_creates_it`
writes a citing summary BEFORE its target exists, asserts the link
appears once the target lands, and asserts the citing file was never
rewritten. That test fails if anyone reverts to a stored flag.

### Matching is DOI-only, on purpose

Reference author blocks are usually a bare surname and titles are often
absent, so fuzzy title matching would produce false edges — worse than
missing ones for graph analysis, because a false edge is invisible
whereas a missing one is merely absent.

### One parser, one normalizer

- `parse_ref_line` / `parse_references_section` were added to
  `extract_references.py`, directly beside `to_md_line`. That file is
  now the only place in Python that knows the reference-line format,
  and `tests/test_ref_line_roundtrip.py` renders → parses → re-renders
  all 8 shapes to keep the pair honest.
- The JS `parseRefs` in `paper-detail.js` was DELETED. It was a second
  implementation of the same format with nothing keeping the two in
  step. The server now parses once and sends structured references.
- Two DOI normalizers existed with different rules (`_norm_doi` in
  `extract_references`, plus the one written for the index). Found by a
  mutation that survived. Consolidated into `_api_http.normalize_doi`;
  verified behaviour-preserving by re-running the index over the real
  corpus (22 edges before and after). A test now asserts both call
  sites are the same function object.
- `_api_common._walk_summaries` now yields `(slug, fm, body)` instead
  of `(slug, fm)`. The whole file was already being read to parse the
  frontmatter, so handing back the body costs no extra I/O and saves
  the citation index a second walk. Two aggregator call sites updated.

### API

- `GET /api/paper/<slug>` gains `references` (structured, each with
  `linked_slug`), `cites`, `cited_by`, and `ref_counts`.
- `GET /api/citations` — whole-corpus graph: nodes with degree counts,
  directed edges, totals, and `duplicate_dois`.

`duplicate_dois` is surfaced rather than silently resolved. Jack's
corpus has one case (`865.full` and `ashby-2022` share a JNeurosci
DOI — the same paper imported twice). Collapsing it would drop real
links; hiding it would leave inflated counts unexplained.

### UI

- New "In-corpus connections" block in paper detail: Cites and Cited by,
  with titles resolved from the already-loaded papers list.
- References that resolve get an "In corpus: <slug>" chip. This is most
  valuable on the DOI-only references Crossref deposits with no author
  or title at all — previously an opaque bare DOI, now a named paper.
- Both use the existing `data-open-paper` delegation rather than a new
  navigation mechanism.

Tests: 126/126 (was 80). Mutation-tested: 8 planted against the new
code, 7 killed; the 1 survivor is documented in `TESTING.md` as
unreachable rather than untested.

---

## 2026-08-24 — rejacktor onboarding

Corpus converted to rejacktor development discipline. No runtime code
changed; this is docs + build-gating only.

- **`CLAUDE.md`** (new) — project workflow file. Run / test / ship
  commands verified this session, the doc-log contract, and an explicit
  do-not-touch list (user's live corpus, `~/.corpus/`, Paper Machine,
  shipped zips, vendored PDF.js).
- **`ROADMAP.md`** (new) — single home for planned-but-unbuilt work.
  Seeded from `CODE_MAP.md`'s Wave-2/3 refactor candidates (5 open
  expansion points, each re-verified against the code on 2026-08-24)
  plus the three unfinished `SHIP_PLAN.md` steps. `CODE_MAP.md`'s
  "Known refactor candidates" section now points here instead of
  duplicating the list.
- **`README.md`** rewritten — the old one claimed Phase 1d "not built
  yet" while v0.1.1 was already in users' hands. It described a project
  that no longer exists.
- **`../ship/CLAUDE.md`** + **`../ship/SHIPS.md`** (new) — release-repo
  rules and the ship registry (one row per release: version, date, dev
  commit, size, notes).
- **`build_ship.py` preflight gates** — the script now mechanically
  refuses to build on: a dirty dev git tree, a red test suite, a missing
  CHANGELOG section for the target version, or overwriting a zip already
  committed to the ship repo. Previously it silently `unlink()`ed an
  existing zip, so re-running without bumping the version would replace
  a released artifact in place. `--skip-tests` exists for iterating on
  the bundle itself; the other three gates have no override.
- **`python/enrich/`** removed — empty directory, referenced by nothing
  (the real API clients live in `python/extract/*_client.py`). It only
  survived because `README.md` claimed it held the enrichment code.
  Note: git never tracked it (empty dirs aren't tracked), so this
  removal is not in version control. Recreate with `mkdir` if it was
  wanted for something.

### Contract tests added (60 -> 80)

The Phase-A claim that "every contract has a test" turned out to be
wrong on three counts. Each of these had zero behavioural coverage:

- **`tests/test_highlights_endpoints.py`** (8) — the v0.1.1 headline
  feature had only its ROUTE asserted, never its behaviour. Covers the
  full round-trip plus the note tri-state (key absent = never
  annotated, `""` = blank note, text = content). Collapsing those three
  states is the plausible "simplification" that would put an empty note
  card beside every highlight the user never touched.
- **`tests/test_bridge_contract.py`** (7) — `launcher.py`'s `_Bridge`
  vs the `window.pywebview.api.*` calls in `src/*.js`, asserted both
  directions. This boundary is uniquely dangerous because every JS call
  site swallows failures in `catch (_) {}`, so a renamed Python method
  kills Pop-out with no error, no toast, no log. `app.js` also sniffs
  one specific method to choose pywebview-vs-browser mode, so renaming
  it silently downgrades every user to the fallback path.
- **`tests/test_version_contract.py`** (4) — `_version.py` as the
  single source for `/api/version`, `build_ship.py`, and the bundle
  stamp. Also pins the file to a single assignment, because the build
  script and the PyInstaller spec both `exec()` its raw text without
  the package importable — any import added there breaks the build far
  from the cause.
- **`tests/test_server_boot.py`** strengthened — it checked only for
  MISSING routes, so `/api/version` and `/api/pick-corpus` sat unlisted
  for the whole v0.1 series. Now asserts both directions.

Mutation-tested: 12 planted bugs, 12 killed (5 against the original
suite, 7 against the new tests). Table in `TESTING.md`.

Tests: 80/80.

---

## v0.1.1 — PDF Note Mode + Pop-out (shipped 2026-08-19)

Reconstructed 2026-08-24 from `git log 14a42cf..c8e3e66`. The release
shipped without a changelog section; `build_ship.py` now gates on this
so it can't happen again.

### PDF Note Mode

Highlight-anchored notes in a right-side gutter next to the PDF. One
note per highlight, no length limit. Separate from the Notes tab.

- Toggle button lives in the PDF.js iframe toolbar (anchored to
  `#toolbarViewerRight` — the left section collided with the
  center-anchored zoom dropdown).
- Right-click a highlight → menu with Create/Focus note and a red
  "Remove highlight [+ note]" backed by a confirm dialog. Gated on
  `noteMode && !highlightMode`, so highlighting still works normally
  with Note Mode off.
- Left-click a highlight pings its gutter card (scroll into view +
  a two-pulse ring animation).
- Hit-testing works via `body.corpus-note-only`, which swaps
  `pointer-events` between the text layer and the highlight rects.
  The earlier approach broke because macOS auto-selects a word on
  right-click, making the `sel.isCollapsed` guard fail.
- Cards reflow on resize via `ResizeObserver` + a greedy collision
  push-down using real `offsetHeight`. Scrolling is synced both ways
  between the iframe and the gutter, guarded by a one-frame
  `_scrollSyncing` flag.
- Notes round-trip through the existing highlights endpoint —
  `papers_api.save_highlights` carries an optional `note` string per
  highlight.

### Pop-out

Open a paper's PDF in a separate native window.

- `launcher.py`'s `_Bridge` gained `open_detached` / `focus_detached` /
  `close_detached`, backed by a `slug → Window` map. Closing the
  detached window fires `corpus-detached-closed` into the main
  window's JS via `evaluate_js`.
- The detached window boots from a URL hash
  (`#detached=<slug>&noteMode=1`) and hides the topbar / tabs /
  sidebar.
- While a paper is popped out, the main window replaces that paper's
  subtabs with a placeholder offering "Bring to front" and "Close that
  window".
- Falls back to `window.open` when the pywebview bridge is absent
  (browser mode), detected via `_hasPywebviewBridge()`.

### Other

- **Papers sidebar sort** — dropdown (author / year / title / date
  added) plus a direction toggle. `added_at` added to `papers_api._paper_row()`.
- **Semantic Scholar throttle** — `_ss_rate_limit()` enforces a 1.1s
  minimum interval between keyless requests (thread-safe via a
  `threading.Lock`), to stop the 429s that unkeyed users were hitting.
- **`GET /api/version`** endpoint (added during the v0.1 ship work,
  first exercised here).

---

## 2026-08-19 — v0.1.1-dev: PDF Note Mode (step 1 — layout + toggle)

v0.1 shipped and worked in the wild. First 0.1.1 feature: the PDF Note
Mode Jack asked for (bug/feature report 20260819-134957). Full plan
lives in Corpus Dev Planning as `t-pdf-note-mode`.

Step 1 of 8: **layout + Note Mode toggle button, no iframe bridging yet.**

- `python/_version.py` bumped 0.1.0 → 0.1.1-dev.
- Paper-detail's PDF subpane now composes as `.pdf-toolbar` on top of
  `.pdf-frame-and-gutter` (a flex row containing the iframe + a
  right-side gutter aside).
- Note Mode toggle button in the toolbar. Clicking flips
  `state.noteMode` (user-preference-global) and adds/removes `.note-mode`
  on the outer `.pd-subpane-pdf`.
- CSS: with `.note-mode` off, the gutter has `width: 0` and the iframe
  fills the row. On, the gutter opens to ~25% of the pane with a soft
  ~180ms transition. Empty-state placeholder text lives there until
  step 2 wires actual note rendering.
- `.pd-subpane-pdf[hidden] { display: none !important }` — the
  hidden-beaten-by-display gotcha I keep re-learning. Added because
  the pane now uses `display: flex`.

What's NOT here yet (steps 2-8 of `t-pdf-note-mode`): forcing
highlights visible from inside the PDF.js iframe, right-click create-
note context menu, gutter note cards positioned to their highlights,
note editor, ping-on-click. Those are the harder iframe-bridge work.

Tests: 60/60.

---

## 2026-08-16 — Wave 3: frontmatter emitter refactor (prep for PDF scanner)

Jack has PDF-scanner work coming that will add 10-20 new frontmatter
fields (page count, extracted-text markers, per-page figures/tables,
alternative reference lists, funding-acknowledgment text, etc.).
`render_frontmatter` was 335 lines of interleaved if-blocks — each
new field would have required threading logic into the right position
among the existing branches. Refactored to make field-adds cheap.

### Approach — middle-ground helpers + orchestrator

Not a full schema table (which would have needed ~15 formatter
callables anyway, since the fancy shapes stay bespoke). Instead:

- Six generic emit-if-present helpers cover the ~40 conditional
  fields: `_emit_scalar_if`, `_emit_list_quoted_if`, `_emit_int_if`,
  `_emit_bool_flag`, `_emit_block_scalar_if`, `_emit_json_block_if`.
- Eight complex-shape emitters cover the fancy YAML: `_emit_authors_detailed`,
  `_emit_funder`, `_emit_license`, `_emit_update_to`, `_emit_ss_only_refs`,
  `_emit_s2_fields_of_study`, `_emit_ss_authors_raw`, `_emit_embedding`,
  `_emit_provenance`.
- `_yaml_flow_str_list` promoted to module scope (was a nested function).
- `render_frontmatter` becomes a linear orchestrator: each field is
  one line, sections marked by comments. 335 → 144 lines (-57%).

Adding a new frontmatter field is now:
- Scalar: `_emit_scalar_if(lines, "new_key", meta.get("new_key"))`
- List:   `_emit_list_quoted_if(lines, "new_list", meta.get("new_list"))`
- Nested: one new `_emit_new_shape(lines, entries)` + one call.
And `PROVENANCE_FIELDS` picks up new provenance rows automatically.

### Safety net — byte-for-byte golden-file test

`tests/test_render_frontmatter.py` locks the entire YAML output for
a rich fixture that exercises every emission kind. Fixture at
`tests/_render_fixture.py`. Golden at
`tests/fixtures/render_frontmatter_golden.md`.

If a future edit changes the output, this test fails with a
line-precise diff showing where. To regenerate the golden (for an
intentional change), see the header comment on the test file.

Tests: 59 → 60.

---

## 2026-08-16 — Notes: indent lists (fix first-item + Tab in plain text)

Two follow-up fixes to the indent feature from earlier today.

### Bug 1: Tab in plain text did nothing useful.

Previous handler only intercepted Tab inside a list; otherwise the
browser did default focus-nav, which is useless in an editor. Now:
Tab outside a list inserts 4 non-breaking spaces (regular spaces get
HTML-whitespace-collapsed; NBSPs render literally without needing
`white-space: pre-wrap` on the body).

### Bug 2: Indenting the first item of a list didn't change the marker.

`document.execCommand("indent")` on a first-item wraps the whole
list in a `<blockquote>` instead of creating a nested `<ul>`/`<ol>`
tree — so the CSS marker-cycling never triggered and the "list
indented, no marker change" visual Jack reported.

Replaced with custom `_indentListItem` / `_outdentListItem`
functions that always produce a proper nested list:
- Prior sibling exists → nest under it (standard case).
- No prior sibling (first-item case) → wrap in
  `<li class="li-phantom"><ul><li>…</li></ul></li>`. The phantom
  parent exists because `<ul>` can only contain `<li>` per HTML
  spec; CSS `.note-body li.li-phantom { list-style: none; }` hides
  its otherwise-orphaned bullet.

Outdent inverts: moves the item out of the sub-list into the
grandparent, cleans up empty sub-lists, and removes phantom
parents that become empty.

Toolbar → and ← buttons dispatch to the same helpers so they
behave identically to Tab / Shift-Tab.

Sanitiser gains `class` on `<li>` restricted to the single value
`li-phantom` — matches the existing `class="note-table"` restriction
pattern. Any other class value is stripped.

Two new sanitiser tests:
- `test_keeps_li_phantom_class` — the allowed class survives.
- `test_strips_other_li_classes` — everything else gets stripped.

CODE_MAP's user-action table updated with the three tab-related
behaviors (in-list, plain-text, toolbar buttons).

Tests: 57 → 59.

---

## 2026-08-16 — Notes: indent lists + nested markers

Two things, one paired feature:

1. **Indent / outdent**. New `→` and `←` buttons in the notes-editor
   toolbar dispatch `document.execCommand("indent" | "outdent")`.
   Tab / Shift-Tab do the same thing when the caret is inside a
   `<li>` — outside a list Tab still does default focus-nav. Both
   paths checkpoint history + trigger autosave.

2. **Nested markers**. Unordered lists cycle `disc → circle → square`
   by depth. Ordered lists cycle `1 → a → i`. CSS-only. Same
   convention as Word / Google Docs. Depth 4+ restarts the cycle.

Sanitiser was already permissive enough (`ul`, `ol`, `li` all on the
allow-list); nesting is a structural property the parser preserves
automatically. Added `test_keeps_nested_lists` to lock the invariant
so a future sanitiser tightening can't silently flatten indents.

CODE_MAP's user-action table gains two rows:
- Tab / Shift-Tab in a list item
- click the `→` / `←` toolbar button

Both are client-only (no server round-trip until the next autosave,
which already logs `note_updated`).

Tests: 56 → 57.

---

## 2026-08-16 — Wave 3: blueprint split finish (server.py → 5 blueprints)

Closes the first Wave-3 audit item. `server.py` was 1257 lines and
owned every non-notes / non-extract endpoint. Split into three new
blueprints and shrunk to a composition root.

### New files

- **`python/config_api.py`** (215 lines) — `config_bp`.
  * Owns: `/api/config` GET+POST, `/api/tooltips` GET, `/api/pick-corpus` POST.
  * Owns: config store (`CONFIG_PATH`, `_load_json_config`,
    `_save_json_config`), secret store (Keychain via `keyring` with
    JSON fallback), `_apply_env` (called by `/api/config` POST and
    `init_app`).
  * Owns: `_bridge` state + `set_bridge()` for the launcher's
    native folder-picker.
  * Reads `IS_DEV` from `current_app.config["CORPUS_IS_DEV"]` so
    no circular import to server.

- **`python/entities_api.py`** (660 lines) — `entities_bp`.
  * Six endpoints: `/api/authors`, `/api/author/<key>`,
    `/api/institutions`, `/api/institution/<key>`,
    `/api/journals`, `/api/journal/<key>`.
  * Three key helpers (`_author_key`, `_institution_key`,
    `_journal_key`) — source of truth for every key JS EntityKeys
    mirrors.
  * Three aggregators (`_aggregate_authors`, `_aggregate_institutions`,
    `_aggregate_journals`) + `_merge_authors_by_display` dedup pass.
  * `_enrichable_detail` — shared body of the three near-identical
    detail endpoints.

- **`python/papers_api.py`** (240 lines) — `papers_bp`.
  * Endpoints: `/api/papers`, `/api/paper/<slug>`, `/pdf/<slug>`,
    `/api/paper/<slug>/highlights` GET+POST,
    `/api/paper/<slug>/reveal[/kind]` POST.
  * `_paper_row` (sidebar list shape), `_paper_link_keys` (canonical
    keys attached to every paper-detail response).
  * Imports `_author_key` / `_institution_key` / `_journal_key`
    from `entities_api` so link_keys stay consistent.

- **`python/_api_common.py`** grew from 21 → 85 lines to hold
  cross-blueprint helpers:
  * `require_corpus_or_abort` (pre-existing).
  * `_fm_dict` — parse a summary MD, return {} on failure.
  * `_walk_summaries` — yields (slug, fm) for every parseable
    summary. Used by every aggregator.
  * `_strip_quotes` — YAML quote-stripper.
  * `_parse_json_block` — YAML block scalar → list.

### Server.py after (~225 lines)

Only:
- Flask app creation
- IS_DEV detection + `app.config["CORPUS_IS_DEV"]` for blueprints
- Access-log hooks (dev-only)
- Blueprint registrations (config, papers, entities, notes, extract)
- Dev-only surfaces wiring (bug reporter, planning, tooltips)
- SPA index route
- `set_bridge = config_api.set_bridge` alias for launcher back-compat
- `_configure_logging` + `init_app`
- `__main__` block

Was: 1257 lines. Now: ~225. Ratio: 82% smaller. Composition root
now literally IS a composition root — nothing but wiring.

### Test updates

Two test files import moved symbols directly (not via HTTP):
- `test_aggregators.py`: `server._aggregate_*` → `entities_api._aggregate_*`.
- `test_metadata.py`: `from server import _author_key, …` →
  `from entities_api import …`.

All other tests use HTTP clients and don't care where routes live.
`test_server_boot`'s route-registry check verifies every expected
URL is still reachable after the split.

### Verification

- pyflakes clean (only the intentional noqa re-export remains).
- pytest: 56/56 pass.
- test_server_boot's assertion `expected - rules == set()` proves
  every documented route survived the blueprint move.

### What Wave 3 still has open

- Frontmatter emitter table (`render_frontmatter` 335 lines → schema table).
- Vanilla-JS `Corpus.*` namespace.
- Resolver ladder + `Source` contract (only when adding a 4th data source).

---

## 2026-08-16 — Wave 2: renderEntityDetail dedup + refresh-handler unification

Closes the last open Wave-2 audit item. Author / institution /
journal detail panes shared ~90% of their skeleton after the earlier
provenance/coverage extraction; extracting the remaining common
shape makes "add a new detail entity" a small change.

### `src/entity-detail.js` — new shared skeleton

```js
EntityDetail.render({
  h1, subtitle,
  metaRows,       // [[key, htmlValue], ...]
  refresh,        // {entity, key, fetchedAt} | null
  sideBlocks,     // [htmlString, ...] — empties filtered
  coverage,       // rows for Coverage.renderTable
})
```

Wraps the standard `<div class="pd-header">` + `<dl class="pd-meta">`
+ optional `<div class="pd-refresh">` + side-block list + coverage
table. Callers compute the entity-specific parts and pass them in.

### Detail modules become descriptors

Author-detail, institution-detail, journal-detail each end with:
```js
pane.innerHTML = EntityDetail.render({
  h1: <name>,
  subtitle: <...>,
  metaRows: <entity-specific rows>,
  refresh: <entity-specific spec or null>,
  sideBlocks: [<entity-specific blocks in order>],
  coverage: <entity-specific rows>,
});
```

Line counts:
- `src/author-detail.js`:      232 → 218 (-14)
- `src/institution-detail.js`: 169 → 151 (-18)
- `src/journal-detail.js`:     162 → 147 (-15)
- New `src/entity-detail.js`:  64 lines
- Net: +17 lines, but the shape now lives in ONE place. Adding a
  new detail entity (Publishers, Funders, …) = writing a descriptor,
  not building the skeleton from scratch.

### Refresh-button unification

Old: three separate attribute names + three separate click-handler
branches in app.js (`data-refresh-inst`, `data-refresh-journal`,
`data-refresh-author`).

New: one attribute pattern emitted by `EntityDetail.render`'s
refresh bar — `data-refresh-entity="<entity>" data-refresh-key="<key>"`.
One click handler in app.js dispatches through a small `_REFRESH_TARGETS`
lookup. Adding a fourth refreshable entity = one row.

Behavior unchanged. Same endpoint (`/api/<entity>/<key>?refresh=1`),
same state key, same render call, same toast.

### Test harness fix

`tests/src/harness.js` had a real bug: `window` was a separate
property on the sandbox, so `window.Foo = {…}` in a loaded script
set `sandbox.window.Foo` but NOT `sandbox.Foo`. Bare `Foo`
references in later scripts failed with ReferenceError. Made
`sandbox.window === sandbox` (real browser semantics — `window` IS
the global). Existing tests that did `const {window} = loadInVM(...)`
still work because `window === sandbox` and property access is
transparent.

### New tests

- `tests/src/entity-detail.test.js` — 8 tests: header, subtitle
  omission, meta-row rendering, refresh bar present/absent/no-cache
  states, side-block order + empty-filter, coverage always rendered.
- `tests/test_script_load_order.py` — one new test:
  `test_entity_detail_loads_before_author_institution_journal`.

Tests: 55 → 56 (frontend suite grew by 8 JS assertions internally,
counts as 1 pytest test).

---

## 2026-08-16 — Logging is dev-only

Jack's ask: shipped builds must not track user actions. Logging
should exist for developer diagnostics but be fully absent from
shipped Corpus.

Implementation — the `corpus.*` logger tree is gated on `IS_DEV`
(which is already the source of truth for every other dev-only
surface — bug reporter, planning modal, tooltip editor):

- `_configure_logging()` now checks `IS_DEV` before doing anything.
  When False: sets `logger.disabled = True` on the `corpus` root
  logger and returns without adding any handler. No log file
  created. No stderr output. Every `logger.info(...)` /
  `logger.warning(...)` call short-circuits at
  `Logger.isEnabledFor()` — before any formatting, exc_info
  capture, or handler lookup.
- The `_access_log_start` / `_access_log_finish` Flask hooks are
  only registered when `IS_DEV` is True. Ship builds don't have
  them attached at all — no per-request `before_request` runs, no
  `time.monotonic()` overhead, nothing.
- `IS_DEV` computation moved up in `server.py` (right after Flask
  app creation) so the logging + hook wiring can reference it. The
  older definition further down is dropped; the dev-only-blueprints
  block reuses the earlier value.

Behavior invariants (from `CONTRIBUTING.md` — updated to codify):
- Dev build: `~/.corpus/logs/server.log` gets every access line +
  every event line. Same as before this commit.
- Ship build: zero log output. No file. No lines. Users can't be
  tracked via logs, period.
- Feature code stays unchanged — every `logger.info(...)` written
  under the contract still works in dev, no-ops in ship.

Three new tests in `test_logging_dev_only.py`:
- `test_configure_logging_disables_tree_when_not_dev` — asserts
  `disabled=True`, zero handlers, `isEnabledFor(WARNING)` False.
- `test_configure_logging_enables_tree_in_dev` — asserts handlers
  attach + INFO enabled.
- `test_access_hooks_not_registered_when_not_dev` — asserts the
  Flask `after_request_funcs` list does/doesn't contain
  `_access_log_finish` depending on `IS_DEV`.

Docs updated:
- `CODE_MAP.md` "User action → log signature" section gains a
  dev-only preamble.
- `CONTRIBUTING.md` gets a dedicated "Logging is dev-only"
  section — includes "if you need visibility in a shipped build,
  use a UI mechanism, not the logger."
- Memory (`feedback-corpus-doc-log-contract`) updated to reflect
  the dev-only invariant.

Tests: 52 → 55.

---

## 2026-08-16 — CLI removal + full logging + doc/log contract

Jack's ask (paraphrasing): remove CLI stuff from Corpus (it's a
desktop app; features go through buttons); finish logging so
every documented flow leaves evidence in `~/.corpus/logs/server.log`;
add a doc contract so future changes maintain the "click → doc
predicts → log confirms" invariant.

### CLI removal

- Deleted `python/extract/rename_pdfs.py` (~570 lines) — standalone
  script, only test was the DOI-regex-alias guard which went with
  it.
- Deleted `python/extract/backfill_dois.py` (~275 lines) — standalone
  script, zero imports.
- Deleted `python/extract/check_schemas.py` (~135 lines) — standalone
  script, zero imports.
- Stripped `if __name__ == "__main__":` blocks + `main()` +
  `argparse` from `extract_metadata.py`, `prefill_summary.py`,
  `extract_references.py`. They remain as library modules (used by
  `extract_api.py` via imports) but no longer act as CLI entry points.
- Dropped unused `argparse` / `json` / `sys` imports the strip left
  behind.
- Removed stale "Run: python3 …" docstring for `extract_references.py`.

### Full logging

- **Flask access log** — new `_access_log_start` / `_access_log_finish`
  hooks in `server.py`. Every `/api/*`, `/pdf/*`, `/dev/*` request
  logs `api_request method=<M> path=<P> status=<code> dur_ms=<n>`.
  Static SPA assets skipped so the log isn't drowned.
- **Notes CRUD** — new `corpus.notes_api` logger. `note_created`,
  `note_updated`, `note_deleted` events per endpoint.
- **Bug reports** — new `corpus.bug_reports` logger. `bug_report_saved`
  event on submit; `bug_report_screenshot_decode_failed` on bad b64.
- **Config save** — `_save_json_config` now emits `config_saved` on
  success + `config_save_failed` (with `exc_info=True`) on write
  failure. Previously a disk-write exception would raise uncaught.
- **Highlights** — `highlights_saved slug=<s> count=<n>` on POST.

Every state-changing endpoint now produces at least one specific
event log in addition to the baseline access log.

### Doc / log contract

- New `CONTRIBUTING.md` — the "doc + log contract" as a checklist
  every code change must run through.
- New section in `CODE_MAP.md`: "User action → log signature." Table
  maps every user-facing action to the endpoint(s) hit and the exact
  event log line(s) that fire. Also includes aggregator side-effects
  and API-fetch side-effects sections, plus grep recipes.
- Memory saved (`feedback-corpus-doc-log-contract`) — HARD RULE for
  future Corpus work.

### Tests

53 → 52 (lost the `rename_pdfs._DOI_RE` alias test with its file;
everything else unchanged). Pyflakes clean.

---

## 2026-08-16 — Add PDFs + Scan both flow through `inbox/`

Prior behavior:
- Add PDFs button: saved upload straight into `papers/`.
- Scan button: only walked `papers/`, ignored `inbox/`.
- Result: dragging a PDF into `inbox/` from Finder and clicking
  Scan did nothing. `inbox/` was a folder in the tree with no
  server-side path to reach it.

New behavior:
- Add PDFs button: saves upload into `<corpus>/inbox/` first, then
  runs the same extract → canonicalize → move to `papers/<slug>.pdf`
  → render summary pipeline. Same visible result as before, but the
  intermediate step is now a real drop zone.
- Scan button: two-pass sweep. Pass 1 processes every PDF in
  `inbox/` (same pipeline). Pass 2 backfills any `papers/` PDF
  without a summary (legacy path for pre-inbox files or
  hand-drops into papers/).
- Response shape adds `inbox_processed: [{filename, status, slug, …}]`
  alongside the existing `extracted: [slug]` and `skipped: int`.
- Frontend toast updated: "extracted N new paper(s) (M from inbox,
  K backfilled)" when both fire.
- Logging added at every choke point: `inbox_processed`,
  `inbox_process_failed`, `inbox_collision`, `scan_prefill_failed`.
  Closes the audit-flagged "documented flow, zero logging" gaps
  for the inbox path.

Extracted `_process_inbox_pdf(source_pdf, original_name)` helper
that both endpoints call — one path, one bug surface. Old inlined
copy in /api/extract is gone.

Two new tests in `test_scan_endpoint.py`: empty-corpus shape, and
the skip-when-summary-exists case. Actual extract pipeline needs
a real PDF + network so it's covered by manual click-through, not
automation.

Tests: 51 → 53.

---

## 2026-08-16 — Wave-1 finish: rename_pdfs + backfill_dois dedup

Last two open Wave-1 items closed.

- `rename_pdfs.py`: `crossref_lookup` used subprocess+`curl` with a
  stale rationale ("macOS Python has no CA cert bundle").
  `_api_http.ssl_contexts()` handles that via urllib now. Delegates
  to `crossref_client.crossref_lookup` under the hood; shape
  transformation stays local. Signature unchanged.
- `backfill_dois.py`: dropped local `_user_agent`, `_ssl_contexts`,
  `_norm`, `title_similarity`, `USER_AGENT` — all identical
  duplicates of `_api_http`. Rewrote the three search functions
  (`crossref_search`, `_semantic_scholar_search`, `_openalex_search`)
  to use `api_get_json`. Half the boilerplate; retries/SSL handled
  by the shared helper.
- Deferred: promoting `_prefix_ok` + multi-source logic into
  `crossref_client.search_by_title_multi()`. Would change the
  extract-pipeline accept rules (currently strict-similarity only) —
  a real feature change, not Wave-1 cleanup.
- Also cleaned pyflakes noise on files I touched recently: dropped
  `orcid_src` unused local in `server.py`, dropped `_papers_dir`
  unused import in `check_schemas.py`.

Tests: 49 unchanged.

**Wave 1 is now fully closed.** Remaining refactor work: Wave 2
(`renderXDetail` triple dedup) + Wave 3 (resolver ladder, source
contract, blueprint split finish, frontmatter emitter, `Corpus.*`
namespace).

---

## 2026-08-16 — Wave-1 cleanup burst

Four small pre-existing audit items closed out. All low-risk, no
unlocks — just tightening rough edges.

### 1. `_noteHistory` leak (src/notes.js)

`deleteNote` never removed its entry from the per-note undo/redo
map. Session-scoped, but a long session that edits many notes
could grow memory. One-line fix: `_noteHistory.delete(id)` inside
the delete flow.

### 2. `.pdf-viewer` magic 210px (src/styles.css)

Old CSS: `height: calc(100vh - var(--topbar-h) - 210px)`. The 210
was a guessed measurement of surrounding chrome (header + subtabs +
padding). Retraction and extraction-failure banners in paper-detail
push the header taller — the guess breaks. Replaced with a proper
flex column layout on `.paper-detail`: subpane gets `flex: 1 1 auto`
and scrolls internally; iframe fills whatever height it received.
No pixel math. Author/institution/journal detail panes are
unaffected (their CSS blocks are separate).

### 3. `_apply_env()` at import time → explicit `init_app()`

Was: `_apply_env()` invoked at module scope in server.py, so any
test that imported `server` touched the real user's Keychain +
config.json unless `CORPUS_CONFIG_PATH` was set first. Fix:

- Extracted a public `init_app()` that calls `_configure_logging()`
  + `_apply_env()`.
- Removed the module-scope call. Import is now pure.
- `launcher.py` calls `srv.init_app()` before serving.
- `python/server.py`'s `__main__` branch calls it too.
- `tests/conftest.py` — updated the docstring; tests never call
  `init_app` so they don't inherit the user's config. Test
  isolation improves as a side effect.

### 4. Logging config + hot-site logging

Zero logging existed anywhere. 37 silent `except Exception: pass`
sites — a failure vanished with no trace. Full coverage isn't
worth the noise (many are intentional silent fallbacks), so:

- New `_configure_logging()` in server.py's `init_app()`.
    * Namespaced logger tree at `corpus.*` (so `logging.getLogger(
      "corpus.server")`, `corpus.api_http`, `corpus.extract_api`).
    * Rotating file handler: `~/.corpus/logs/server.log`, 5MB /
      3 backups, INFO level.
    * Console handler: WARNING and up (dev-visible, quiet-by-default).
    * Idempotent; safe to call again.
- Added `logger.warning(...exc_info=True)` at 4 highest-value
  swallow sites:
    * `server._load_json_config` — malformed config.json is worth
      knowing about.
    * `server._fm_dict` — a summary MD failing to parse.
    * `_api_http.api_get_json` — every Crossref/OA/SS call that
      dies silently (WARNING for unexpected, INFO for expected
      URL errors like DNS/timeout).
    * `extract_api._prefetch_enrichment_for_slug` — daemon-thread
      failures were the WORST kind of invisible.
- 33 other swallow sites unchanged (intentional silent fallbacks;
  logging them would be noise). Any future one worth logging just
  needs `logger.warning(..., exc_info=True)` — no ceremony.

Tests: 49 unchanged. All four items are behavior-preserving except
where behavior was BROKEN (banner-pushed iframe, memory leak on
deleted notes, tests silently inheriting user config).

---

## 2026-08-16 — Aggregator dedup, honest scope (audit A1 + A2)

Landed the wins from audit A1 / A2 that are actually clean. Honest
note upfront: the audit oversold the aggregator-guts overlap. The
three aggregators superficially resemble each other but do wildly
different accumulation. What IS genuinely shared — the file-walk
skeleton, two copy-pasted primitives, and the three near-clone
detail endpoints — got dedup'd. The per-summary accumulation logic
inside each aggregator stayed put.

### Four new module-scope helpers in `python/server.py`

- `_walk_summaries()` — generator yielding `(slug, fm)` for every
  parseable summary MD. Replaces the copy-pasted
  `for md in sorted(summaries_dir().glob("*.md")): try parse …
  except continue: slug = md.stem` skeleton in `_aggregate_journals`
  and `_aggregate_authors`.
- `_strip_quotes(s)` — YAML quote-stripper. Was defined once inside
  `_aggregate_journals` and re-inlined during the recent
  `_paper_link_keys` work; now shared.
- `_parse_json_block(v)` — YAML block scalar → list. Was defined
  twice (in `_aggregate_journals` and `_aggregate_authors`) plus
  once more inline in `_paper_link_keys`. Now one.
- `_enrichable_detail(aggregate_fn, key, id_getter, enricher)` —
  the shared body of the three entity detail endpoints. Each was
  ~15 lines of the same "require corpus → aggregate → find by key →
  404 or extract id → enrich if id → return" pattern. Now each
  endpoint is 4-6 lines.

### Callers updated

- `_paper_link_keys` — drops its two locally-defined helpers, uses
  the module-scope ones.
- `_aggregate_journals` + `_aggregate_authors` — switched to
  `_walk_summaries()` iteration; dropped their local
  `_parse_json_block` / `_strip_quotes` / `parse_frontmatter`
  re-imports.
- `_aggregate_institutions` — its "batch-load titles/years for
  referenced papers" loop was doing what `_fm_dict` already does;
  swapped to `_fm_dict` and dropped the local `parse_frontmatter`
  re-import.
- `author_detail`, `institution_detail`, `journal_detail` — each
  collapsed from ~15 lines to a 4-line call into `_enrichable_detail`
  with the entity-specific id-getter + enricher passed as lambdas.

### Safety net

`tests/test_aggregators.py` — new (6 tests). Fixture-based structural
snapshot of all three aggregators + a round-trip test hitting each
detail endpoint. Snapshots record count, key format, per-record
shape (papers-per-author, authors-per-institution, etc.), and 404
behavior on unknown keys. Written BEFORE the refactor so any silent
drift = red test.

### What stayed put

Per-summary accumulation logic inside each aggregator. The three do
different things and the audit's "~70% shared" claim doesn't survive
a close read — the actual shared piece was the file-walk skeleton
(~7 lines), which is now shared. Further dedup would require forcing
a shape on inherently different accumulations. Not worth the
regression risk.

`server.py`: 973 → 953 lines (-20). Tests: 43 → 49.

---

## 2026-08-16 — Fix: paper-detail publisher link 404s (backend-computed keys)

Jack reported clicking the publisher name on a paper detail pane
landed on "failed to load: HTTP 404" in the Journals tab. Root cause:
the frontend was *computing* deep-link keys via `EntityKeys.*`, which
tries to mirror the backend key helpers but had subtle drift for
some real-world publisher name shapes (bare-string ISSN in YAML,
quoted list items, etc.). Any mismatch = 404 on click.

Fix: have the **backend** attach canonical keys to the paper-detail
response, using the exact same `_journal_key` / `_author_key` /
`_institution_key` helpers the aggregators use. Frontend now reads
those keys directly instead of guessing.

- `python/server.py` — `paper_detail` returns a new `link_keys` block:
    ```
    {
      "journal":                str,           # "" if publisher unknown
      "authors_detailed":       [str, ...],    # parallel to fm.authors_detailed
      "authors_detailed_insts": [[str, ...], ...],
      "oa_authors":             [str, ...],    # parallel to fm.oa_authors
      "oa_authors_insts":       [[str, ...], ...],
    }
    ```
- `src/paper-detail.js` — the publisher row, per-author name, and
  per-institution bullets all consume `d.link_keys.*` when present,
  falling back to `EntityKeys.*` for defense.
- `src/entity-keys.js` — while diagnosing, hardened
  `EntityKeys.journal` to accept bare-string ISSN and strip stray
  quotes (matches the backend's aggregator-side normalization). The
  frontend module is still in use as a fallback + reference; the
  parity tests remain valuable.
- `tests/test_link_keys.py` — new end-to-end regression test. Writes
  a fixture summary with a real publisher + two authors +
  institutions, hits `/api/paper/<slug>`, then uses every returned
  `link_keys` value to hit the matching entity endpoint. If any key
  is rejected (drift between paper-detail and any aggregator), the
  test fails immediately.
- `tests/src/entity-keys.test.js` — 3 new tests covering bare-string
  and quoted-string ISSN handling.

Tests: 41 → 43 (added `test_paper_link_keys_round_trip` +
`test_paper_link_keys_absent_publisher_yields_empty_key`).

---

## 2026-08-16 — Deep-links across every entity-cross-reference

Extended the previous deep-link pass to also cover institutions.
Every place one entity references another — authors listed inside
a paper, institutions listed inside an author, publishers listed
inside a paper — is now a clickable jump to that entity's page.
Full linkage map:

| From              | Refs to    | Anchor emitted at         |
|-------------------|------------|---------------------------|
| paper-detail      | authors    | "Authors + affiliations" block |
| paper-detail      | institutions | per-author affiliation bullets (OA + Crossref/SS paths) |
| paper-detail      | journal    | "Publisher" row |
| author-detail     | papers     | "Papers in corpus" (pre-existing) |
| author-detail     | institutions | "Institutions" block (new) |
| institution-detail| authors    | "Authors" block (pre-existing) |
| institution-detail| papers     | "Papers in corpus" (pre-existing) |
| journal-detail    | papers     | "Papers in corpus" (pre-existing) |

### What changed

- `src/entity-keys.js` — new `EntityKeys.institution(name, ror)`
  helper mirroring `_institution_key` (ROR wins; falls back to
  name slug; empty → "unknown").
- `src/paper-detail.js` — institution names in per-author
  affiliations wrap in `<a data-open-institution="…">` (both the
  OA-structured path and the Crossref/SS name-only path).
- `src/author-detail.js` — institution names in the Institutions
  block wrap in `<a data-open-institution="…">`. External "ROR ↗"
  link next to it stays external.
- `src/app.js` — deep-link handler gains a `data-open-institution`
  branch, routing to `switchMode("institutions")` + `selectInstitution`.
- `tests/src/entity-keys.test.js` — 5 new tests for institution
  key: ROR URL / bare ROR / name-slug / accents / empty→"unknown".
- `tests/test_metadata.py` — same 6 institution fixtures against
  the Python `_institution_key` for cross-language parity.

### Behavior guardrails

- Institution links only appear when a name is present; nothing
  to click on missing data.
- Existing external "ROR ↗" links coexist with the new internal
  deep-link — same pattern as ORCID coexisting with the author
  name in the author block.
- The Crossref/SS non-OA fallback path in paper-detail's
  affiliations uses a name-slug key that matches what the author
  aggregator computes for those same name strings, so the link
  resolves.

Python tests unchanged (41); JS test count grew 25 → 30 (5 new
institution-key assertions).

---

## 2026-08-16 — Paper-detail deep-links: click authors + publisher

Wired up the "click an author name in the paper detail pane → jump
to that author's tab" flow, plus the same for the publisher name →
Journals tab. The deep-link click handler in `app.js` has always
supported `a[data-open-author]` links; paper-detail just never
emitted them. This closes the loop.

- New `src/entity-keys.js` — JS mirrors of `_author_key` and
  `_journal_key` from `python/server.py`. Used at render time to
  build anchor `data-open-*` values that match what the backend
  aggregators produce.
- `src/paper-detail.js` — wraps every author-name in
  `<a href="#" data-open-author="…">` (only when we have a family
  name); wraps the "Publisher" field value in
  `<a href="#" data-open-journal="…">` (only when publisher is
  real, not "unknown").
- `src/app.js` — deep-link handler gains a `data-open-journal`
  branch that mirrors the paper / author branches.
- `tests/src/entity-keys.test.js` — 12 tests locking every key
  case: plain names, initials, no-given fallback, first-token
  behavior, NFKD accent-stripping, apostrophes / spaces / hyphens
  collapsing to single hyphens, ISSN preference over name, ISSN
  normalization, name-slug fallback, empty → "unknown".
- `tests/test_metadata.py` — new `test_entity_key_python_parity`
  asserts the same fixtures against the Python side. If either
  language drifts, exactly one suite fails, surfacing the mismatch.

Tests: 39 → 41.

---

## 2026-08-16 — Mode registry + modals registry (audit A6 + C-modals)

The single biggest adaptability tax the audit flagged: adding a new
sidebar tab (Publishers, Funders, Datasets…) used to require editing
nine coordinated spots — state object, `switchMode` show/hide dance,
filter input listener, list click delegator, arrow-key `modes` map,
arrow-key `listId` map, arrow-key `attr` ternary, index.html markup,
and CSS. Now it's one array entry.

### `src/app.js` — MODES table

A single `MODES = [...]` array near the top declares each tab as a
complete recipe: `{ id, stateKey, filterKey, selectedKey, listId,
filterId, detailId, dataAttr, load, render, select, renderDetail,
loadPolicy, emptyStateHtml? }`. Five sites now iterate it instead of
per-tab hardcoding:

- **`switchMode`** — one loop toggles hidden on filter/list/detail
  elements. Load-vs-render decision uses `loadPolicy` (`"eager"` for
  Papers, `"lazy"` for Authors/Institutions/Journals, `"always"`
  for Notes). The Notes-empty-state innerHTML is now expressed as
  an optional `emptyStateHtml: () => _noteEmptyStateHtml()` on the
  Notes entry, so switchMode carries zero tab-specific `if` blocks.
- **Filter input listeners** — five near-identical `addEventListener`
  blocks collapsed into one loop reading `filterKey` / `render` off
  each mode.
- **List click delegators** — five `closest("li[data-…]")` blocks
  collapsed into one loop reading `dataAttr` / `select` off each
  mode. Notes' `data-note-id` special case is a single field value
  now, not a branch.
- **Arrow-key handler** — the `modes` lookup dict, `listId` lookup
  dict, and `attr` ternary all disappear. Handler now grabs the
  right MODE by `state.mode`, queries its `listId` for `data-*`
  rows, and consults the pure `Nav.nextIndex()` helper for the
  arithmetic.

Behavior-preserving except for one tiny nit: when the list is
non-empty in state but the filter renders 0 rows, arrow keys no
longer call `preventDefault()` — since there's nothing to select,
default keyboard behavior (usually a no-op) can run.

### `src/nav.js` — pure arrow-key arithmetic

Extracted the "given itemCount + currentIndex + direction, what's
next?" math from the arrow-key handler into a standalone module so
it can be unit-tested without a DOM. Handles the "no selection →
seed off the end" and "at boundary → clamp, don't wrap" cases.
11 tests in `tests/src/nav.test.js`.

### `src/modals.js` — modal registry (audit "kill dev-only class-name coupling")

The arrow-key handler used to hardcode dev-only class names
(`.dev-plan-modal-overlay`, `.dev-tt-modal-overlay`,
`.dev-bug-modal-overlay`) inside shipped app.js — a violation of
the dev/prod boundary Jack cares about. New `Modals` registry:

- `Modals.watchSelector(sel)` — a module opts in by naming a
  selector to watch. `.modal-overlay:not([hidden])` is registered
  by default so shipped modals (Settings) still block arrow-nav.
- `Modals.register(el)` / `Modals.unregister(el)` — explicit
  element-based registration for modals without a shared class.
- `Modals.anyOpen()` — the arrow-key handler asks this.

Each dev-only file (`planning.js`, `tooltip-editor.js`,
`bug-reporter.js`) now calls `Modals.watchSelector(".dev-*-modal-overlay")`
at load-time. In shipped builds, those files aren't loaded, so
their class names are never registered and app.js has no
knowledge of them.

### `src/index.html`

Script order: `tooltips.default.js` → `provenance.js` → `modals.js`
→ `nav.js` → detail modules → `notes.js` → `app.js`. Two new
`test_script_load_order` tests guard the ordering.

### Tests

- `tests/src/nav.test.js` — 11 tests for `Nav.nextIndex`: empty list,
  no selection, out-of-range, middle-of-list, boundaries, single-item.
- `tests/test_script_load_order.py` — 2 new tests for nav.js + modals.js
  ordering vs app.js.

Line counts: `src/app.js` 816 → 829 (MODES definition + docs). The
gain isn't line count; it's edit surface for the next tab.

Tests: 37 → 39.

---

## 2026-08-16 — Wave-1 backend dedup + frontend test harness

Two Wave-1 items from the audit landed together (both prerequisites
for the mode-registry refactor coming next).

### Frontend test harness (Wave-1 E1)

There were zero JS tests. Any refactor that touched `src/` was
blind — the `test_script_load_order.py` regex sniffer was the only
guardrail. Now:

- `tests/src/harness.js` — Node `vm`-based loader. Reads a browser JS
  file, evals it in a sandboxed context with fakes for `window`,
  `document`, `SRC_ABBR`, `escHtml`, `escAttr`, `tt`. Returns the
  sandbox so tests can pull `window.Provenance` etc. Zero deps
  beyond `node:test` + `node:assert` + `node:vm`.
- `tests/src/provenance.test.js` — real assertions for the module
  I extracted in the prior commit. 13 tests covering
  `Provenance.badgeFromArr` / `badgeFromField` (dedupe, winner vs
  verifier ordering, unknown source fallback, null-safety),
  `Coverage.inSource` (crossref-search-counts-as-C invariant),
  `Coverage.cell` (4-state matrix), `Coverage.renderTable`
  (rendered rows + legend).
- `tests/test_frontend.py` — Python glue that shells to
  `node --test tests/src/`. Skips (does NOT fail) when node is
  absent so the Python suite always runs. Install with
  `brew install node` to activate the JS side.
- `TESTING.md` — documents both suites, when to run each, and the
  node install prerequisite.

Verified locally with `.venv/bin/python -m pytest tests/ -q`:
36 pass, 1 skip (the frontend runner, awaiting node install).

### Backend dedup (Wave-1 B4 + B6)

Four sets of duplicate primitives collapsed into `_api_http.py`:

- **DOI regex** — was defined three times: `extract_metadata._DOI_RE`
  (wide negated char class), `rename_pdfs._DOI_RE` (narrower positive
  class), `extract_references._DOI_URL_OR_BARE` (URL-or-bare, distinct
  purpose). New `_api_http.DOI_RE` + `DOI_TRAIL_RE` unify the first
  two; `extract_metadata` and `rename_pdfs` both alias them at module
  scope so callers stay one-line. `extract_references` intentionally
  keeps its own regex (URL-or-bare context, different suffix rules).
  Small behavior improvement for `rename_pdfs`: the shared regex is
  a strict superset — catches at least as many DOIs as before, never
  fewer, at the same natural boundaries (`\s"'<>(){}\[\];,`).
- **Author-name splitter** — the "split `Given [Middle...] Family`
  vs `Family J.` shapes" logic lived inline in
  `_from_pdf_metadata` (18 lines) and `_from_openalex` (10 lines,
  slightly less capable — dropped trailing initials rather than
  keeping them). New `_api_http.split_display_name(name)` handles
  both shapes uniformly; both call sites now delegate. Semantic
  effect: OpenAlex mappings for the (rare) `"Smith J."`-shaped
  `display_name` will now retain the initial in `given` instead of
  dropping it, matching what the PDF path already did.
- **`kind` mapping** — Crossref and OpenAlex clients each defined
  the same Crossref-type-to-kind dict (10 entries, differing only in
  OA's extra `"article": "article"` alias). New
  `_api_http.crossref_type_to_kind(t)` returns the mapped kind or
  `None` for unknown types; each caller keeps its own default
  (Crossref = "article", OpenAlex = leave unset). Semantic Scholar
  keeps its distinct tag-set derivation — different upstream shape.
- **Dead import** — dropped now-unused `re` from `openalex_client.py`
  (its only use was the inline name-split logic).

Added 4 tests to `tests/test_metadata.py` for the new helpers,
including a `rename_pdfs._DOI_RE is _api_http.DOI_RE` identity check
so a future well-meaning re-inline can't drift the two apart.

Not touched (called out in audit but bigger scope): `backfill_dois.py`
still deliberately duplicates title-search logic; `rename_pdfs.py`
still shells out to `curl`. Both deferred to a Wave-3 pass since
each has its own broader story (backfill's `_prefix_ok` should be
promoted into the extract pipeline; curl's rationale can be deleted
now that `ssl_contexts()` exists).

---

## 2026-08-16 — Shared provenance / coverage module

First step of the Wave-1 dedup pass called out in the 2026-08-16 audit.
Four detail modules (`paper-detail`, `author-detail`, `institution-detail`,
`journal-detail`) each defined their own `provFromArr` / `covCell` /
`inSrc` / coverage-table HTML — ~30 lines × 4 = ~120 lines of copy-paste
that had already started to drift.

- New `src/provenance.js` (~125 lines) — exports:
    * `Provenance.badgeFromArr(arr)` — the winner+verifier badge strip.
    * `Provenance.badgeFromField(fm, field)` — reads `fm[field+"_from"]`
      then delegates to `badgeFromArr`.
    * `Coverage.inSource(fromArr, srcAbbr)` — did source "C"/"SS"/"OA"
      contribute to this field?
    * `Coverage.cell(v)` — one `<td>` for the 4-state matrix
      (null/undefined = —, "skip"/"SKIP" = ⊘, true = ✓, else = ✗).
    * `Coverage.renderTable(rows)` — full Coverage section (h3 +
      thead + tbody + legend). Rows are `[label, cr, ss, oa, ttKey]`.
    * `Coverage.SRC_TAG` + `Coverage.LEGEND_HTML` for callers that
      need the primitives.
- `paper-detail.js`: dropped local `provBadge` (30 lines), `SRC_TAG`
  const, local `cell` (5 lines), and inline coverage-table HTML.
  Local `provBadge` is now a one-line alias so the ~40 call sites
  don't need to change. `renderDetail` lost ~65 lines.
- `author-detail.js`: dropped local `provFromArr` (14 lines), local
  `inSrc`, local `covCell`, and inline coverage-table HTML. Aliases
  keep the 15 call sites unchanged. File shrank 268 → 226 lines.
- `institution-detail.js`: same treatment. 210 → 169 lines.
- `journal-detail.js`: same treatment. 203 → 162 lines.
- `index.html`: `provenance.js` loads AFTER `tooltips.default.js` and
  BEFORE the detail modules. Load-order comment updated.
- `tests/test_script_load_order.py`: new
  `test_provenance_loads_before_detail_modules` — locks the ordering
  in so a future reorder can't silently break every coverage table.

**Small behavior improvement, worth flagging**: paper-detail.js had
always mapped `"crossref-search"` to the C column; author /
institution / journal did not, even though their aggregators inherit
paper frontmatter `_from` arrays that can contain that value. The
new shared `Coverage.SRC_TAG` treats `"crossref-search"` as C on
every page, matching what paper-detail always did. In practice this
only affects rows on the three other pages where a `_from` array
inherited the string; those cells will now show ✓ instead of ✗.

Tests: 31 → 32 pass (added the load-order guard).

---

## 2026-08-15 — Docs + refactor pass (Phase 0 + 1)

Started a code-atlas + refactor cycle to keep source files small enough
that a bug report can be diagnosed by opening only the involved files,
not the whole codebase.

Phase 0 — infra (no runtime changes):
- Added `CODE_MAP.md` (feature → file mapping).
- Added `CHANGELOG.md` (this file).
- Added `TESTING.md` (smoke-test conventions).
- Added `tests/` with smoke suite covering the sanitizer, extract flow,
  and server import health.

Phase 1 — split `src/app.js` (was 3298 lines → 816 lines core):

- `src/notes.js` (912 lines) — Notes tab: sidebar list, rich-text editor,
  toolbar spec, tables (insert/resize/context-menu), session undo/redo,
  autosave. Also fixes a silent bug where `_relativeTime` was defined
  twice in app.js: renamed the notes-version to `_noteRelTime`.
- `src/paper-detail.js` (913 lines) — `loadPaperDetail`, `renderDetail`,
  `reExtract`, `copyBibtex`, `parseRefs`. Still the biggest single
  extracted file; internal renderDetail is the next split candidate.
- `src/author-detail.js` (259 lines) — `loadAuthorDetail` +
  `renderAuthorDetail`.
- `src/institution-detail.js` (201 lines) — same for institutions.
- `src/journal-detail.js` (194 lines) — same for journals.
- Dropped dead code: `_saveSelection` / `_restoreSelection` in app.js
  (unused since the earlier autosave-no-longer-replaces-innerHTML fix).
- Updated `index.html`: script load order documented and grouped
  (app.js → detail bundle → notes.js).

Also updated `CODE_MAP.md` to reflect the new file layout with per-file
line counts and the shared-globals contract between app.js and the
feature modules.

Tests: all 29 pass unchanged.

Phase 4 — audit pass (found + fixed 3 real bugs from the earlier
splits, deleted dead code, added a regression guard for Phase 1):

- Bug (silent since Phase 3): after splitting `extract_metadata.py`,
  the three new client files (`crossref_client`, `openalex_client`,
  `semanticscholar_client`) still referenced the old internal names
  from the pre-split monolith — `_api_get_json`, `_corpus_user_agent`,
  `_ssl_contexts`, `_title_similarity`, `_headers`, `_surname_initial`.
  My sed only renamed one of them (`_surname_initial → surname_initial`);
  the rest were dangling. Every `_from_*` mapper would have raised
  `NameError` on first real call — the smoke tests didn't catch it
  because none of them hit the actual Crossref/OA/SS APIs. Found by
  running pyflakes across every source file. Fixed by:
    * renaming call sites to the shared `_api_http` names
      (`api_get_json`, `corpus_user_agent`, `ssl_contexts`,
      `title_similarity`, `api_headers`)
    * adding missing top-level imports (`json`, `ssl`, `urllib.error`,
      `urllib.request`, `urllib.parse`) to clients whose raw HTTP paths
      (`crossref_search_by_title`, `semanticscholar_author_batch`) needed
      them
    * dropping unused imports (e.g. `html as _html` at top of
      `crossref_client` — only the inner `_strip_html` used it)
    * fixing `extract_metadata.py`'s dangling `surname_initial` in
      `_merge_author_institutions`

- server.py: dedup `_require_corpus`. There were TWO copies doing the
  same job — the local `_require_corpus` (12 call sites) and the
  shared `require_corpus_or_abort` in `_api_common.py`. Replaced every
  local call with the shared one; dropped the local def.

- server.py: dropped unused imports (`corpus_root`, `inbox_dir`,
  `notes_dir` from `_paths` — after Phase 2 the endpoints still in
  server.py don't touch those dirs directly). Also collapsed three
  redundant `import re, unicodedata` calls inside `_aggregate_*`
  helpers (`re` already imported at module top).

- Other files: dropped unused imports in `check_schemas.py` (`sys`,
  `Path`, `_papers_dir` alias) and `oa_enrichment.py` (`time`).

- Test: added `tests/test_script_load_order.py` (2 tests) to lock in
  the Phase-1-regression fix. If someone reorders `index.html` so
  feature modules load AFTER `app.js`, the guard fails immediately
  instead of silently killing every event handler below the first
  ReferenceError.

Not in this pass (documented as future work in CODE_MAP):
- `_aggregate_authors` / `_aggregate_institutions` / `_aggregate_journals`
  in server.py (~365 lines total, ~40% shared shape).
- `renderAuthorDetail` / `renderInstitutionDetail` / `renderJournalDetail`
  in the split frontend files (~680 lines total, similar shape).
  Both would need proper frontend/aggregator tests before extracting
  a shared skeleton without risking regressions.

Tests: 29 → 31 pass.

Phase 2 — split `python/server.py` (1451 lines → 982 lines core):

- `python/notes_api.py` (275 lines) — `notes_bp` Flask blueprint owning
  the five note endpoints, the HTML sanitizer + its allow-list, and the
  notes-JSON storage helpers (`_note_id`, `_note_row`, `_iso_now`).
- `python/extract_api.py` (280 lines) — `extract_bp` blueprint owning
  `/api/extract`, `/api/scan`, `/api/paper/<slug>/re-extract` plus the
  helpers only they use (`_resolve_slug_collision`,
  `_prefetch_enrichment_for_slug`, `_kick_enrichment`).
- `python/_api_common.py` (20 lines) — the one shared helper (used by
  both blueprints AND the endpoints still in server.py):
  `require_corpus_or_abort`.
- `server.py` now registers both blueprints and retains: config store,
  Flask app setup, dev-only surfaces, list/detail endpoints for
  papers/authors/institutions/journals, aggregators, PDF-serve,
  tooltips, highlights, reveal, and the native-dialog bridge.

Tests updated: `test_note_sanitizer.py` imports `_sanitize_note_html`
from `notes_api` now instead of `server`. All 29 tests still pass.

Phase 3 — split `python/extract/extract_metadata.py` (2076 → 951 lines):

- `python/extract/_api_http.py` (132 lines) — shared HTTP + SSL +
  text-similarity helpers used by all three clients:
  URL/timeout constants, `api_get_json`, `api_headers`,
  `ssl_contexts`, `corpus_user_agent`, `surname_initial`,
  `norm_title`, `title_similarity`.
- `python/extract/crossref_client.py` (369 lines) — Crossref
  `/works/<doi>` lookup, `/works?query` title-search fallback, and
  the `_from_crossref` mapper (the biggest single mapper — 240 lines
  of nested Crossref-shape → frontmatter transformations).
- `python/extract/openalex_client.py` (381 lines) — OpenAlex work
  lookup and the `_from_openalex` mapper (per-author affiliation
  hierarchy, OA status, topic/keyword hierarchy, counts-by-year,
  versions, retraction notice — the source of most enriched fields).
- `python/extract/semanticscholar_client.py` (394 lines) — SS graph
  lookup, `semanticscholar_author_batch` (h-index / paper count /
  citations by author ID — used by oa_enrichment worker), and the
  `_from_semanticscholar` mapper (owns tldr / SPECTER2 embedding /
  bibtex / publication_types / paper_type / ss_paper_id + arXiv/
  PubMed external IDs).
- `python/extract/extract_metadata.py` (951 lines) — kept: DOI
  extraction + scoring + cross-check (`_extract_doi_candidates`,
  `_rank_dois`, `_score_doi`, `_select_best_doi`); PDF text
  fallbacks (`_title_candidates_from_pdf_text`, `_from_pdf_metadata`,
  `_from_text_heuristic`, `_from_slug`, container-title / label-soup
  filters); per-field merger (`merge`, `merge_with_provenance`,
  `PROVENANCE_FIELDS`); orchestrator (`_collect_api_metadata`,
  `_merge_api_meta`, `extract_metadata`, `main`).

No behaviour change. Public API preserved — `extract_metadata()`,
`crossref_lookup()`, `crossref_search_by_title()`, `openalex_lookup()`,
`semanticscholar_lookup()`, `semanticscholar_author_batch()` all
importable from `extract_metadata` (re-exported) so external scripts
(scripts/backfill_dois.py, tests, etc.) don't need updates.

Extract-metadata blast area is now four focused files instead of one
2076-line monster: to change how Crossref maps a field, open
crossref_client.py — the OA/SS mappers stay out of your context.

Tests: all 29 pass unchanged.

## 2026-08-15 — Notes tab (rich-text editor, tables, undo/redo)

Added a top-level "Notes" tab with a rich-text scratchpad editor.
Features: bold/italic/underline/strike, numeric font-size input (1–120),
bullet/numbered lists, insert tables with row/col prompts and
Excel-style resize handles, right-click cell menu (insert/delete
row/column, delete table), session-scoped per-note undo/redo with
Cmd-Z / Cmd-Shift-Z. Server-side HTML sanitizer strips scripts,
`javascript:` URLs, arbitrary styles/classes; clamps font-size and
table dimensions into safe ranges. Notes stored as JSON files under
`<corpus_dir>/notes/<id>.json`.

Also, related to the extract pipeline: `_title_candidates_from_pdf_text`
was added to `extract_metadata.py` as a fallback when `/Info` has no
title and text-scan DOI matching failed. Filters out journal/masthead
shapes and metadata-label soup so failed extractions land at `unknown`
rather than storing wrong data. `re_extract()` now runs
`canonical_slug_for()` and renames PDF+summary in place when the
resolved metadata's canonical slug differs.
