# Corpus Code Map

**Purpose**: When a bug report comes in, read this file first. It tells you
which source files own each feature. Only open the specific files you need.

> Line numbers reflect the file state as of the last commit. They will
> drift; treat them as approximate anchors, not source of truth. The
> `//` and `# ----------` section markers within each file are the
> authoritative internal index.

---

## Directory layout

```
dev/
├── launcher.py                        # pywebview boot + Flask thread; writes ~/.corpus/server.json in dev
├── build_ship.py                      # macOS .app zip + Windows source zip; 4 preflight gates
├── build_windows.bat                  # ships INSIDE the Windows source zip; venv + PyInstaller on Windows
├── pyinstaller_corpus.spec            # ONE spec, both platforms (branches on IS_WINDOWS)
├── python/
│   ├── server.py                      # Flask composition root: app, IS_DEV, access-log hooks, init_app, dev-only wiring (~225 lines)
│   ├── config_api.py                  # Blueprint: /api/config, /api/tooltips, /api/pick-corpus + config store + Keychain (~215 lines)
│   ├── papers_api.py                  # Blueprint: /api/papers, /api/paper/<slug>, /pdf/<slug>, highlights, reveal (~240 lines)
│   ├── entities_api.py                # Blueprint: /api/authors + /api/institutions + /api/journals (+ their details) + aggregators + key helpers (~660 lines)
│   ├── notes_api.py                   # Blueprint: /api/notes[/id] + HTML sanitizer (~285 lines)
│   ├── projects_api.py                # Blueprint: /api/projects[/id][/members] + member-kind allow-list (~375 lines)
│   ├── documents_api.py               # Blueprint: /api/documents, /document/<id>/pdf, /api/document/<id>/highlights — non-paper PDFs, no lookups (~140 lines)
│   ├── highlights_store.py            # load / clean / save a PDF's highlight list — shared by papers_api and documents_api (~75 lines)
│   ├── extract_api.py                 # Blueprint: /api/extract, /api/scan, /api/paper/<slug>/re-extract + helpers (~315 lines)
│   ├── _api_common.py                 # Shared Flask + frontmatter helpers: require_corpus_or_abort, summary_paths, _read_summary (+ parsed-summary cache), _fm_dict, _walk_summaries (yields slug/fm/body), _strip_quotes, _parse_json_block (~165 lines)
│   ├── citations.py                   # Intra-corpus citation index: DOI-matched links between papers, derived not stored (~200 lines)
│   ├── bridges.py                     # Citation bridges: pure graph logic, no Flask, no network (~130 lines)
│   ├── bridges_api.py                 # Blueprint: /api/bridges[/compute] + compute_bridges_now() + cache (~250 lines)
│   ├── progress.py                    # Blueprint: /api/progress + the single job slot every long job reports into (~155 lines)
│   ├── pdf_refs_merge.py              # Folds PDF-read refs into the API list — fills blanks + appends, never overwrites (~185 lines)
│   └── extract/                       # metadata + refs + prefill pipeline
│       ├── extract_metadata.py        # orchestrator: DOI extraction + PDF fallbacks + merger (~950 lines)
│       ├── crossref_client.py         # Crossref /works lookup + title-search + _from_crossref mapper (~370 lines)
│       ├── openalex_client.py         # OpenAlex lookup + _from_openalex mapper (~380 lines)
│       ├── semanticscholar_client.py  # SS graph lookup + author batch + _from_semanticscholar mapper (~390 lines)
│       ├── _api_http.py               # shared HTTP/SSL/text-sim helpers (~130 lines)
│       ├── extract_references.py      # references-list parser (Crossref) + the md line format (writer + reader)
│       ├── extract_references_pdf.py  # references read from the PDF's own text — third source, additive only
│       ├── prefill_summary.py         # write summary MD skeleton
│       ├── rename_pdfs.py             # inbox → papers/<slug>.pdf
│       ├── backfill_dois.py           # retro-DOI resolver
│       ├── oa_enrichment.py           # per-entity OA cache
│       ├── check_schemas.py           # summary MD schema validator
│       ├── _paths.py                  # dir helpers (papers/, summaries/, notes/, …)
│       └── _fm.py                     # YAML frontmatter parser
├── src/
│   ├── index.html                     # SPA shell (tabs + panes + modals)
│   ├── app.js                         # boot, state, tab switch, filters, papers list, wiring (~800 lines)
│   ├── paper-detail.js                # renderDetail + loadPaperDetail + reExtract (~970 lines). Ref parsing moved server-side 2026-08-25; connections block lives in corpus-links.js
│   ├── author-detail.js               # loadAuthorDetail + renderAuthorDetail (~225 lines)
│   ├── institution-detail.js          # loadInstitutionDetail + renderInstitutionDetail (~170 lines)
│   ├── journal-detail.js              # loadJournalDetail + renderJournalDetail (~160 lines)
│   ├── notes.js                       # Notes tab: editor, toolbar, tables, undo/redo (~900 lines)
│   ├── projects.js                    # Projects tab: list, detail, member picker (~315 lines)
│   ├── documents.js                   # Documents tab: list, upload, PDF pane via app.js pdfPaneHtml (~120 lines)
│   ├── note-workspace.js              # window.NoteWorkspace — popped-out note: PDF panel, highlight picking (~150 lines)
│   ├── modals.js                      # window.Modals — arrow-nav / focus-blocker registry (~55 lines)
│   ├── nav.js                         # window.Nav.nextIndex — pure arrow-key arithmetic (~30 lines)
│   ├── entity-keys.js                 # window.EntityKeys — JS mirror of entities_api.py's _author_key/_journal_key/_institution_key (~80 lines). Parity enforced by tests/test_metadata.py::test_entity_key_python_parity. papers_api.py imports those helpers rather than copying them.
│   ├── entity-detail.js               # window.EntityDetail.render — shared skeleton for author/institution/journal detail panes (~65 lines)
│   ├── corpus-links.js                # window.CorpusLinks.render — in-corpus citation connections block; both directions ALWAYS rendered (~100 lines)
│   ├── countries.js                   # window.Countries.name/withCode — ISO 3166-1 alpha-2 → country name via Intl.DisplayNames (~90 lines)
│   ├── progress.js                    # window.Progress.watch — polls /api/progress, renders the job strip (~105 lines)
│   ├── provenance.js                  # shared Provenance.* / Coverage.* helpers used by all 4 detail modules (~125 lines)
│   ├── styles.css                     # all styles
│   ├── tooltips.default.js            # shipped tooltip strings
│   └── vendor/pdfjs/                  # PDF.js viewer (do not modify)

Script load order in index.html:
    tooltips.default.js → countries.js → provenance.js → modals.js → nav.js
      → entity-keys.js → entity-detail.js → corpus-links.js
      → progress.js → {paper,author,institution,journal}-detail.js → notes.js
      → note-workspace.js
      → projects.js → app.js
Shared helpers (provenance/modals/nav) load first so app.js and the
detail modules can reference their namespaces safely. Detail modules
load AFTER provenance.js (they alias Provenance/Coverage at parse
time) and BEFORE app.js (app.js's MODES table references the detail
modules' exported functions). The detail modules and app.js lean on
each other's globals resolved at call-time inside function bodies —
`state`, `api`, `toast`, `$`, `escHtml`, `escAttr`, `SRC_ABBR`,
`fmtTs`, `tsSpan`, `_relativeTime`, `hideEmptyState`, `tt` come from
app.js; MODES entries reference detail-module renderers.
└── tests/                             # smoke test suite (see TESTING.md)
```

---

## Feature → files map

### Notes (rich-text scratchpad)

Everything under the "Notes" tab.

| Concern                          | File                        | Section / symbols |
|----------------------------------|-----------------------------|-------------------|
| DOM shell (tab + list + detail)  | `src/index.html`            | `data-tab="notes"`, `#notes-list`, `#note-detail`, `#btn-new-note` |
| List + detail + editor           | `src/notes.js`              | top of file |
| Toolbar spec                     | `src/notes.js`              | `_NOTE_TOOLBAR`, `renderNoteDetail`. SINGLE source for both the button and its keyboard chord — the `key` field is what the keydown handler looks up. |
| Formatting chords (⌘B/U/I/S)     | `src/notes.js`              | `keyHandler` resolves `e.key` against `_NOTE_TOOLBAR[].key`, then dispatches by clicking the matching `.note-tb-btn[data-cmd]` so keyboard and mouse share one path (focus restore, history checkpoint, save). Force-save moved to ⌘⇧S. |
| Rich-text ops (bold/italic/…)   | `src/notes.js`              | `_wireNoteEditor` — toolbar.click handler |
| Font-size input                  | `src/notes.js`              | `_applyNoteFontSizePx`, `_NOTE_FONT_SIZE_MIN/MAX` |
| Tables (insert / resize / menu) | `src/notes.js`              | `_insertNoteTable`, `_wireNoteTables`, `_startNoteTableResize`, `_showNoteTableContextMenu`, `_tableInsertRow/Col`, `_tableDeleteRow/Col` |
| Session undo/redo               | `src/notes.js`              | `_noteHistory` Map + `_history*` fns |
| Autosave (debounced)            | `src/notes.js`              | `_wireNoteEditor.commitSave`, `scheduleSave` |
| Note-scoped time formatter      | `src/notes.js`              | `_noteRelTime` (renamed from `_relativeTime` on split to avoid colliding with the journals-detail one, which had a different format) |
| CSS                              | `src/styles.css`            | `.note-detail`, `.note-toolbar`, `.note-body`, `.note-tb-*`, `.note-table*` |
| Server endpoints                 | `python/notes_api.py`       | `/api/notes` (list, POST), `/api/note/<id>` (GET/PUT/DELETE) — Flask blueprint `notes_bp` |
| HTML sanitizer                   | `python/notes_api.py`       | `_sanitize_note_html`, `_NOTE_ALLOWED_TAGS`, `_NOTE_ALLOWED_ATTRS`, `_sanitize_table_style` |
| Storage layout                   | `python/extract/_paths.py`  | `notes_dir()` → `<corpus>/notes/<id>.json` |
| Entity links (insert)            | `src/notes.js`              | `_openEntityLinkPicker`, `_entityLinkHtml`, toolbar entry `entityLink: true` |
| Entity links (right-click)       | `src/notes.js`              | `_wireNoteEntityLinks` → "Go to <noun>" / "Remove link" |
| Shared popup menu                | `src/notes.js`              | `_showNoteMenu(x, y, actions, onChanged)` — used by BOTH the table menu and the link menu |
| Pop-out keeps your place         | `src/notes.js` (`noteScrollAnchor`, `restoreNoteScrollAnchor`, `_noteScrollParent`), `src/app.js` (`openDetached`, `_readDetachedHash`, `openDetachedNote`) | Popping out a note records the top-level block at the top of the view plus the fraction scrolled into it, sends it as `&at=<i>&atf=<f>` in the pop-out URL, and the pop-out scrolls there after first layout. Block-based, not pixels, because the pop-out is a different width; each side finds its own scrolling ancestor. Pinned by `tests/src/note-scroll-place.test.js`. |
| Note settings dropdown           | `src/notes.js`, `src/styles.css` | Header **Settings** button → `#note-settings-menu` (in `renderNoteDetail`'s markup, closed by default), wired by `_wireNoteSettings(root, onDelete)`. Closes on ×, Escape or outside click; document listeners exist only while open. Only item: Delete note. New note-level options = another `role="menuitem"` button in that markup. Pinned by `tests/src/note-settings.test.js`. |
| Which entities are linkable      | `src/app.js`                | MODES entries declaring `linkAttr` → `window.LINKABLE_MODES`. Single source; the picker, the deep-link handler and the sanitizer all derive from it. |
| Link sanitiser rules             | `python/notes_api.py`       | `_NOTE_LINK_ATTRS`, `_NOTE_LINK_DATA_ATTRS`, `_NOTE_LINK_VALUE_RE`, `_NOTE_A_ALLOWED_CLASSES`. Parity with app.js enforced by `tests/test_note_link_attrs.py`. |

### Papers (list + detail)

| Concern                          | File                        | Section / symbols |
|----------------------------------|-----------------------------|-------------------|
| Sidebar list                     | `src/app.js`                | `loadPapers`, `renderPapers`, `selectPaper` |
| Detail pane                      | `src/paper-detail.js`       | `loadPaperDetail`, `renderDetail` (main pane) → `renderPaperInto(host, d, opts)` (the one paper-info renderer; every lookup scoped to `host`) — still ~800 lines, next refactor candidate (break out per-section renderers) |
| Bibtex copy / re-extract / refs  | `src/paper-detail.js`       | `copyBibtex`, `reExtract`, `parseRefs` |
| CSS                              | `src/styles.css`            | `.papers-list`, `.paper-detail`, `.pd-*` |
| Detached-window layout           | `src/styles.css`            | `body.corpus-detached …` block. Header is compacted there ONLY (actions row, metadata on one line, Pop out hidden) — the docked pane keeps the column layout because it sits beside a 340px sidebar. Pinned by `tests/test_detached_layout.py`. |
| Reading a summary                | `python/_api_common.py`     | THREE ways to read a summary were consolidated 2026-09-17: `list_papers` globbed for itself, `paper_detail` did a raw `read_text` + `parse_frontmatter`, and everything else used `_walk_summaries`. All now go through `summary_paths()` + `_read_summary()`. |
| Endpoints                        | `python/papers_api.py`      | `/api/papers`, `/api/paper/<slug>`, `/api/citations`, `/api/paper/<slug>/reveal[/<kind>]`, `/api/paper/<slug>/highlights` (blueprint `papers_bp`). `/api/paper/<slug>/re-extract` lives in `python/extract_api.py`. |
| "no DOI" chip                    | `src/app.js` + `styles.css` | `renderPapers` emits `data-no-doi`; `.papers-list .p-no-doi` styles |
| Paper-info & PDF subtabs        | `src/app.js`                | `renderDetail` builds subtabs; `state.paperSubtab` |
| PDF viewer + highlights          | `src/vendor/pdfjs/web/corpus-highlights.{js,css}` | (see design doc at top of that JS file) |
| Note gutter rendering            | `src/app.js`                | `_renderNoteGutter` — updates cards IN PLACE when the note-id set is unchanged (`gutter.dataset.noteSig`), rebuilds only when it changes. Never writes to a focused textarea; preserves scrollTop across a rebuild. Rebuilding while typing destroyed the caret AND zeroed scroll, which the sync listener forwarded to the viewer as `set-scroll: 0`. Pinned by `tests/test_note_gutter_stability.py`. |
| Highlight removal — eraser       | `src/vendor/pdfjs/web/corpus-highlights.js` | `eraseSelection()`; toolbar `#corpusEraseBtn`; `body.corpus-erasing`. Drag removes every highlight the drag touches, regardless of start point or active colour. Mutually exclusive with Highlight mode. |
| Highlight undo (1 level)         | `src/vendor/pdfjs/web/corpus-highlights.js` | `commitHighlights(label, fn)` is the ONLY place `state.highlights` may be mutated — it snapshots, mutates, renders, saves, notifies. `undoLast` / `clearUndo` / `refreshUndoButton`; toolbar `#corpusUndoBtn`; Cmd/Ctrl-Z. Note edits clear the snapshot. Design-doc §6b. |
| Shared selection geometry        | `src/vendor/pdfjs/web/corpus-highlights.js` | `resolveSelection` / `highlightsOverlapping` — used by BOTH the highlight subsume rule and the eraser; see design-doc §3 for why rects come from spans. `highlightsOverlapping` compares every stored rect against every SELECTION rect; a bounding-box test is wrong for multi-line spans (design-doc §6). `boundsOf` removed 2026-09-09 — it existed only for that broken test. |

### Intra-corpus citation links

Paper A cites paper B and both are in the corpus → a link. The
substrate for connection analysis.

| Concern | File | Section / symbols |
|---|---|---|
| Index + graph | `python/citations.py` | `build_index`, `CitationIndex`, `resolve_references`. Module docstring explains why links are derived, not stored. |
| PDF reference reader | `python/extract/extract_references_pdf.py` | `extract_references_from_pdf` -> (refs, status). Status distinguishes "ok" / "no_section" / "unreadable" — an unreadable scan must never look like a paper that cites nothing. |
| PDF merge rule | `python/pdf_refs_merge.py` | `enrich` (fill blanks only), `pdf_only` (append unmatched), `load_or_extract` (disk cache under `<corpus>/pdf_refs/`). PDF NEVER overwrites an API value. |
| Reference-line parser | `python/extract/extract_references.py` | `parse_ref_line`, `parse_references_section` — the ONLY reader of the line format; `Reference.to_md_line` is the ONLY writer. Both in this file so they can't drift; round-trip test at `tests/test_ref_line_roundtrip.py`. |
| DOI normalization | `python/extract/_api_http.py` | `normalize_doi` — single source of truth. `citations` re-exports it; `extract_references._norm_doi` is an alias; `extract_api._resolve_slug_collision` uses it to decide paper identity on import (it compared raw strings until 2026-09-17, which made `doi: unknown` match itself and silently overwrite a different paper). Pinned by `tests/test_citations.py::test_one_doi_normalizer_shared_by_matcher_and_parser`. Does NOT collapse a double slash — see ROADMAP. |
| Per-paper links | `python/papers_api.py` | `paper_detail` returns `references` / `cites` / `cited_by` / `ref_counts` |
| Whole-corpus graph | `python/papers_api.py` | `citation_graph` → `/api/citations` (nodes + directed edges + totals + `duplicate_dois`) |
| UI — connections block | `src/corpus-links.js` | `CorpusLinks.render({cites, citedBy, refCounts, hasDoi, titleFor})`. Called from `renderDetail` in `paper-detail.js`; positioned directly after the metadata grid. Tested at `tests/src/corpus-links.test.js`. |
| UI — per-ref chip | `src/paper-detail.js` | `.ref-incorpus` anchor inside the refs `<li>` map, uses `data-open-paper` |
| CSS | `src/styles.css` | `.pd-links`, `.pd-links-list`, `.ref-incorpus` |
| Filter-box styling | `src/styles.css` | One rule covers `.sidebar-header input`, `.pj-picker-filter` and `.note-link-filter`. The modal two used to declare width+margin only, missing the padding and `font: inherit` — a clipped placeholder in the default search font. Pinned by `tests/test_list_search.py::test_every_filter_box_shares_one_style_rule`. |

**Matching is DOI-only.** Reference author blocks are usually a bare
surname and titles are often absent, so fuzzy title matching would
produce false links — worse than missing ones for graph analysis.
Extending to title matching is a ROADMAP item gated on structured
reference storage.

**Links are never written to disk.** They are recomputed from what is
in `summaries/` on each request, so adding a paper updates every
affected summary's links with no repair pass. `tests/test_citations.py::
test_link_is_not_stored_so_adding_a_paper_creates_it` fails if anyone
changes this to a stored flag.

### Derived-data caches

Two caches sit in front of work that was being redone on every request.
Both are process-local, in-memory, and invalidate off the filesystem —
nothing is written to disk, so no repair pass and no stale file.

| Concern | File | Section / symbols |
|---|---|---|
| Parsed summaries | `python/_api_common.py` | `_SUMMARY_CACHE` + `_read_summary(md)`. Validated on **(mtime_ns, size)** — mtime alone misses a rewrite inside one clock tick, size alone misses a same-length edit. Returns a shallow copy so a caller that mutates frontmatter can't poison later readers. |
| Cache pruning | `python/_api_common.py` | `summary_paths()` — the ONE place summaries are listed, and therefore the one place entries for deleted files are dropped. Pruning used to live inside `_walk_summaries`, which `/api/papers` never called, so deleted summaries leaked forever. |
| Citation index | `python/citations.py` | `build_index()` memoises on `_corpus_fingerprint()` = (file count, newest mtime, total size). `_build_index_uncached()` is the real work. Links remain derived and unstored — this only skips recomputing an identical answer from unchanged inputs. |
| Clearing | both | `clear_summary_cache()` / `clear_index_cache()`. `tests/conftest.py` calls both per test — each test has its own `tmp_path` corpus, so a surviving entry would be a stale answer about a different corpus. |

**Measured 2026-09-17** (best-of-5, warm), before → after:

| Endpoint | 59 papers | 590 papers |
|---|---|---|
| `/api/papers` | 35.1 → 1.1ms | 198.5 → 10.2ms |
| `/api/authors` | 28.9 → 4.5ms | 229.4 → 32.1ms |
| `/api/institutions` | 46.9 → 7.0ms | 439.8 → 41.5ms |
| `/api/journals` | 20.9 → 1.1ms | 202.8 → 11.4ms |
| `/api/citations` | 65.1 → 1.3ms | 617.7 → 12.3ms |

The first request after a change still pays full price, and is ~11%
slower than before (the extra stat + copy). Everything after it is
6-50x faster. Output verified byte-identical across all 10 endpoints on
the real corpus.

### Detached note workspace

Pop a note into its own window: note on the left, a PDF panel on the
right, and links that point at one exact highlight. Added 2026-09-21.

| Concern | File | Section / symbols |
|---|---|---|
| Window identity | `src/app.js` | `DETACH_KINDS`, `detachKey(kind, id)`, `_readDetachedHash()`. A detached window is `"<kind>:<id>"`. `launcher.py` only ever uses that string as a dict key, so generalising from a bare paper slug needed no Python change. A hash with no colon reads as a paper, so windows popped out by an older build still work. |
| Opening | `src/app.js` | `openDetached(kind, id)`, `openDetachedNote(id)`, `_afterDetachChange(kind, id)`. `state.detachedWindows` is keyed by the composite key — every lookup goes through `detachKey`. |
| The split | `src/index.html`, `src/styles.css` | `#note-workspace` / `#nw-note` / `#nw-panel`; `body.corpus-detached-note`. |
| Panel | `src/note-workspace.js` | `NoteWorkspace.showPaper(slug, highlightId)` / `closePanel` / `postToPanel`. Has its OWN post helper — app.js's `_postToViewer` targets `#paper-detail .pdf-viewer`, which does not exist in this window. |
| Links target the panel | `src/app.js` | In the deep-link handler, checked BEFORE `switchMode` — switching tabs in a detached window tears down the split layout. Only `paper` links redirect; other entity kinds have nowhere to go here and are ignored rather than blanking the window. |
| Scroll to a highlight | `src/vendor/pdfjs/web/corpus-highlights.js` (`scrollToHighlight`, `_tryPendingScroll`, hooks on `pagerendered` / `pagesinit`), senders `note-workspace.js::_scrollWhenReady` and `app.js::_scrollPaperPaneToHighlight` | Keeps one pending request; if the highlight's box is not drawn (page not rendered) it jumps to the stored page once, then centres + flashes on render. Requests expire after 10s; repeats of a just-completed scroll are ignored, so senders may re-post. Pinned by `tests/src/highlight-scroll.test.js`. |
| Highlight picking | `src/note-workspace.js`, `src/vendor/pdfjs/web/corpus-highlights.js` | `pickHighlight(cb)` → `{type:"pick-highlight", on}` → viewer sets `state.pickMode` → click reports `{type:"highlight-picked", id, text}`. The pick branch runs BEFORE the Note Mode guard, or a pick armed from the workspace could never fire. A click that hits no highlight stays armed. |
| The link | `src/notes.js` | `_highlightLinkHtml(slug, id, label)` / `_insertHighlightLink`. Carries BOTH `data-open-paper` and `data-open-highlight`, so it degrades to an ordinary paper link in the docked view or when the highlight has been erased. |
| Scrolling to it | `corpus-highlights.js`, `src/app.js`, `src/note-workspace.js` | `scrollToHighlight(id)` returns false for an unknown id (leaves the paper where it is). Both panes retry while the document loads — there is no ready message on the bridge, and adding one is a new contract for a value that is cheap to retry. |
| Sanitizer | `python/notes_api.py` | `_NOTE_EXTRA_LINK_DATA_ATTRS` — deliberately NOT in `_NOTE_LINK_ATTRS`, which mirrors the MODES `linkAttr` entries and is parity-tested. A highlight is a position inside a paper, not a navigable entity. |

Pinned by `tests/test_note_workspace.py`.

### Documents (non-paper PDFs)

Added 2026-09-25. Jack: "just want to be able to upload this chapter and
take notes on it" — "none of the api stuff".

| Concern | File | Section / symbols |
|---|---|---|
| Storage | `python/extract/_paths.py` | `documents_dir()` → `<corpus>/documents/<id>/{document.pdf, meta.json, highlights.json}`. NOT papers/ or summaries/, so Scan, citers, bridges and metadata lookups never see a document. |
| Endpoints | `python/documents_api.py` | `GET/POST /api/documents` (list / upload one PDF; title = tidied filename), `PATCH /api/document/<id>` (rename — title only, the id never changes), `GET /document/<id>/pdf`, `GET/POST /api/document/<id>/highlights`. `document_titles()` / `document_exists()` serve projects_api. Every id must match `_ID_RE` before it touches the filesystem. |
| Highlight rules | `python/highlights_store.py` | `clean_highlights` — ONE sanitizer for papers and documents (anchored notes included). |
| Viewer | `src/vendor/pdfjs/web/corpus-highlights.js` | `highlightsApiFor(fileUrl)`: `/pdf/<slug>` → paper endpoint, `/document/<id>/pdf` → document endpoint. |
| Tab | `src/documents.js`, MODES entry `documents` in `src/app.js` | List + upload (`#btn-add-document`, `#document-picker`) + pane. The pane carries `.paper-detail` for layout and renders `pdfPaneHtml`, so the PDF view, Note Mode and gutter are the paper's. |
| Note links, projects, pop-out | MODES `documents` entry (`linkAttr`, `memberKind`), `python/notes_api.py::_NOTE_LINK_ATTRS`, `python/projects_api.py::_PROJECT_MEMBER_KINDS`, `DETACH_KINDS` + the `document` boot branch in `src/app.js`, `NoteWorkspace.showPdf(kind, id, hid)` | All reuse the paper machinery. A note panel's claim is a `<kind>:<id>` key (`launcher.py::set_panel_paper`), the same key a pop-out window uses, so a document in a panel and the same document popped out lock each other out. A highlight link carries `data-open-document` or `data-open-paper` (`notes.js::_highlightLinkHtml`). Rename is in place (`documents.js::_startRename`). |
| Which pane's viewer is live | `src/app.js` | `_pdfPaneRoot()` — the current tab's pane when its MODES entry has `pdfPane: true` (papers, documents), else the paper pane. `_paperViewerFrame`, the gutter, Note Mode and card lookups all go through it. |

Pinned by `tests/test_documents.py`, `tests/src/highlights-endpoint.test.js`,
and `tests/test_dev_testing.py` (Testing's viewer still never drives the gutter).

### Projects (folders of papers and notes)

A project organizes papers and notes without moving them. Anything can
belong to any number of projects.

| Concern | File | Section / symbols |
|---|---|---|
| DOM shell (tab + list + detail) | `src/index.html` | `data-tab="projects"`, `#projects-list`, `#project-detail`, `#project-filter`, `#btn-new-project` |
| List + detail + title/description edit | `src/projects.js` | `loadProjects`, `renderProjects`, `selectProject`, `renderProjectDetail`, `_wireProjectDetail` |
| Member picker | `src/projects.js` | `_openMemberPicker` — deliberately NOT notes.js's `_openEntityLinkPicker` (that one takes a DOM Range and writes into a contenteditable). Row labels come from the same MODES `linkLabel`/`memberLabel`, so the duplicated part is modal markup, not a fact. Extracting a shared picker shell is a ROADMAP item. |
| Which modes are filable | `src/app.js` | MODES entries declaring `memberKind` → `window.PROJECT_MEMBER_MODES` / `window.PROJECT_MEMBER_KINDS`. Single source; the picker, the detail sections and the sidebar count line all derive from it. |
| Server endpoints | `python/projects_api.py` | `/api/projects` (GET/POST), `/api/project/<pid>` (GET/PUT/DELETE), `/api/project/<pid>/members` (POST), `/api/member-projects/<kind>/<mid>` (GET) — blueprint `projects_bp` |
| Member-kind allow-list | `python/projects_api.py` | `_PROJECT_MEMBER_KINDS`. Parity with app.js enforced by `tests/test_project_member_kinds.py`. |
| Add-to-project from a paper | `src/projects.js` (`openProjectPickerFor`, `_toggleMembership`, exported as `window.ProjectMembership.openFor`) + `src/paper-detail.js` (`#btn-add-to-project`) | The reverse entry point: file the paper you are reading without opening its project. Lists EVERY project with the current ones ticked and toggles on click, so one control both files and unfiles — an add-only list would leave removal reachable only from the project side. Stays open between picks. The paper pane only renders the button and calls in; every membership rule stays in projects.js. Three silent seams (the exported name, the `"paper"` kind literal, the two endpoints) are pinned by `tests/test_add_to_project_entry.py`. |
| Stored citers | `python/citers.py` (store, `split_by_corpus`, `fetch_and_store`), `python/citers_api.py` (GET paged / POST fetch), `openalex_client.openalex_citer_pages` (cursor paging, uncapped), `_paths.citers_dir`, `src/citers.js` (`Citers.render` / `load`), host `#pd-citers-host` in paper-detail | Every known citer of a paper, fetched from OpenAlex (on demand, for every paper an import adds, or corpus-wide via `backfill` / `POST /api/citers/fetch-all`) into `<corpus>/citers/<slug>.json` as compact rows under a `fields` list. In-corpus vs elsewhere is decided at READ time from the citation index's DOI map (never stored — it changes with every import), the paper itself excluded. In-corpus citers use the References list's `ref-incorpus` marker; the elsewhere list pages 50 at a time. A failed page stores a partial list marked `complete: false`. NOT used by the bridge search yet (Jack's instruction) — `bridges_api` still uses `openalex_citers_of`. Pinned by `tests/test_citers.py`, `tests/src/citers.test.js`. |
| Slug rename migration | `python/slug_migration.py` (`migrate_paper_slug`, `differs_only_by_suffix`), called from `extract_api.re_extract` | The ONE list of what a paper's slug owns beyond its PDF and summary: `highlights/<slug>.json` and `citers/<slug>.json` (moved, never overwritten), `pdf_refs/<slug>.json` (dropped — regenerable), project `members.paper` lists, and notes' `data-open-paper` links (exact-match, so `pan-2025` never rewrites a `pan-2025-1` link). Re-extract also refuses suffix-only renames (`x-2025-1` → `x-2025`). Logs `paper_slug_migrated`. Added 2026-09-21 after Re-extract renamed `pan-2025-1` and stranded 177 highlights. Pinned by `tests/test_reextract_rename.py`. **Any new slug-keyed store must be added here.** |
| Dev Testing tab (dev only) | `python/dev_only/testing.py` (`FEATURES`, three `/api/dev/testing/*` routes), `python/dev_only/paperclean/` (the extractor + `test_set.json`), `src/dev_only/testing.{js,css}`, MODES entry `testing` in `src/app.js` (four forwards to `window.DevTesting`) | Features under evaluation. Text extractor: the test-set papers, and a side-by-side of live extracted text vs the PDF, each scrolling independently, with a stats strip (retention, mid-paragraph share, dropped blocks). Extraction runs on every click — no cache, so it always shows current code. Slugs outside `test_set.json` 404. The tab ships `hidden` and only `_loadDevOnly` reveals it. Pinned by `tests/test_dev_testing.py` + `tests/test_paperclean.py`. |
| PDF viewer URL | `src/app.js` (`pdfViewerSrc`) | The ONLY builder of a pdf.js iframe `src`, used by the paper pane, the note-window panel and the Testing tab. Carries `pagemode=none` (table of contents starts closed) and `annotationEditorMode=-1`. Three hand-built copies had drifted; pinned by `tests/test_window_editing_locks.py`. |
| Static file content types | `python/server.py` (`WEB_MIME_TYPES`, `pin_web_mime_types`) | Pinned at import so a Windows registry cannot serve `.mjs`/`.js` as `text/plain` — pdf.js's ES modules are refused under a wrong type while the classic-script main app still runs, leaving a toolbar over a black page. Every browser-enforced extension under `src/` must be in the table; `tests/test_web_mime_types.py` walks `src/` to hold it. |
| Viewer did not start | `src/vendor/pdfjs/web/corpus-highlights.js` (`reportViewerLoadFailure`) | `init()` checks `window.PDFViewerApplication` first; if pdf.js never ran it shows a box listing each viewer module and the Content-Type it was served with, and stops. No log line — shipped builds log nothing, and this is the visible substitute. Pinned by `tests/src/viewer-failure.test.js`. |
| One editor per note / paper | `src/app.js` (`isDetachedElsewhere`, `detachedPlaceholderHtml`, the delegated `[data-detach-focus]` handler, `corpus-panel-paper` listener, `state.panelPapers`), `src/notes.js` (`flushNoteSave`, lock at the top of `renderNoteDetail`), `src/note-workspace.js` (`_claim`), `launcher.py` (`_Bridge.set_panel_paper`, `_panel_holder`) | A note popped out is locked in the main window; pending autosave is flushed before it pops. When it closes, the main window RELOADS the note from disk (`_afterDetachChange` → `selectNote`) — re-drawing its pre-pop-out copy is what overwrote Jack's work on 2026-09-28. Behind that, every save carries the revision it was edited from and the server refuses a stale one (`notes_api.update_note`, `notes.js::_showConflict`); a closing window flushes a pending save with `keepalive` (`pagehide`). Pinned by `tests/test_note_stale_writes.py`. A paper in a note window's panel is claimed through the launcher — the only process that sees every window — and is then refused elsewhere (pop-out returns `"busy"`, other panels too, and the main paper pane shows the placeholder). The placeholder buttons send the full `<kind>:<id>` key. |
| Note-panel Info / PDF | `src/note-workspace.js` (`_showTab`, `_loadInfo`), `#nw-panel-tabs` in `index.html` | The FULL paper view — `paper-detail.js::renderPaperInto(host, d, {panel: true, reload})`, the same renderer as the main pane (was a compact copy until 2026-09-25). Panel mode drops the subtabs, pop-out, Re-extract and Add to project, which act on the main window. The PDF iframe is hidden, never destroyed, so switching back keeps the reading position. Pinned by `tests/test_paper_view_single_renderer.py`. |
| Paper-pane viewer messages | `src/app.js` (`_paperViewerFrame`, the `message` listener) | Only the paper pane's OWN pdf.js frame may drive its note gutter / Note Mode. Before 2026-09-21 any frame could, and a second viewer (the Testing tab) would have repainted the open paper's anchored notes with another paper's. |
| Picker shell | `src/projects.js` (`_pickerShell`) | Overlay + filter box + list + dismissal, shared by the project-side member picker and the paper-side project picker. Extracted when the second picker arrived rather than making a third copy of the modal markup. `notes.js`'s entity-link picker is still separate — it writes into a contenteditable Range, see ROADMAP. |
| Storage layout | `python/extract/_paths.py` | `projects_dir()` → `<corpus>/projects/<id>.json` |
| CSS | `src/styles.css` | `.project-detail`, `.pj-*`, `.project-empty` |

**Membership is stored on the PROJECT, never on the paper.**
`prefill_summary.render_frontmatter` emits a fixed field list with no
pass-through, so a `projects:` key in a summary's frontmatter is
silently deleted by the next Re-extract. Same reasoning that put
highlights, pdf_refs and notes in sidecar dirs. Pinned by
`tests/test_projects.py::test_membership_survives_a_summary_rewrite`.

**The reverse index is derived, not stored.** "Which projects contain
this paper?" scans project files (`/api/member-projects/...`), the way
`citations.py` recomputes links. No second copy to desync, no repair
pass when a project is deleted.

**Dangling members are filtered on read, never pruned from disk.** A
paper can be temporarily missing (corpus dir mis-pointed, PDF mid-move).
Filtering hides it; pruning would permanently forget the membership the
first time anyone opened the tab.

**Deleting a project never deletes its contents.** Pinned by
`tests/test_projects.py::test_deleting_a_project_leaves_its_contents_alone`.

### Country display

OpenAlex stores ISO 3166-1 alpha-2 codes. Nothing renders them raw.

| Concern | File | Section / symbols |
|---|---|---|
| The helper | `src/countries.js` | `Countries.name(code)` → "Netherlands"; `Countries.withCode(code)` → "Netherlands (NL)". Both return the input unchanged when it can't be resolved, so callers render the result directly with no guard. |
| Where the names come from | `src/countries.js` | `Intl.DisplayNames` — ICU/CLDR data built into the runtime. Deliberately NOT a hand-written table: ~250 rows of unverifiable fact that drifts as countries are renamed. Falls back to the raw code if `Intl.DisplayNames` is absent (ES2021) or throws. |
| Render sites (9) | `src/app.js` (institutions sidebar), `src/institution-detail.js` (Country row, Location line, subtitle), `src/author-detail.js` (last-known institution, institution list, subtitle), `src/journal-detail.js` (Country of publication), `src/paper-detail.js` (per-institution meta) | All go through the helper. `withCode` only on the two rows explicitly ABOUT the stored field; everywhere else the name alone. |
| Searchability | `src/app.js` | The institutions `searchFields` includes `Countries.name(r.country_code)` — the list displays "Netherlands", so the filter must match it. The raw code keeps working too. |

Enforced by `tests/test_country_display.py`: no module may `escHtml()` a
bare `country_code`, any module referencing one must use the helper, and
the script must load before every module that calls it. The formatting
itself is executed in `tests/src/countries.test.js`.

### Long-job progress

One channel, not one per feature. Scan, Add PDFs and the bridge search
all report into a single server-side job slot; the frontend polls one
endpoint and renders whatever it finds.

| Concern | File | Section / symbols |
|---|---|---|
| The job slot | `python/progress.py` | `start(job, phases) -> Job | None` — None means REFUSED. Writes go through the returned handle: `job.step(phase, detail, done, total)` / `job.finish(error)`; `snapshot()` reads. `progress.NULL` is a no-op handle for a caller that was refused and still has work. Thread-safe — the scan writes from its request thread, the bridge search from a background thread. |
| Endpoint | `python/progress.py` | `GET /api/progress`. Deliberately NOT behind `require_corpus_or_abort`: it is polled twice a second and a 400 per tick before a corpus is picked is noise. |
| UI | `src/progress.js` | `Progress.watch(onDone)` polls every 500ms and renders `#job-progress`. Three levels, as requested: JOB, PHASE ("what function"), DETAIL (which file). |
| Reporters | `python/extract_api.py`, `python/bridges_api.py` | Scan declares its own two phases plus `BRIDGE_PHASES`, so the strip shows "step 2 of 6" across the whole sequence rather than one job that ends and another that appears. The import hands its handle on: `_after_import(slugs, job)` → `citers.backfill(on_step=job.step)` → `compute_bridges_now(job=job)`. |
| Anchored readouts | `src/progress.js`, `src/styles.css` | Step / count / elapsed each render into their own fixed-width slot (`.jp-step` 11ch, `.jp-count` 9ch, `.jp-time` 6ch, right-aligned, tabular digits). One shared right-aligned string made every value slide when any one changed width. |

**Only one job at a time, and the refusal is enforced.** `start()`
returns None while another job is live, and every entry point acts on
it: `/api/scan`, `/api/extract` and both citer endpoints answer **409**.
Writes carry the token `start()` issued, so a refused caller cannot
write into the running job either — a foreign write is dropped and
logged as `progress_foreign_write`.

Why it is enforced rather than advisory: on 2026-09-22 two scans of the
same inbox ran together (server.log, `added=64` and `added=37` two
seconds apart). Each had counted the inbox at a different moment, so the
strip's total alternated between 100 and 98, and the two passes raced
over the same files.

**Units are per-phase, never global.** A job's phases count different
things (files, papers, requests); a single combined bar jumps backwards.

**Polling, not SSE.** `launcher.py` runs werkzeug with `threaded=True`
(verified), so a poll is answered while a scan holds its request
thread. SSE would add a long-lived connection and a reconnect story for
a value that is worthless once the job ends.

### Citation bridges (indirect connections)

A and B are both in the corpus with no citation between them, but a
paper M that is NOT in the corpus cites B and is cited by A. M is a
bridge. Added 2026-09-17 on Jack's request.

| Concern | File | Section / symbols |
|---|---|---|
| Graph logic | `python/bridges.py` | `find_bridges(forward, backward, direct, years)`, `bridges_for(slug, rows)`, `Bridge`. Pure — no Flask, no network, no I/O. |
| Fetch + cache | `python/bridges_api.py` | `/api/bridges` (GET, cache only) and `/api/bridges/compute` (POST, does the work). `bridges_for_slug()` is what `/api/paper/<slug>` calls. |
| Is a paper's citer list done? | `python/citers.py` | `_stored_for(slug, doi)` — a store counts only if fetched for the paper's CURRENT DOI; a re-extract that changes the DOI makes it stale. |
| Where `backward` comes from | `python/citers.py` | `citer_ids_for(slugs, index_path, on_read)` — citing ids from the per-paper stores, through a derived index at `<corpus>/bridges/citer_ids.json` (`bridges_api.CITER_IDS_INDEX`). An entry is trusted only while its store keeps the mtime + size it was read at, so an unchanged store costs a stat and a refetched one is re-read. Only COMPLETE stores are indexed; partial ones fall through to `openalex_citers_of`. Totals: `citers_from_store`, `citer_stores_read`. |
| OpenAlex bulk | `python/extract/openalex_client.py` | `openalex_works_by(field, values, select)` (50/filter), `openalex_citers_of(id)` (paginated `cites:`), `oa_short_id()`. |
| Storage | `python/extract/_paths.py` | `bridges_dir()` → `<corpus>/bridges/index.json`. Sidecar, so a re-extract can't wipe it. |
| UI | `src/corpus-links.js` | `_bridges()` inside the connections block — hop count, connecting-paper titles, year, citation count, and a `Find bridges` button. |
| Button wiring | `src/paper-detail.js` | `findBridges()` — disables and relabels for the ~40s run. |
| CSS | `src/styles.css` | `.pd-bridges`, `.pd-bridge*` |

**Meet in the middle, never search outward.** `forward(A)` is A's
references (already on disk, free); `backward(B)` is everyone citing B
(one request). A bridge is the intersection. Measured 2026-09-17:
walking outward instead cost 64 requests and 18.4s for ONE pair and
found nothing, and a third hop would be ~2000 requests per pair. The
intersection answers every pair at once. On the real corpus: **71
requests, ~43s, 71 bridges** against 22 known direct links.

**The citer store answers `backward`, so a recompute is cheap.**
Before 2026-09-23 every compute re-fetched every paper's citers: 935
paginated requests and 26.6 minutes on the 941-paper corpus, once per
import. The store already held that data. Two consequences: bridges are
only as fresh as the citer store (refresh via a paper's Fetch citers or
`POST /api/citers/fetch-all`), and papers with over 2,000 citers are no
longer truncated the way `openalex_citers_of` truncated them.

**On demand, never on load.** `/api/paper/<slug>` reads the cache and
never touches the network — it is on the path of every sidebar click.
Pinned by `tests/test_bridges.py::test_paper_detail_never_triggers_the_network`.

**Three states the UI must not conflate:** not computed / computed-and-
empty / stale. "No bridges" and "nobody pressed the button" are
different claims, and `computed_at: null` is what distinguishes them.

**Semantic Scholar cannot serve this.** `/paper/batch` with
`fields=references.externalIds` returns `referenceCount: 67` with an
EMPTY references array, and 429s even with a key set. OpenAlex returns
complete `referenced_works` inline.

### Authors / Institutions / Journals (parallel triple)

Same shape as Papers but on OpenAlex-enriched aggregates.

| Concern           | File                | Section / symbols |
|-------------------|---------------------|-------------------|
| Sidebar lists     | `src/app.js`        | `loadAuthors`/`renderAuthors`/`selectAuthor`, same for Institutions/Journals |
| Author detail     | `src/author-detail.js`      | `loadAuthorDetail`, `renderAuthorDetail` (~220 lines) — computes entity-specific parts, delegates skeleton to `EntityDetail.render` |
| Institution detail| `src/institution-detail.js` | `loadInstitutionDetail`, `renderInstitutionDetail` (~150 lines) — same pattern |
| Journal detail    | `src/journal-detail.js`     | `loadJournalDetail`, `renderJournalDetail` (~150 lines) — same pattern |
| Shared skeleton   | `src/entity-detail.js`      | `EntityDetail.render({h1, subtitle, metaRows, refresh, sideBlocks, coverage})` — header + meta grid + refresh bar + side blocks + coverage table. |
| Shared time formatter for all three | `src/app.js` | `_relativeTime` (~line 425) |
| Endpoints         | `python/entities_api.py` | `/api/authors`, `/api/author/<key>`, `/api/institutions`, `/api/institution/<key>`, `/api/journals`, `/api/journal/<key>` (blueprint `entities_bp`) |
| Aggregators       | `python/entities_api.py` | `_aggregate_authors`, `_aggregate_institutions`, `_aggregate_journals`. File-walk skeleton shared via `_walk_summaries()` (in `python/_api_common.py`, along with `_strip_quotes` + `_parse_json_block`). |
| Detail endpoints  | `python/entities_api.py` | `author_detail`, `institution_detail`, `journal_detail` — 4-line bodies each; shared "aggregate → find → enrich → return" logic in `_enrichable_detail()`. |
| OA enrichment     | `python/extract/oa_enrichment.py` | per-entity cache under `~/.corpus/oa_cache/` |

### PDF ingestion + extraction

| Concern                          | File                                     | Section / symbols |
|----------------------------------|------------------------------------------|-------------------|
| Add-PDFs button + file picker    | `src/index.html` + `src/app.js`         | `#btn-add`, `#pdf-picker`, `addPdfs` |
| Upload endpoint                  | `python/extract_api.py`                  | `/api/extract` — saves upload into `<corpus>/inbox/` then calls `_process_inbox_pdf`. Flask blueprint `extract_bp`. |
| Shared inbox-pipeline helper     | `python/extract_api.py`                  | `_process_inbox_pdf(source_pdf, original_name)` — extracts metadata, canonicalizes slug, moves `inbox/x.pdf` → `papers/<slug>.pdf`, renders summary MD, kicks enrichment. Called by both `/api/extract` and `/api/scan`. |
| Re-extract single paper          | `python/extract_api.py`                  | `/api/paper/<slug>/re-extract` |
| Slug canonicalization on upload  | `python/extract_api.py` | `_resolve_slug_collision`, calls into `prefill_summary.canonical_slug_for`. Identity is `normalize_doi` on BOTH sides — same DOI means update in place, a different DOI means `-1`/`-2`/…, and NO DOI on either side means they are not the same paper. The suffix search returns the FIRST FREE number, so a `-2` with no `-1` yields `-1`; Corpus attaches no meaning to the number. The filename is never an input to `canonical_slug_for`, but it IS the last-resort slug when metadata is too thin, and that path goes through the resolver too. Pinned by `tests/test_slug_collision.py`. |
| Enrichment cache warmer          | `python/extract_api.py`                  | `_prefetch_enrichment_for_slug`, `_kick_enrichment` |
| Scan (two-pass sweep)            | `python/extract_api.py`                  | `/api/scan` — pass 1 processes every PDF in `inbox/` via `_process_inbox_pdf`; pass 2 backfills any `papers/` PDF without a summary (legacy path). Response: `{inbox_processed, extracted, skipped}`. |
| Inbox rename script (standalone) | `python/extract/rename_pdfs.py`         | Not invoked by any endpoint — manual CLI-only. Does more sophisticated matching (existing-summary lookup, ambiguity flagging) than `_process_inbox_pdf`. Use when auto-processing over-collides. |
| Metadata resolution              | `python/extract/extract_metadata.py`     | `extract_metadata()` — orchestrator; composes the three clients + fallbacks + merger |
| DOI candidates + scoring         | `python/extract/extract_metadata.py`     | `_extract_doi_candidates`, `_rank_dois`, `_score_doi`, `_select_best_doi` |
| Picker rows are always current | `src/app.js` (`fetchModeList`, `listUrl` on each linkable MODES entry) | The note link picker (`notes.js::_openEntityLinkPicker` → `selectType`) and the project member picker (`projects.js::_openMemberPicker`) refetch the type's list on every open, in every window, without re-rendering its tab. Before 2026-09-29 they loaded only when empty, so a popped-out note never saw papers imported elsewhere. `listUrl` is the one place each endpoint is written; the tab loaders read it. Pinned by `tests/src/fetch-mode-list.test.js`, `tests/test_picker_fresh_lists.py`. |
| List sorting (sidebar + note link picker) | `src/sorting.js`, `sorts` on each MODES entry in `src/app.js` | `Sorting.sortRows(sorts, rows, key, dir)`, `Sorting.defaultDir`. Picker: `notes.js::_openEntityLinkPicker` (sort before the 200 cap), choice per type in localStorage `corpus.linkPickerSort`. Pinned by `tests/src/sorting.test.js`, `tests/test_link_picker_sort.py`. |
| Title-scan fallback              | `python/extract/extract_metadata.py`     | `_title_candidates_from_pdf_text` (page-1 LINES grouped into size tiers within 12%, so mixed-size titles keep every word), `_join_spans` (word breaks from span gaps), `_looks_like_container_title`, `_looks_like_metadata_label_soup`, `_line_scan_candidates` |
| Title → paper resolution         | `python/extract/extract_metadata.py`     | `_resolve_by_title(title)` — Crossref search, then OpenAlex `title.search`, then S2 `/search/match`. A DOI from any of them hands off to the normal three-source DOI lookup; a work with NO DOI is recorded from the OpenAlex / S2 records (`oa_paper_id`, `ss_paper_id`). Every exit is refused if the record is journal front matter (`_is_front_matter`). Seeds: /Info title AND page-1 candidates, always both. |
| Crossref lookup + search + map   | `python/extract/crossref_client.py`      | `crossref_lookup`, `crossref_search_by_title`, `_from_crossref` |
| OpenAlex lookup + map            | `python/extract/openalex_client.py`      | `openalex_lookup`, `openalex_search_by_title` (full work payload, >= `TITLE_MATCH_FLOOR`), `_from_openalex` |
| Semantic Scholar lookup + map    | `python/extract/semanticscholar_client.py` | `semanticscholar_lookup`, `semanticscholar_lookup_id` (by S2 paperId), `semanticscholar_match_title`, `_ss_get` (rate gate + retry), `semanticscholar_author_batch`, `_from_semanticscholar` |
| Title-match rules (one home)     | `python/extract/_api_http.py`            | `TITLE_MATCH_FLOOR = 0.90` (OpenAlex / S2 acceptance), `MIN_TITLE_WORDS` / `title_worth_searching` (all three searches refuse 1–2 word seeds) |
| Shared HTTP + text-sim helpers   | `python/extract/_api_http.py`            | `api_get_json`, `api_headers`, `ssl_contexts`, `corpus_user_agent`, `surname_initial`, `split_display_name`, `norm_title`, `title_similarity`, `crossref_type_to_kind`, `DOI_RE`, `DOI_TRAIL_RE`, `CROSSREF_URL`, `OPENALEX_URL`, `SS_URL` + timeouts |
| Per-field provenance merger      | `python/extract/extract_metadata.py`     | `merge_with_provenance`, `merge`, `_norm_for_compare`, `PROVENANCE_FIELDS` |
| PDF /Info stream                 | `python/extract/extract_metadata.py`     | `_from_pdf_metadata`, `_looks_like_real_title` |
| References parser                | `python/extract/extract_references.py`   | `extract_references_from_crossref` |
| Prefill orchestrator             | `python/extract/prefill_summary.py`     | `render_summary`, `canonical_slug_for` |
| Rename inbox → canonical         | `python/extract/rename_pdfs.py`         | main entry |
| Retro-DOI fill                   | `python/extract/backfill_dois.py`       | main entry |
| Schema validation                | `python/extract/check_schemas.py`       | main entry |
| Frontmatter parser               | `python/extract/_fm.py`                 | `parse_frontmatter` |

### App shell / navigation

| Concern                   | File                    | Section / symbols |
|---------------------------|-------------------------|-------------------|
| Tab registry              | `src/app.js`            | `MODES = [...]` — single source of truth for every sidebar tab. Adding a new tab = one array entry + matching HTML `<ol>`, `<input>`, `<div>` in `index.html`. That promise is enforced by `tests/test_mode_action_buttons.py`, which fails if a MODES entry names an element id the HTML doesn't have. |
| Top-right action slot     | `src/app.js`            | A mode declares `actionBtnId` to own the slot: its button shows, the corpus-wide Add PDFs / Scan pair hides. Notes → `#btn-new-note`, Projects → `#btn-new-project`. Was a hard-coded `id === "notes"` check until 2026-09-14; made MODES-driven when Projects would have added a second branch. Pinned by `tests/test_mode_action_buttons.py`. |
| Back / forward            | `src/app.js`            | `_currentPlace` / `_recordPlace` / `_goToPlace` / `goBack` / `goForward` / `_refreshNavArrows`; buttons `#btn-back` `#btn-fwd`; chords ⌘/Ctrl-[ ⌘/Ctrl-] and Alt+←/→. A place is `{mode, id}`, derived from each mode's `selectedKey`. Recording happens at EXACTLY two sites — the wrap over `MODES[].select` and `switchMode` — so every existing and future navigation path records without being touched. A move after going back truncates the forward branch, browser-style. Capped at `HISTORY_MAX`. Pinned by `tests/test_nav_history.py`. |
| Tab switching             | `src/app.js`            | `switchMode(id)` — iterates MODES, honors per-mode `loadPolicy` (eager/lazy/always). |
| State object              | `src/app.js`            | `const state = { ... }` at top |
| Arrow-key sidebar nav     | `src/app.js`            | `document.addEventListener("keydown", ...)` — uses `MODES_BY_ID[state.mode]` + `Nav.nextIndex()` (from `src/nav.js`). |
| Modal registry            | `src/modals.js`         | `Modals.watchSelector`, `Modals.register`, `Modals.anyOpen`. Dev-only overlays self-register from `dev_only/*.js` so shipped app.js has no dev-only class names. |
| Filter inputs             | `src/app.js`            | Wired via a single `for (const m of MODES)` loop. Filter ids per mode live in `MODES[i].filterId`. The placeholder is set from `MODES[i].searchHint` at boot, so the box names what it actually searches. |
| List search (all lists)   | `src/app.js`            | `modeRowMatches(mode, row, q)` — THE definition of "what text makes a row findable". Every list that filters uses it: the four sidebars, `notes.js`'s entity-link picker, `projects.js`'s member picker. Each mode declares `searchFields` (an ARRAY, matched element-wise — joining would let a query straddle a field boundary and silently widen every filter) plus a matching `searchHint`. Was six inline copies until 2026-09-14; the two pickers searched only the display label, so papers weren't findable by author. Pinned by `tests/test_list_search.py`. |
| List click delegators     | `src/app.js`            | Same loop. Selection via `m.select(li.getAttribute(m.dataAttr))`. |
| Settings modal            | `src/app.js` + `index.html` | `openSettings`, `saveSettings`, `#settings-modal` (auto-registered with `Modals` via the shipped `.modal-overlay:not([hidden])` selector). |
| Empty state               | `src/app.js` + `index.html` | `showEmptyState(reason)` — ONE element, THREE states. `"loading"` is shown by `boot()` BEFORE the corpus read: it names the configured folder and hides the folder picker. `"no-corpus"` (first run) and `"empty-corpus"` (a corpus IS set but holds no papers; names the path) are CONCLUSIONS and are only reachable after the read. The loading state was added 2026-09-20 — the markup used to start on the no-corpus copy, so a cold 209-summary corpus (~20s, 5.4 MB) told a user with a working corpus to "Pick a corpus directory". Pinned by `tests/test_empty_corpus_state.py`. |
| Cross-pane deep links     | `src/app.js`            | One `click` listener that ITERATES `LINKABLE_MODES` (was four hard-coded branches; made MODES-driven 2026-08-27, closing the Wave-3 note). Emitters use `data-open-<linkAttr>`. Emitted at render-time by every detail module. **Keys come from the backend** — `/api/paper/<slug>` returns a `link_keys` block computed by `_paper_link_keys(fm)` in `papers_api.py` using the same `_journal_key` / `_author_key` / `_institution_key` helpers the aggregators use. `src/entity-keys.js` remains as a fallback + reference. Round-trip test at `tests/test_link_keys.py`. |

### Config / secrets

| Concern             | File               | Section / symbols |
|---------------------|--------------------|-------------------|
| Config file         | `~/.corpus/config.json` (outside repo) | `{corpus_dir, mailto}` |
| Corpus-dir guard    | `python/extract/_paths.py` | `is_corpus_source_tree(path)` — true for the Corpus repo or anything inside it, detected by `launcher.py` + `pyinstaller_corpus.spec` together. Enforced twice: `config_api.set_config` 400s when the user picks it, `ensure_corpus_layout` raises rather than scaffolding (a config saved before the guard existed is still on disk). Deliberately does NOT reject any git repo — a corpus under version control is legitimate. Pinned by `tests/test_corpus_dir_guard.py`. |
| Keychain secrets    | `python/config_api.py` | `_get_secret`, `_set_secret`, `KEYRING_SERVICE`, `SECRET_KEYS` |
| Env application     | `python/config_api.py` | `_apply_env` (sets CORPUS_MAILTO etc. for extract scripts). Called by `server.init_app()`, never at import time. |
| Config endpoint     | `python/config_api.py` | `/api/config` (GET/POST), `/api/version` (GET) |
| Native folder pick  | `launcher.py` (`_Bridge.pick_folder`, js_api) + `python/config_api.py` `/api/pick-corpus` |
| Version stamp       | `python/_version.py` | `__version__` — single source of truth; read by `config_api` and `build_ship.py` |
| Server address (dev) | `~/.corpus/server.json` (outside repo) + `python/dev_only/server_address.py` | `write(port)` / `read()` / `clear()`. `launcher.py` binds an EPHEMERAL port, so this file is the only way anything outside the window can reach the API — `/api/progress` above all. Carries the launcher's pid; `read()` returns None once that pid is gone, so a file orphaned by a crash cannot point at a port the OS has reassigned. Stripped from the ship with the rest of `dev_only/`; `launcher.py` guards the import behind `srv.IS_DEV` AND a try/except. Pinned by `tests/test_server_address.py`. Recipe in `CLAUDE.md` § "Seeing what the running app is doing". |

### Bug-reporter (dev-only)

| Concern                | File                                     |
|------------------------|------------------------------------------|
| Storage                | `~/.corpus/bug-reports/<timestamp>-<slug>/` |
| Endpoints              | `python/dev_only/bug_reports.py`         |
| UI                     | `src/dev_only/bug-reporter.js`           |
| Annotation-box maths   | `src/dev_only/draw-geometry.js` (`window.BugDrawGeom`) |
| Dev-only conditional   | `python/server.py` `# ---------- Dev-only surfaces` block |

The draw canvas is sized to the screenshot's NATURAL pixels, and a
Corpus screenshot is the whole scrolled page — 3422 x 16760 (57
megapixels) in the report that raised it. `pointermove` therefore
repaints only the dirty region (the union of where the preview box
was last frame and where it is now), coalesced to one
`requestAnimationFrame` per frame, with the canvas rect cached for the drag. Clearing
the whole canvas per move is what Jack reported as "dragging the red
box is super laggy" on 2026-09-21. `redraw()` still does a full clear,
but only for Undo and Clear boxes. The stroke width has ONE definition
(`BugDrawGeom.LINE_WIDTH`) because the repaint padding is derived from
it — two copies drifting shows up as red smears where an old box was
not fully erased. Pinned by `tests/src/draw-geometry.test.js`.

---

## User action → log signature

**Dev-mode only** — the entire `corpus.*` logger tree is disabled
in shipped builds (`_configure_logging` sets `logger.disabled = True`
when `IS_DEV` is False, and the access-log Flask hooks are not
registered at all). Shipped users produce zero log output. This
table is what you get in dev.

Every user action produces a predictable trail in `~/.corpus/logs/server.log`
(the file the log rotator writes; INFO+ is kept). Use this table to
verify what happened: if the log line isn't there, the action didn't
run (or ran through a different code path than expected).

**Every** `/api/*`, `/pdf/*`, and `/dev/*` request produces one baseline
line via the Flask access-log hook (`server.py:_access_log_finish`):

```
api_request method=<M> path=<P> status=<code> dur_ms=<n>
```

State-changing operations emit an ADDITIONAL event log with the
specific ids/counts involved. Actions that never hit the server
(pure client-side, e.g. tab switch, filter typing) are called out.

| User action | Endpoint(s) hit | Event log(s) emitted |
|-------------|-----------------|-----------------------|
| Pick a corpus folder that is Corpus's own source tree | POST /api/config → 400 | `config_rejected_source_tree path=<p>` — nothing is written to config.json |
| Boot with a corpus_dir that is the source tree (legacy config) | (boot) | `corpus_layout_skipped path=<p>` with traceback — scaffolding refused; the app shows the `empty-corpus` state |
| Boot the app | GET /api/config, GET /api/tooltips, GET /api/papers | (access only; `config_load_failed` on malformed config.json). With a corpus set but zero papers the pane shows the `empty-corpus` state naming the configured path, rather than rendering blank. |
| Click a top tab (Papers / Authors / …) | (client-only) | (none) |
| Click a paper in sidebar | GET /api/paper/<slug> | `pdf_refs_extracted slug=<s> status=<st> count=<n>` on first view (cached after); `citation_index_built papers=<n> edges=<n>`; `citation_index_duplicate_dois count=<n> dois=[…]` when two summaries share a DOI |
| Click an "In corpus" chip on a reference, or a paper in "In-corpus connections" | GET /api/paper/<target-slug> | Same as any paper load (client-side `data-open-paper` delegation, no extra endpoint) |
| Load the citation graph | GET /api/citations | `citation_graph_served papers=<n> edges=<n>` (+ the index lines above) |
| Click Add PDFs → pick file(s) | POST /api/extract | `inbox_processed src=<name> slug=<slug>` per file, or `inbox_process_failed` / `inbox_collision` |
| Click Scan | POST /api/scan | `inbox_processed …` for each inbox PDF; `scan_prefill_failed slug=<s>` on backfill errors. 409 + no log lines when an import is already running |
| Click Re-extract on paper detail | POST /api/paper/<slug>/re-extract | (via extract pipeline: `api_get_json` failures logged if network fails) |
| Click back / forward, or ⌘[ / ⌘] | GET /api/<entity>/<id> for the destination | (access only) — pure client-side history; no endpoint knows about it |
| Type in filter box (any tab, or either picker) | (client-only) | (none) — all six filters run through `modeRowMatches`; the mode's `searchFields` decides what matches |
| Arrow-key sidebar nav | GET /api/<entity>/<key> on new selection | (access only) |
| Click author name in paper detail | GET /api/author/<key> | `oa_author_enrich_bad_orcid` / `oa_author_enrich_empty` on enrichment fail |
| Click publisher name in paper detail | GET /api/journal/<key> | (access only; enrichment errors surface via `api_get_json` warnings) |
| Click institution name (any pane) | GET /api/institution/<key> | (access only) |
| Click "Refresh from source" | GET /api/<entity>/<key>?refresh=1 | Same as detail load; forces cache miss |
| Click reveal-in-Finder (source file / summary) | POST /api/paper/<slug>/reveal/<kind> | (access only) |
| Save PDF highlights (auto, debounced) | POST /api/paper/<slug>/highlights | `highlights_saved slug=<s> count=<n>` |
| Documents tab → Add document… → pick a PDF | POST /api/documents, then GET /api/documents | `document_added id=<id> filename=<name>` |
| Highlight / anchored note in a document | POST /api/document/<id>/highlights (debounced) | `document_highlights_saved id=<id> count=<n>` |
| Document → Rename → type → Enter (or leave the field) | PATCH /api/document/<id> | `document_renamed id=<id>` |
| Document → Pop out ⧉ | bridge `open_detached("document:<id>", …)`; the new window boots `#detached=document:<id>` | none server-side; the main pane shows the "open in a separate window" placeholder |
| Document → Add to project | POST /api/project/<pid>/members `{kind: "document"}` | same as a paper member |
| Click Erase in the PDF toolbar, drag over text | POST /api/paper/<slug>/highlights (debounced) | `highlights_saved slug=<s> count=<n>` with a LOWER count. Confirms first only when an erased highlight carries a note. |
| Click Undo in the PDF toolbar (or Cmd/Ctrl-Z in the viewer) | POST /api/paper/<slug>/highlights (debounced) | `highlights_saved slug=<s> count=<n>` back at the pre-action count. Button is disabled unless a highlight action was the last thing done. |
| Click the Projects tab | GET /api/projects | (access only) — `loadPolicy: "always"`, so it refetches on every switch |
| Create project (`New project` button) | POST /api/projects, GET /api/projects, GET /api/project/<id> | `project_created id=<id> title=<t>` |
| Edit a project title / description (autosave, 500ms) | PUT /api/project/<id> | `project_updated id=<id> title=<t>` — title+description ONLY; membership cannot be written here |
| Click `Add papers…` / `Add notes…` → pick a row | POST /api/project/<id>/members | `project_member_add id=<id> kind=<k> member=<m> count=<n>` |
| Click ✕ on a member row | POST /api/project/<id>/members | `project_member_remove id=<id> kind=<k> member=<m> count=<n>` |
| Paper pane → `Add to project` → tick a project | GET /api/member-projects/paper/<slug>, then POST /api/project/<id>/members | `project_member_add id=<id> kind=paper member=<slug> count=<n>` |
| Paper pane → `Add to project` → untick a project | POST /api/project/<id>/members | `project_member_remove id=<id> kind=paper member=<slug> count=<n>` |
| Paper info → Citers section appears | GET /api/paper/<slug>/citers | (cache read only — baseline access log) |
| Scan / Add PDFs → (after reading) Fetching citers | background, same job as the import | `citers_stored slug=<slug> …` per added paper, then `citers_backfill_done stored=<n> skipped=<n> no_doi=<n> not_found=<n> failed=<n> lookup_failed=<n>` |
| (no button) Fetch citers for the whole corpus | POST /api/citers/fetch-all → 202, background job `Fetching citers for the corpus` | `job_started …` then per-paper `citers_stored`, then `citers_backfill_done …` |
| Paper info → `Find citers` / `Refresh` | POST /api/paper/<slug>/citers/fetch | `job_started job=Finding citers of <slug>` … `citers_stored slug=<slug> rows=<n> reported=<n> complete=<bool> bytes=<n> elapsed=<s>` (or `citers_partial`) |
| Paper info → Citers `Show more` | GET /api/paper/<slug>/citers?offset=<n>&limit=50 | (baseline access log) |
| Click `Delete project` → confirm | DELETE /api/project/<id>, GET /api/projects | `project_deleted id=<id>` — papers and notes are untouched |
| Click a member row in a project | GET /api/paper/<slug> or GET /api/note/<id> | Handled in `projects.js` via `switchMode(mode.id)` + `mode.select(id)`, NOT the `data-open-*` delegation — that one iterates `LINKABLE_MODES`, which excludes notes, so a note row would have been a dead link |
| Click Scan / Add PDFs | POST /api/scan or /api/extract, then GET /api/progress every 500ms | `job_started job=Importing papers`; `inbox_processed …` per file; `auto_bridges_kicked added=<n>` when anything landed; then the bridge lines; `job_finished` |
| Click `Find bridges` on a paper | POST /api/bridges/compute, then GET /api/paper/<slug> | `bridges_computed papers=<n> bridges=<n> failed=<n> elapsed=<s>`; `bridge_compute_no_papers` when nothing resolves |
| Open a paper (bridges section) | GET /api/paper/<slug> | (access only) — cache read, never the network; `bridge_cache_unreadable` if the file is corrupt |
| Click `Pop out` on a note | (client-only) + GET /api/note/<id>, GET /api/papers in the new window | (access only) |
| Click a paper link inside a popped-out note | GET /pdf/<slug> in the panel | (access only) — the panel loads; no navigation happens |
| Click `Link highlight`, then a highlight | (client-only) | (none) — postMessage both ways; the next autosave fires `note_updated` |
| Click a highlight link in a note | GET /api/paper/<slug> (docked) or GET /pdf/<slug> (panel) | (access only) |
| Create note (`New note` button) | POST /api/notes | `note_created id=<id> title=<t>` |
| Edit note (autosave) | PUT /api/note/<id> with `base_revision` | `note_updated id=<id> title=<t> body_len=<n> rev=<r>` |
| Save from a copy that is out of date (note changed in another window) | PUT /api/note/<id> → **409** | `note_update_refused_stale id=<id> base=<b> current=<c>`; the editor stops autosaving and shows "Load the saved version" / "Keep mine" (the latter re-sends with `force`). |
| Notes editor — ⌘B / ⌘U / ⌘I / ⌘S | (client-only) | (none) — resolved via `_NOTE_TOOLBAR[].key` and dispatched through the toolbar button. Next autosave fires `note_updated`. |
| Notes editor — ⌘⇧S | PUT /api/note/<id> | `note_updated id=<id> …` — force-flush save (was ⌘S before ⌘S became strikethrough). |
| Notes editor — Tab / Shift-Tab in a list item | (client-only) | (none) — `_indentListItem`/`_outdentListItem` mutate the DOM (nest under prior sibling, or wrap first-item in a `<li class="li-phantom">`). Next autosave fires `note_updated`. |
| Notes editor — Tab in plain text | (client-only) | (none) — inserts 4 non-breaking spaces via `execCommand("insertText")`. Shift-Tab falls through to browser focus-nav. |
| Notes editor — click `→` / `←` toolbar button | (client-only) | (none) — same as Tab/Shift-Tab in a list item (routed to the same custom helpers). |
| Notes editor — click 🔗, pick an entity | GET /api/authors \| /api/institutions \| /api/journals on first use of that type (lazy modes) | (access only). Insert is client-side; next autosave fires `note_updated`. |
| Notes editor — right-click an entity link → "Go to …" | GET /api/paper/<slug> (or the entity's detail endpoint) | Same as clicking that entity anywhere else. |
| Notes editor — right-click an entity link → "Remove link" | (client-only) | (none) — unwraps the `<a>`, keeping the text. Next autosave fires `note_updated`. |
| Delete note (Settings → Delete note, then confirm) | DELETE /api/note/<id> | `note_deleted id=<id>` |
| Open Notes tab / select a note | GET /api/notes, GET /api/note/<id> | (access only) |
| Open Settings, hit Save | POST /api/config | `config_saved path=<p> keys=[…]` — or `config_save_failed` if disk write throws |
| Native folder-picker (Settings) | POST /api/pick-corpus | (access only) |
| **Dev-only** — click Bug button, submit | POST /api/dev/bug-report | `bug_report_saved label=<l> dst=<p> desc_len=<n> has_screenshot=<b>` |
| **Dev-only** — Planning save | POST /api/dev/planning | (access only) |
| **Dev-only** — Tooltips save | POST /api/dev/tooltips | (access only) |

**Aggregator side effects** (fire on any endpoint that walks
`_aggregate_authors`, so most sidebar loads):
- `frontmatter_parse_failed slug=<s>` — one summary MD couldn't be parsed
- `author_dedupe_merged survivor=<k> dropped=[…] reason=display_match` — near-duplicate author records merged

**API-fetch side effects** (fire on any call into Crossref / OpenAlex /
Semantic Scholar):
- `api_get_json failed url=<u> reason=<r>` — expected URL failure (DNS, timeout, HTTP error)
- `api_get_json unexpected failure url=<u>` — non-URL exception (WARNING with traceback)
- `oa_author_enrich_bad_orcid orcid=<o>` — regex didn't match; malformed ORCID
- `oa_author_enrich_empty orcid=<o>` — OA returned nothing for a valid ORCID
- `enrichment_prefetch_failed slug=<s>` — background daemon-thread crash after upload

**Grep recipes**:
```
grep 'path=/api/paper/'  # every paper-detail load
grep 'status=5'          # server errors
grep 'note_'             # every note lifecycle event
grep 'inbox_'            # every inbox → papers move
grep 'FAIL\|failed'      # anything that broke
awk '/dur_ms/ {print $NF, $0}' | sort -n # slowest requests
```

## Debug playbook

When a bug report mentions the Notes tab / editor / tables / undo:
- Read `CODE_MAP.md` "Notes" section, then just those files.
- Sanitizer bugs → `_sanitize_note_html` + its allow-list constants.
- Editor caret / DOM bugs → `_wireNoteEditor` + the `_history*` fns.
- Editor jumps / scrolls after a picker or input → `_restoreCaret` (the one place focus is handed back; `preventScroll`).
- Table bugs → `_wireNoteTables` + `_start*Resize` + `_noteTableHitTest`.

When a bug mentions the paper detail pane:
- Read `renderDetail` in `src/paper-detail.js` (starts around line 27, runs to end of file).
- Provenance badges + coverage table come from `src/provenance.js`.
- Coverage ROWS (`coverageRows` in `src/paper-detail.js`) are held to what
  `render_frontmatter` writes by `tests/test_coverage_rows.py`. Cell forms:
  fm key / `null` (—) / `SKIP:<key>` (⊘, key must NOT be written) /
  `STORE:<name>` (per-paper store, from `papers_api.PAPER_STORES` →
  `stores` in `/api/paper/<slug>`). A new frontmatter field needs a row or
  an entry in that test's `NOT_A_COVERAGE_FIELD` with a reason.
- Backend data comes from `/api/paper/<slug>` in `python/papers_api.py`.

When metadata extraction picks wrong DOI / title / author:
- Read `extract_metadata()` in `python/extract/extract_metadata.py`.
- Text-scan fallback: `_title_candidates_from_pdf_text`.
- Title lookups and the front-matter guard: `_resolve_by_title`.
- DOI cross-check: `_select_best_doi`.

When something silently doesn't work:
- Check the sanitizer allow-list (`_NOTE_ALLOWED_TAGS`, `_NOTE_ALLOWED_ATTRS`) — HTML tags/attrs not on the list get silently stripped on save.
- Check the schema validator (`check_schemas.py`) — malformed summaries surface here.

---

## Known refactor candidates

**Open items live in `ROADMAP.md`** (§ Expansion points) — not here.
They were moved there on 2026-08-24 so planned work has exactly one
home; keeping the list in two files guaranteed they'd drift apart.
Each entry carries origin, blocked-on status, and a touch-list sketch.

As of that move, five were open: coverage-rows shape, resolver ladder,
Source contract, `renderDetail` split, and the `window.Corpus`
namespace. Two entries that had been on this list are now done and
appear only in the Resolved log below: the blueprint split (finished
2026-08-16 — `server.py` is a composition root over five blueprints)
and the frontmatter emitter (refactored 2026-08-16).

See the CHANGELOG.md 2026-08-16 audit entry for the original audit +
rationale.

### Waves 1 and 2 — closed 2026-08-16

### Resolved

- **2026-08-16** — Wave-2 finish: `renderAuthorDetail` / `renderInstitutionDetail` / `renderJournalDetail` shared skeleton extracted to `src/entity-detail.js`. Refresh-button attribute unified to `data-refresh-entity + data-refresh-key`; app.js's refresh-click handler collapsed from three branches to one dispatch table.
- **2026-08-16** — Wave-1 finish: `rename_pdfs.py` `crossref_lookup` now delegates to `crossref_client` (dropped subprocess+curl); `backfill_dois.py` dropped its local `_user_agent` / `_ssl_contexts` / `_norm` / `title_similarity` duplicates and its three search functions use `api_get_json`. Multi-source promotion into `crossref_client` deferred.
- **2026-08-16** — Wave-1 cleanup burst. `_noteHistory` leak fixed (`deleteNote` clears its entry); `.pdf-viewer` layout switched from magic `calc(100vh - 210px)` to a proper flex column on `.paper-detail` (retraction/failure banners no longer break the iframe); `_apply_env()` moved from import-time side effect to explicit `init_app()` (called by launcher + `__main__` — tests no longer inherit the user's config); logging config added (`~/.corpus/logs/server.log` rotating file + WARNING console; namespaced `corpus.*` loggers in server / api_http / extract_api; 4 highest-value silent-swallow sites now log with `exc_info=True`).
- **2026-08-16** — Aggregator + detail-endpoint dedup (audit A1 / A2, partial). Shared bits — file-walk skeleton (`_walk_summaries`), `_strip_quotes`, `_parse_json_block`, and the three-way detail-endpoint pattern (`_enrichable_detail`) — lifted to module scope in `server.py`. Per-summary accumulation stays per-aggregator; the audit's "~70% shared" claim was optimistic. Snapshot test at `tests/test_aggregators.py`.
- **2026-08-16** — Mode registry (audit A6). Adding a new sidebar tab now requires one `MODES` array entry + matching HTML (was 9 scattered edits). New `src/nav.js` holds the pure arrow-key arithmetic; new `src/modals.js` holds the modal registry so dev-only class names stop leaking into shipped app.js.
- **2026-08-16** — DOI regex duplicated in `extract_metadata` + `rename_pdfs` (extract_references's URL-or-bare variant kept separate); `kind` mapping duplicated in `crossref_client` + `openalex_client`; author-name splitter duplicated in `_from_pdf_metadata` + `_from_openalex`. All extracted to `_api_http.py` (`DOI_RE`, `DOI_TRAIL_RE`, `crossref_type_to_kind`, `split_display_name`).
- **2026-08-16** — Zero frontend tests. Added `tests/src/harness.js` (Node vm loader with fakes) + `tests/src/provenance.test.js` (13 tests) + `tests/test_frontend.py` (pytest glue that skips when node absent). Install `node` (`brew install node`) to activate.
- **2026-08-16** — `provFromArr` / `covCell` / `inSrc` / coverage-table HTML duplicated across all 4 detail modules → extracted to `src/provenance.js` (Provenance.* + Coverage.* namespaces).
- **2026-08-15** — `_relativeTime` was duplicated in app.js (lines 879 and 1178) — second silently overrode first. The notes-version was renamed to `_noteRelTime` in `notes.js` (different format string); app.js retains the one journals/authors/institutions call.
- **2026-08-15** — `_saveSelection` / `_restoreSelection` (dead since autosave stopped replacing innerHTML) — dropped during the notes.js extraction.

See `CHANGELOG.md` for the ongoing refactor log.
