// Corpus v0.1 — vanilla JS. No framework, no build step.
//
// Talks to the Flask server at same-origin. State kept in a small
// module-scoped object; render functions redraw from state on change.

const state = {
  config:      null,           // {corpus_dir, mailto, keys: {…}}
  papers:      [],             // list from /api/papers
  filter:      "",
  // Sidebar sort — Papers only for now. Default matches the backend's
  // author-asc ordering so first paint stays consistent with what
  // /api/papers already returns; user picks override that.
  papersSort:  { field: "author", dir: "asc" },
  // PDF Note Mode is a user-preference toggle — global across papers.
  // When on, the PDF subtab lays the iframe against the left with a
  // right-side gutter for anchored notes. Highlight-mode plumbing
  // inside the iframe is separate (step 2 of the feature build).
  noteMode:    false,
  // slug → windowRef for PDFs the user has popped out into a separate
  // browser window. Each entry is polled for .closed; on close we
  // re-render the main paper detail so its PDF pane comes back to
  // life. Entries are cleaned up in `_watchDetachedWindow`.
  detachedWindows: new Map(),
  // note key ("note:<id>") -> slug shown in that note window's PDF panel.
  // Fed by launcher.py's `corpus-panel-paper` event; the launcher is the
  // authority, this is the main window's copy of its answer.
  panelPapers: new Map(),
  // Set only in a popped-out window: {kind, id, noteMode}. The main
  // window leaves it null.
  detached: null,
  // Detached NOTE workspace: which paper the right-hand panel shows,
  // and whether a highlight pick is armed.
  panelSlug: null,
  pickingHighlight: false,
  selectedSlug: null,
  detail:      null,           // /api/paper/<slug> response
  paperSubtab: "info",         // "info" | "pdf" — which paper subtab is active
  tooltips:    {},             // user overrides fetched from /api/tooltips
  mode:        "papers",       // "papers" | "authors" | "institutions" — which tab is active
  authors:     [],             // list from /api/authors
  authorFilter: "",
  selectedAuthorKey: null,
  authorDetail: null,          // /api/author/<key> response
  institutions: [],
  institutionFilter: "",
  selectedInstitutionKey: null,
  institutionDetail: null,
  journals: [],
  journalFilter: "",
  selectedJournalKey: null,
  journalDetail: null,
  notes: [],
  noteFilter: "",
  selectedNoteId: null,
  noteDetail: null,          // /api/note/<id> response
  // Where the user has been. A "place" is {mode, id} — the same pair
  // every navigation already produces, because each MODES entry
  // declares the state key holding its selection. Nothing else needs
  // to know what a place is.
  history: [],
  historyAt: -1,
  navigating: false,   // suppresses recording while moving through history
  projects: [],
  projectFilter: "",
  selectedProjectId: null,
  documents: [],
  documentFilter: "",
  selectedDocId: null,
  // Dev-only Testing tab (src/dev_only/testing.js). Initialised here
  // because switchMode reads `state[m.stateKey].length` for every mode.
  testingFeatures: [],
  testingFilter: "",
  selectedTestingId: null,
  graphNodes: [],           // dev-only Graph tab: papers in the citation graph
  graphFilter: "",
  selectedGraphSlug: null,
  projectDetail: null,       // /api/project/<id> response (carries `resolved`)
};

// Tooltip lookup — merges defaults (in tooltips.default.js) with any
// user overrides (from ~/.corpus/tooltips.json). Returns "" when no
// tooltip is defined so callers can `title="${tt(k)}"` unconditionally.
window.tt = function tt(key) {
  return (state.tooltips && state.tooltips[key]) ||
         (window.TOOLTIPS_DEFAULT && window.TOOLTIPS_DEFAULT[key]) ||
         "";
};

// Cached one-time probe: does this browser's Intl.DateTimeFormat
// accept timeZoneName: 'shortGeneric'? Older engines throw on
// unknown values; newer ones (Chrome/Edge/Safari ≥ 2022) support it.
let _sgCache = null;
function _supportsShortGeneric() {
  if (_sgCache !== null) return _sgCache;
  try {
    new Intl.DateTimeFormat(undefined, { timeZoneName: "shortGeneric" }).format(new Date());
    _sgCache = true;
  } catch (_) {
    _sgCache = false;
  }
  return _sgCache;
}

// Source abbreviations — Corpus's ONLY pill-styled UI. Kept at
// module scope so any renderer (paper detail, author detail) can
// resolve provenance source names to their display abbreviations
// without duplicating the map.
const SRC_ABBR = {
  "crossref":         "C",
  "crossref-search":  "C",
  "openalex":         "OA",
  "semanticscholar":  "SS",
  "pdf-metadata":     "PDF",
  "slug":             "F",
};

// ---------- Mode registry ----------
//
// Single source of truth for every sidebar tab. Adding a new tab means
// (a) push one entry here, (b) add the matching <ol id="…-list">,
// <input id="…-filter">, and <div id="…-detail"> to index.html.
// Filter listeners, list click-delegators, `switchMode`, and the
// arrow-key handler all iterate this array — no more scattered
// per-tab special cases.
//
// Field summary:
//   id            — tab id (matches <button data-tab="…">)
//   stateKey      — key on `state` holding the list array
//   filterKey     — key on `state` holding the filter string
//   selectedKey   — key on `state` holding the current selection id
//   listId        — HTML id of the sidebar <ol>
//   filterId      — HTML id of the <input type="search"> filter box
//   detailId      — HTML id of the right-pane <div>
//   dataAttr      — HTML data attribute on each <li> that carries the
//                   row's identity ("data-slug" / "data-key" /
//                   "data-note-id")
//   listUrl       — (linkable tabs) the endpoint returning the list; the
//                   ONE place it is written. `load` reads it, and so does
//                   `fetchModeList`, which pickers use to get fresh rows
//                   without re-rendering the tab
//   load          — async: fetch the list from the server + render
//   render        — sync: re-render the sidebar list from state
//   select        — user picked a row (updates state + loads detail)
//   renderDetail  — re-render the right-pane detail for the current
//                   selection
//   loadPolicy    — "eager"  → loaded at boot, tab-switch just renders
//                   "lazy"   → load on first visit, cache thereafter
//                   "always" → load fresh every visit (user-editable)
//   emptyStateHtml (optional) — when nothing is selected AND the list
//                   is empty, replace the detail pane innerHTML with
//                   this. Only Notes uses it today.
//
// Every function referenced below is either declared later in this
// file (function declarations are hoisted) or is a top-level function
// in a feature module loaded before app.js — the load order in
// index.html guarantees they exist by the time MODES is evaluated.
const MODES = [
  { id: "papers", stateKey: "papers", filterKey: "filter", selectedKey: "selectedSlug",
    listId: "papers-list", filterId: "filter", detailId: "paper-detail", dataAttr: "data-slug",
    load: loadPapers, render: renderPapers, select: selectPaper, renderDetail: renderDetail,
    listUrl: "/api/papers",
    loadPolicy: "eager", pdfPane: true,
    linkAttr: "paper", linkNoun: "paper",
    memberKind: "paper", memberNoun: "paper", memberNounPlural: "papers",
    searchFields: (r) => [r.author, r.year, r.title],
    searchHint: "title, author, year",
    linkId: (r) => r.slug,
    linkLabel: (r) => [r.title && r.title !== "unknown" ? r.title : r.slug,
                       r.year && r.year !== "unknown" ? `(${r.year})` : ""].filter(Boolean).join(" "),
    // Sort options — the ONE list behind the Papers sidebar's "Sort by"
    // and the note link picker's (see src/sorting.js). Order = menu order.
    sorts: [
      { key: "author",   label: "Author",     value: (r) => r.author },
      { key: "year",     label: "Year",       value: (r) => r.year, numeric: true },
      { key: "title",    label: "Title",      value: (r) => r.title },
      { key: "added_at", label: "Date added", value: (r) => r.added_at, defaultDir: "desc" },
    ] },
  { id: "authors", stateKey: "authors", filterKey: "authorFilter", selectedKey: "selectedAuthorKey",
    listId: "authors-list", filterId: "author-filter", detailId: "author-detail", dataAttr: "data-key",
    load: loadAuthors, render: renderAuthors, select: selectAuthor, renderDetail: renderAuthorDetail,
    listUrl: "/api/authors",
    loadPolicy: "lazy",
    linkAttr: "author", linkNoun: "author",
    searchFields: (r) => [r.family, r.given, r.primary_institution],
    searchHint: "name, institution",
    linkId: (r) => r.key,
    linkLabel: (r) => [r.family, r.given].filter(Boolean).join(", ") || r.key,
    sorts: [
      { key: "name",   label: "Name",             value: (r) => [r.family, r.given].filter(Boolean).join(", ") },
      { key: "papers", label: "Papers in corpus", value: (r) => r.num_papers, numeric: true, defaultDir: "desc" },
    ] },
  { id: "institutions", stateKey: "institutions", filterKey: "institutionFilter", selectedKey: "selectedInstitutionKey",
    listId: "institutions-list", filterId: "institution-filter", detailId: "institution-detail", dataAttr: "data-key",
    load: loadInstitutions, render: renderInstitutions, select: selectInstitution, renderDetail: renderInstitutionDetail,
    listUrl: "/api/institutions",
    loadPolicy: "lazy",
    linkAttr: "institution", linkNoun: "institution",
    searchFields: (r) => [r.name, r.country_code, Countries.name(r.country_code), r.type],
    searchHint: "name, country, type",
    linkId: (r) => r.key,
    linkLabel: (r) => r.name || r.key,
    sorts: [
      { key: "name",    label: "Name",             value: (r) => r.name },
      { key: "papers",  label: "Papers in corpus", value: (r) => r.num_papers, numeric: true, defaultDir: "desc" },
      { key: "country", label: "Country",          value: (r) => Countries.name(r.country_code) || r.country_code },
    ] },
  { id: "journals", stateKey: "journals", filterKey: "journalFilter", selectedKey: "selectedJournalKey",
    listId: "journals-list", filterId: "journal-filter", detailId: "journal-detail", dataAttr: "data-key",
    load: loadJournals, render: renderJournals, select: selectJournal, renderDetail: renderJournalDetail,
    listUrl: "/api/journals",
    loadPolicy: "lazy",
    linkAttr: "journal", linkNoun: "journal",
    searchFields: (r) => [r.name, r.host_organization, r.venue_type, r.issn],
    searchHint: "name, publisher, ISSN",
    linkId: (r) => r.key,
    linkLabel: (r) => r.name || r.key,
    sorts: [
      { key: "name",   label: "Name",             value: (r) => r.name },
      { key: "papers", label: "Papers in corpus", value: (r) => r.num_papers, numeric: true, defaultDir: "desc" },
    ] },
  { id: "notes", stateKey: "notes", filterKey: "noteFilter", selectedKey: "selectedNoteId",
    listId: "notes-list", filterId: "note-filter", detailId: "note-detail", dataAttr: "data-note-id",
    load: loadNotes, render: renderNotes, select: selectNote, renderDetail: renderNoteDetail,
    loadPolicy: "always", emptyStateHtml: () => _noteEmptyStateHtml(),
    actionBtnId: "btn-new-note",
    memberKind: "note", memberNoun: "note", memberNounPlural: "notes",
    searchFields: (r) => [r.title, r.snippet],
    searchHint: "title, text",
    memberLabel: (r) => r.title || "Untitled note" },
  { id: "projects", stateKey: "projects", filterKey: "projectFilter", selectedKey: "selectedProjectId",
    listId: "projects-list", filterId: "project-filter", detailId: "project-detail", dataAttr: "data-project-id",
    load: loadProjects, render: renderProjects, select: selectProject, renderDetail: renderProjectDetail,
    loadPolicy: "always", emptyStateHtml: () => _projectEmptyStateHtml(),
    searchFields: (r) => [r.title, r.description],
    searchHint: "title, description",
    actionBtnId: "btn-new-project" },
  // Documents (2026-09-25): PDFs that are not papers — a book chapter.
  // Read, highlighted and annotated exactly like a paper's PDF (same
  // viewer, same gutter via `pdfPane: true`), with none of the metadata
  // lookups. Linkable from notes, project members, pop-out: 2026-09-25.
  { id: "documents", stateKey: "documents", filterKey: "documentFilter", selectedKey: "selectedDocId",
    listId: "documents-list", filterId: "document-filter", detailId: "document-detail", dataAttr: "data-doc-id",
    load: loadDocuments, render: renderDocuments, select: selectDocument, renderDetail: renderDocumentDetail,
    listUrl: "/api/documents",
    loadPolicy: "lazy", pdfPane: true, emptyStateHtml: () => _documentEmptyStateHtml(),
    actionBtnId: "btn-add-document",
    linkAttr: "document", linkNoun: "document",
    memberKind: "document", memberNoun: "document", memberNounPlural: "documents",
    memberLabel: (r) => r.title || r.id,
    searchFields: (r) => [r.title, r.filename],
    searchHint: "title, file name",
    linkId: (r) => r.id,
    linkLabel: (r) => r.title || r.id,
    sorts: [
      { key: "title",    label: "Title",      value: (r) => r.title },
      { key: "added_at", label: "Date added", value: (r) => r.added_at, defaultDir: "desc" },
    ] },
  // DEV ONLY — features under evaluation. In MODES rather than bolted on
  // later because every per-mode mechanism (tab switching, filter
  // wiring, list clicks, back/forward) is a boot-time loop over this
  // array; a mode registered after boot would miss all four.
  //
  // All four hooks forward to `window.DevTesting`, resolved at CALL
  // time, which exists only when src/dev_only/testing.js has loaded. In
  // a shipped build that file is stripped and the tab stays hidden, so
  // none of these can be reached — and each no-ops if one somehow is.
  { id: "testing", stateKey: "testingFeatures", filterKey: "testingFilter", selectedKey: "selectedTestingId",
    listId: "testing-list", filterId: "testing-filter", detailId: "testing-detail", dataAttr: "data-testing-id",
    load:         () => window.DevTesting && window.DevTesting.load(),
    render:       () => window.DevTesting && window.DevTesting.render(),
    select:       (id) => window.DevTesting && window.DevTesting.select(id),
    renderDetail: () => window.DevTesting && window.DevTesting.renderDetail(),
    loadPolicy: "always", devOnly: true,
    emptyStateHtml: () => "<p>Pick a feature under test.</p>",
    searchFields: (r) => [r.title, r.summary],
    searchHint: "feature name" },
  // DEV ONLY — the citation graph in 3D (experimental, 2026-10-22).
  // Same forwarding pattern as Testing: hooks resolve window.DevGraph at
  // call time, which exists only when src/dev_only/graph.js has loaded.
  { id: "graph", stateKey: "graphNodes", filterKey: "graphFilter", selectedKey: "selectedGraphSlug",
    listId: "graph-list", filterId: "graph-filter", detailId: "graph-detail", dataAttr: "data-graph-slug",
    load:         () => window.DevGraph && window.DevGraph.load(),
    render:       () => window.DevGraph && window.DevGraph.render(),
    select:       (id) => window.DevGraph && window.DevGraph.select(id),
    renderDetail: () => window.DevGraph && window.DevGraph.renderDetail(),
    loadPolicy: "always", devOnly: true,
    emptyStateHtml: () => "<p>No citations between papers in this corpus yet.</p>",
    searchFields: (r) => [r.title, r.slug],
    searchHint: "title or slug" },
];
const MODES_BY_ID = Object.fromEntries(MODES.map(m => [m.id, m]));

// ---------- Back / forward ----------
//
// Requirement (2026-09-21): back and forward arrows navigate between
// previously visited places.
//
// A place is {mode, id}. Recording hangs off ONE choke point — every
// mode's `select` is wrapped below — rather than being sprinkled
// through the six select functions, the deep-link handler, the arrow
// keys and the project member list. Those all already route through
// `m.select`, so wrapping it catches them by construction, and a new
// navigation path gets history for free.
const HISTORY_MAX = 50;

function _currentPlace() {
  const m = MODES_BY_ID[state.mode];
  return { mode: state.mode, id: (m && state[m.selectedKey]) || null };
}

function _recordPlace() {
  if (state.navigating) return;      // moving through history is not a new place
  const p = _currentPlace();
  const cur = state.history[state.historyAt];
  if (cur && cur.mode === p.mode && cur.id === p.id) return;   // no-op move
  // Any new move truncates the forward branch, exactly like a browser.
  state.history = state.history.slice(0, state.historyAt + 1);
  state.history.push(p);
  if (state.history.length > HISTORY_MAX) state.history.shift();
  state.historyAt = state.history.length - 1;
  _refreshNavArrows();
}

async function _goToPlace(i) {
  const p = state.history[i];
  if (!p) return;
  state.navigating = true;
  try {
    if (p.mode !== state.mode) switchMode(p.mode);
    const m = MODES_BY_ID[p.mode];
    if (p.id && m) await m.select(p.id);
    state.historyAt = i;
  } finally {
    state.navigating = false;
    _refreshNavArrows();
  }
}

function goBack()    { if (state.historyAt > 0) _goToPlace(state.historyAt - 1); }
function goForward() { if (state.historyAt < state.history.length - 1) _goToPlace(state.historyAt + 1); }

function _refreshNavArrows() {
  const b = document.getElementById("btn-back");
  const f = document.getElementById("btn-fwd");
  if (b) b.disabled = state.historyAt <= 0;
  if (f) f.disabled = state.historyAt >= state.history.length - 1;
}

// THE choke point. Wrapping here means the six select functions stay
// unaware of history, and every existing caller records without being
// touched. Recorded AFTER the real select so the state key is updated.
for (const m of MODES) {
  const raw = m.select;
  m.select = async (id) => {
    const r = await raw(id);
    _recordPlace();
    return r;
  };
}

// Entities a note (or any pane) can deep-link to. A mode is linkable
// exactly when it declares `linkAttr`; nothing else maintains a second
// list of entity types. `window.LINKABLE_MODES` so notes.js can build
// its picker from the same declaration.
const LINKABLE_MODES = MODES.filter(m => m.linkAttr);
window.LINKABLE_MODES = LINKABLE_MODES;
// The data-attribute suffixes the notes sanitiser must preserve. Kept
// in sync with python/notes_api.py by
// tests/test_note_link_attrs.py::test_js_and_python_agree_on_link_attrs.
window.LINK_ATTRS = LINKABLE_MODES.map(m => m.linkAttr);

// Fresh rows for a picker, WITHOUT touching the tab that owns the list.
//
// Bug (2026-09-29): in a popped-out note the link-paper picker did not
// pick up papers added to the corpus. The pickers
// read `state[<stateKey>]`, which a window fills once; only the window
// that ran an import reloads its papers afterwards, so a popped-out
// note's picker kept the paper list from the moment it opened. Pickers
// now refetch on every open. They do not call `mode.load`: that
// re-renders the sidebar and, for documents, the document pane — which
// would reload an open PDF under the user.
//
// Tabs with no `listUrl` (notes) keep the old rule: load if empty.
async function fetchModeList(mode) {
  if (mode.listUrl) {
    state[mode.stateKey] = await api(mode.listUrl);
  } else if (!(state[mode.stateKey] || []).length && typeof mode.load === "function") {
    await mode.load();
  }
}

// What a project can contain. A mode qualifies exactly when it declares
// `memberKind`; nothing else maintains a second list of member types.
// `python/projects_api.py::_PROJECT_MEMBER_KINDS` must match, enforced
// by tests/test_project_member_kinds.py.
// Does one row match a filter query? THE single definition of "what
// text makes a row findable", for every list that filters: the four
// sidebars, the notes entity-link picker, and the project member
// picker.
//
// Before 2026-09-14 each of those six places had its own copy. The
// sidebars searched several fields; both pickers searched only the
// DISPLAY label, which for a paper is "Title (year)" — so typing an
// author name into "Add papers…" matched nothing (reported as "should be
// able to search by author here as well"). Adding author
// to one picker would have made a seventh copy.
//
// `searchFields` returns an ARRAY, and each element is tested
// separately, because that is what the sidebars already did. Joining
// into one string would let a query straddle a field boundary
// ("c. 2001" spanning author→year) and silently widen every filter in
// the app.
//
// A mode with no `searchFields` falls back to its display label, so a
// new mode is findable by what it shows without extra wiring.
function modeRowMatches(mode, row, q) {
  if (!q) return true;
  // Lowercase the query HERE rather than trusting the caller. Every
  // current caller happens to pass an already-lowercased string, so
  // omitting this works today and fails silently for whoever adds the
  // next one: matching would just quietly become case-sensitive, with
  // no error and no obviously-wrong result to notice.
  q = String(q).toLowerCase();
  const fields = mode.searchFields
    ? mode.searchFields(row)
    : [mode.memberLabel ? mode.memberLabel(row) : (mode.linkLabel ? mode.linkLabel(row) : row.title)];
  return fields.some(v =>
    v != null && String(v).toLowerCase().includes(q));
}
window.modeRowMatches = modeRowMatches;

const PROJECT_MEMBER_MODES = MODES.filter(m => m.memberKind);
window.PROJECT_MEMBER_MODES = PROJECT_MEMBER_MODES;
window.PROJECT_MEMBER_KINDS = PROJECT_MEMBER_MODES.map(m => m.memberKind);

// Timestamp formatter — every timestamp Corpus displays runs through
// here so they render in the viewer's local timezone regardless of
// how the source deposited them.
// Handles both:
//   * ISO with explicit TZ ("2025-05-27T09:06:16Z", "…+00:00")
//   * ISO with no TZ ("2025-10-10T00:00:00", "2026-07-30T17:31:21.811387")
//     — OpenAlex writes these; per their docs they're UTC, so we
//     assume UTC when no offset is present.
// Falls back to the raw string when parsing fails.
// Returns { local, tooltip } — `local` is the display string, `tooltip`
// is the raw source value (put on `title=` so users can see what came
// from the API before any conversion).
window.fmtTs = function fmtTs(raw, opts) {
  if (raw == null || raw === "") return { local: "", tooltip: "" };
  const s = String(raw).trim();
  // If no timezone marker (Z, +hh:mm, -hh:mm), assume UTC. Both
  // Crossref and OpenAlex deposit UTC per their API docs; a bare
  // "2026-07-30T17:31:21.811387" would otherwise get parsed as
  // browser-local by Date, silently shifting hours.
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s);
  const isoInput = hasTz ? s : s + "Z";
  const d = new Date(isoInput);
  if (isNaN(d.getTime())) return { local: s, tooltip: s };
  const showTime = !(opts && opts.dateOnly);
  // Date-only inputs (Crossref journal_issue_date like "2025-04") also
  // arrive here; skip time components for those or every issue reads
  // as midnight-local.
  const dateOnlyRaw = /^\d{4}(-\d{2}){0,2}$/.test(s);
  // shortGeneric renders the zone as its DST-agnostic name ("ET"
  // instead of EST/EDT, "PT" instead of PST/PDT). Otherwise a paper
  // deposited in January would show EST and one from July EDT — both
  // technically correct, visually inconsistent. Falls back to "short"
  // on locales / runtimes that don't support shortGeneric (rare in
  // Chrome/Safari 2022+ but conservative to guard).
  const zoneName = _supportsShortGeneric() ? "shortGeneric" : "short";
  const local = (showTime && !dateOnlyRaw)
    ? d.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
        timeZoneName: zoneName,
      })
    : d.toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: dateOnlyRaw && s.length < 8 ? undefined : "numeric",
      });
  return { local, tooltip: `Source (UTC): ${s}` };
};
// Convenience — most callers just want the local string with the
// source-time tooltip pre-attached, wrapped in a span.
window.tsSpan = function tsSpan(raw, opts) {
  const { local, tooltip } = window.fmtTs(raw, opts);
  if (!local) return "";
  return `<span class="ts" title="${escAttr(tooltip)}">${escHtml(local)}</span>`;
};

// ---------- Utilities ----------

const $ = (sel) => document.querySelector(sel);

/** Send a frontend error to server.log. Dev builds only.
 *
 *  Frontend exceptions left no trace anywhere: the pywebview window has
 *  no visible console, and a blank pop-out (2026-09-21) could only be
 *  diagnosed by inference from which API calls did NOT appear in the
 *  log. The route exists only in dev (python/dev_only/client_errors.py),
 *  and this checks dev_mode first, so a shipped build sends nothing. */
function _reportClientError(where, err) {
  try {
    if (!(state.config && state.config.dev_mode)) return;
    const payload = {
      where,
      message: String((err && err.message) || err || ""),
      stack: String((err && err.stack) || ""),
      url: String(location.href || ""),
    };
    fetch("/api/dev/client-error", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
  } catch (_) { /* reporting must never throw */ }
}
window.addEventListener("error", (e) => _reportClientError("error", (e && e.error) || (e && e.message)));
window.addEventListener("unhandledrejection", (e) => _reportClientError("promise", e && e.reason));

function toast(msg, kind) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (kind ? " " + kind : "");
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3500);
}

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok) {
    const err = new Error(body.description || body.error || `HTTP ${r.status}`);
    err.status = r.status;
    err.body = body;
    throw err;
  }
  return body;
}

// ---------- Config / boot ----------

async function loadConfig() {
  state.config = await api("/api/config");
  const path = state.config.corpus_dir || "";
  // Corpus path lives only in Settings now — no topbar readout.
  const hasCorpus = Boolean(path);
  $("#btn-add").disabled           = !hasCorpus;
  $("#btn-scan").disabled          = !hasCorpus;
  $("#filter").disabled            = !hasCorpus;
  const af = $("#author-filter");       if (af)  af.disabled  = !hasCorpus;
  const inf = $("#institution-filter"); if (inf) inf.disabled = !hasCorpus;
  const jf = $("#journal-filter");      if (jf)  jf.disabled  = !hasCorpus;
  // Dev-only bundle — loaded once on first successful config fetch that
  // reports dev_mode: true. Shipped builds return dev_mode: false, so
  // the bug reporter never mounts.
  if (state.config.dev_mode && !window._devOnlyLoaded) {
    window._devOnlyLoaded = true;
    _loadDevOnly();
  }
  return state.config;
}

function _loadDevOnly() {
  // Add stylesheets then scripts — scripts depend on styles being
  // present when they inject buttons.
  // Reveal dev-only tabs. They ship hidden in index.html; this is the
  // only place that un-hides them, and it runs only when /api/config
  // reports dev_mode.
  document.querySelectorAll(".tabs .tab[data-dev-only]").forEach(t => { t.hidden = false; });

  ["/dev_only/bug-reporter.css", "/dev_only/tooltip-editor.css", "/dev_only/planning.css",
   "/dev_only/testing.css", "/dev_only/graph.css"].forEach(href => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = href;
    document.head.appendChild(css);
  });

  // html2canvas is a bulky (~200KB) UMD lib. Load it first so
  // bug-reporter.js can rely on window.html2canvas being defined.
  const h2c = document.createElement("script");
  h2c.src = "/dev_only/html2canvas.min.js";
  h2c.onload = () => {
    // `async = false` on a DYNAMICALLY created script is what preserves
    // execution order — without it the browser runs whichever downloads
    // first, and bug-reporter.js can start before the geometry helper it
    // calls on every pointer move exists.
    ["/dev_only/draw-geometry.js", "/dev_only/bug-reporter.js",
     "/dev_only/tooltip-editor.js", "/dev_only/planning.js",
     "/dev_only/testing.js",
     // Graph tab: three.js, then its orbit controls (which attach to
     // THREE), then the model, then the view that uses all three.
     "/dev_only/vendor/three.min.js", "/dev_only/vendor/OrbitControls.js",
     "/dev_only/graph-model.js", "/dev_only/graph.js"].forEach(src => {
      const s = document.createElement("script");
      s.src = src;
      s.async = false;
      document.head.appendChild(s);
    });
  };
  document.head.appendChild(h2c);
}
// Expose state for the tooltip editor to refresh after save.
window.state = state;

// Detached-window boot. Corpus opens a paper's PDF in a separate browser
// window at the same URL with `#detached=<slug>[&noteMode=1]`. Detected
// here so we can strip the chrome and mount just the paper detail —
// user gets a maximized PDF-only window with the full in-viewer
// toolbar (Highlight, show, Note Mode).
// A detached window is identified by "<kind>:<id>" — "paper:schunn-2001"
// or "note:1789...". Everything downstream (the Map key, the pywebview
// bridge, the close-notify event) treats that string as OPAQUE, which
// is why generalising from a bare paper slug touched almost nothing:
// launcher.py only ever uses it as a dict key.
//
// A hash with no colon is read as a paper, so windows popped out by an
// older build keep working.
const DETACH_KINDS = ["paper", "note", "document"];

function detachKey(kind, id) { return `${kind}:${id}`; }

/** The note window whose PDF panel is showing this paper / document, or
 *  null. Panel claims are "<kind>:<id>" keys since documents could open
 *  in the panel too (2026-09-25) — the same keys pop-out windows use. */
function _panelHolderOf(kind, id) {
  const key = detachKey(kind, id);
  for (const [noteKey, k] of state.panelPapers) if (k === key) return noteKey;
  return null;
}

/** "paper" / "note" / "document" — what the placeholder calls the thing. */
function _detachNoun(kind) {
  return kind === "note" ? "note" : kind === "document" ? "document" : "paper";
}

/** Is this paper/note being edited in another window?
 *
 *  For a paper that means popped out on its own OR showing in a note
 *  window's PDF panel — both are editors, since highlights save from
 *  either. */
function isDetachedElsewhere(kind, id) {
  if (kind !== "note" && _panelHolderOf(kind, id)) return true;
  const w = state.detachedWindows.get(detachKey(kind, id));
  return !!(w && (w === true || !w.closed));
}

/** The "open in a separate window" panel, for papers and notes alike.
 *
 *  A note could be open in a pop-out and the main window at once, so two
 *  editors autosaved over each other (2026-09-21). Papers had this placeholder; notes never did, so a popped-out note
 *  stayed editable in the main window and the two autosaves overwrote
 *  each other. One builder now serves both.
 *
 *  The buttons carry the full `<kind>:<id>` key. The paper version used
 *  to send the bare slug to `focus_detached` / `close_detached`, but
 *  launcher.py registers windows under the full key — so under pywebview
 *  "Bring to front" and "Close that window" silently did nothing. */
function detachedPlaceholderHtml(kind, id) {
  // Held by a note window's panel: point at THAT window. Offer no Close —
  // closing it would close the note too, which is not what the button
  // would appear to do.
  const holder = kind !== "note" ? _panelHolderOf(kind, id) : null;
  if (holder) {
    return `
    <div class="pd-detached-full">
      <div class="pdf-detached-placeholder">
        <p>This ${_detachNoun(kind)} is open in a note's PDF panel.</p>
        <div class="pdf-detached-actions">
          <button class="btn primary" data-detach-focus="${escAttr(holder)}">Bring to front</button>
        </div>
      </div>
    </div>`;
  }
  const key = detachKey(kind, id);
  const noun = _detachNoun(kind);
  return `
    <div class="pd-detached-full">
      <div class="pdf-detached-placeholder">
        <p>This ${noun} is open in a separate window.</p>
        <div class="pdf-detached-actions">
          <button class="btn primary" data-detach-focus="${escAttr(key)}">Bring to front</button>
          <button class="btn" data-detach-close="${escAttr(key)}">Close that window</button>
        </div>
      </div>
    </div>`;
}

// launcher.py tells the main window whenever a note panel claims or
// releases a paper. Re-render the paper pane if it is showing either one.
window.addEventListener("corpus-panel-paper", (e) => {
  const d = (e && e.detail) || {};
  if (!d.note) return;
  // `slug` carries the claimed "<kind>:<id>" key (launcher field name kept).
  const before = state.panelPapers.get(d.note) || null;
  if (d.slug) state.panelPapers.set(d.note, d.slug);
  else state.panelPapers.delete(d.note);
  for (const key of [before, d.slug]) {
    if (!key) continue;
    const i = key.indexOf(":");
    _afterDetachChange(key.slice(0, i), key.slice(i + 1));
  }
});

// One delegated handler for every placeholder's buttons.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest && e.target.closest("[data-detach-focus],[data-detach-close]");
  if (!btn) return;
  const focus = btn.hasAttribute("data-detach-focus");
  const key = btn.getAttribute(focus ? "data-detach-focus" : "data-detach-close");
  // Written out as `window.pywebview.api.<method>` on purpose:
  // tests/test_bridge_contract.py finds bridge calls by that literal
  // form, and an aliased `bridge.x()` call is invisible to it.
  if (_hasPywebviewBridge()) {
    try {
      if (focus) await window.pywebview.api.focus_detached(key);
      else       await window.pywebview.api.close_detached(key);
    } catch (_) {}
    return;
  }
  const w = state.detachedWindows.get(key);
  if (w && w !== true && !w.closed) (focus ? w.focus() : w.close());
});

function _readDetachedHash() {
  const raw = (location.hash || "").replace(/^#/, "");
  const p = new URLSearchParams(raw);
  const val = p.get("detached") || "";
  if (!val) return { kind: null, id: null, noteMode: p.get("noteMode") === "1" };
  const i = val.indexOf(":");
  const kind = i === -1 ? "paper" : val.slice(0, i);
  const id   = i === -1 ? val     : val.slice(i + 1);
  const at = parseInt(p.get("at") || "", 10);
  return {
    kind: DETACH_KINDS.includes(kind) ? kind : "paper",
    id: id || null,
    noteMode: p.get("noteMode") === "1",
    // Where a popped-out note should open scrolled to, or null.
    place: at >= 0 ? { i: at, f: parseFloat(p.get("atf")) || 0 } : null,
  };
}

async function boot() {
  const detached = _readDetachedHash();
  if (detached.id) {
    document.body.classList.add("corpus-detached");
    document.body.classList.add(`corpus-detached-${detached.kind}`);
    state.detached = detached;
    if (detached.kind === "paper" || detached.kind === "document") {
      state.noteMode = detached.noteMode;
      state.paperSubtab = "pdf";
    }
  }
  await loadConfig();
  // Load user tooltip overrides (returns {} if none saved).
  try { state.tooltips = await api("/api/tooltips"); } catch (_) { state.tooltips = {}; }
  // Topbar buttons live in index.html so aren't touched by the per-
  // paper renderers. Set their tooltip attrs on boot after tooltips
  // have loaded so overrides apply.
  const topbarTips = {
    "btn-add":      "btn.add_pdfs",
    "btn-scan":     "btn.scan",
    "btn-settings": "btn.settings",
  };
  for (const [id, key] of Object.entries(topbarTips)) {
    const b = document.getElementById(id);
    if (b) b.title = tt(key);
  }
  if (state.config.corpus_dir) {
    // Name the corpus BEFORE the slow read, so the very first thing on
    // screen is the folder we are actually using.
    showEmptyState("loading");
    if (detached.id) {
      // Detached window: render exactly one thing. Skip the sidebar
      // list load entirely.
      hideEmptyState();
      if (detached.kind === "note") {
        // Note FIRST. The papers list only supplies titles for the PDF
        // panel's header, and the panel already falls back to the slug.
        //
        // This used to `await loadPapers()` before fetching the note. On
        // 2026-09-21, after a restart, a cold /api/papers over ~620
        // summaries took 251s — and the popped-out note sat completely
        // blank for all of it.
        loadPapers().catch(() => {});
        // Titles for documents a note links to, for the same panel header.
        loadDocuments().catch(() => {});
        await openDetachedNote(detached.id);
      } else if (detached.kind === "document") {
        // The documents tab is the live PDF pane in this window: its
        // viewer drives the note gutter (see _pdfPaneRoot).
        state.mode = "documents";
        await loadDocuments();
        selectDocument(detached.id);
      } else {
        await selectPaper(detached.id);
      }
    } else {
      await loadPapers();
      // Only hide the empty state if there is actually something to
      // show. An empty corpus keeps it up, with the path named.
      if (state.papers.length) hideEmptyState();
      else showEmptyState("empty-corpus");
    }
  } else {
    showEmptyState("no-corpus");
  }
}

// Is the app running under pywebview (shipped desktop shell) vs a
// browser tab (dev mode via Flask)? The bridge exposes multi-window
// helpers only in the pywebview case; browser mode uses window.open.
function _hasPywebviewBridge() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.open_detached);
}

// Open the given paper's PDF in a separate window. Under pywebview
// this is a real native window managed by the Python bridge; under a
// browser it's window.open. Either way, main-window state tracks the
// slug so the paper detail can swap in the "open elsewhere" placeholder.
async function openDetached(kind, id) {
  // Land any pending autosave BEFORE the new window reads the note. The
  // pop-out fetches immediately; without this, the last ~800ms of typing
  // in the main window saves after the pop-out has loaded, and the
  // pop-out's next save writes over it.
  if (kind === "note" && typeof flushNoteSave === "function") {
    try { await flushNoteSave(); } catch (_) {}
  }
  const key = detachKey(kind, id);
  const existing = state.detachedWindows.get(key);
  const nm  = state.noteMode ? "1" : "0";
  // A note opens where the user was reading it (notes.js::noteScrollAnchor).
  const place = (kind === "note" && state.selectedNoteId === id)
    ? noteScrollAnchor(document.getElementById("note-body")) : null;
  const at = place ? `&at=${place.i}&atf=${place.f}` : "";
  const url = `${location.origin}${location.pathname}#detached=${encodeURIComponent(key)}&noteMode=${nm}${at}`;
  const title = kind === "note" ? `Corpus — note` : `Corpus — ${id}`;

  if (_hasPywebviewBridge()) {
    // pywebview: existing entries mean the Python side has a Window
    // ref. Ask it to focus rather than opening a duplicate.
    if (existing) {
      try { await window.pywebview.api.focus_detached(key); } catch (_) {}
      return;
    }
    let res;
    try {
      res = await window.pywebview.api.open_detached(key, url, title);
    } catch (e) {
      toast("failed to open window: " + e.message, "err");
      return;
    }
    if (res === "error") {
      toast("failed to open window", "err");
      return;
    }
    if (res === "busy") {
      // Already being edited in a note window's panel — send the user
      // there rather than opening a second editor.
      const holder = kind !== "note" ? _panelHolderOf(kind, id) : null;
      toast("already open in a note's PDF panel");
      if (holder) { try { await window.pywebview.api.focus_detached(holder); } catch (_) {} }
      return;
    }
    // Placeholder ref — real Window lives Python-side. Close is
    // notified via the `corpus-detached-closed` event listener below.
    state.detachedWindows.set(key, true);
    _afterDetachChange(kind, id);
    return;
  }

  // Browser dev-mode fallback.
  if (existing && existing.focus && !existing.closed) { existing.focus(); return; }
  const win = window.open(url, `corpus-${key}`, "width=1400,height=900");
  if (!win) { toast("popup blocked — allow popups for Corpus", "err"); return; }
  state.detachedWindows.set(key, win);
  _watchDetachedWindow(key, win);
  _afterDetachChange(kind, id);
}

// Boot path for a popped-out NOTE. Renders the note editor into the
// workspace's left pane instead of the docked #note-detail, so the
// split layout owns the window.
async function openDetachedNote(id) {
  const ws = document.getElementById("note-workspace");
  const host = document.getElementById("nw-note");
  if (!ws || !host) return;
  ws.hidden = false;
  document.getElementById("note-detail").hidden = true;
  state.selectedNoteId = id;
  try {
    state.noteDetail = await api(`/api/note/${encodeURIComponent(id)}`);
  } catch (e) {
    host.innerHTML = `<p class="err">failed to load note: ${escHtml(e.message)}</p>`;
    return;
  }
  renderNoteDetail(host);
  // After layout, so block positions are real.
  const place = state.detached && state.detached.place;
  if (place) requestAnimationFrame(() =>
    restoreNoteScrollAnchor(document.getElementById("note-body"), place));
  document.getElementById("nw-panel-close")
    .addEventListener("click", () => NoteWorkspace.closePanel());
}

// Re-render whichever pane is showing the thing that just popped out,
// so it can swap in its "open elsewhere" placeholder.
function _afterDetachChange(kind, id) {
  if (kind === "paper" && state.mode === "papers" && state.selectedSlug === id) renderDetail();
  if (kind === "note" && state.mode === "notes" && state.selectedNoteId === id) {
    // Locking can draw from memory. UNLOCKING must reload from disk: the
    // note was edited in the other window meanwhile, and the copy in
    // `state.noteDetail` is from before it popped out. Re-showing that
    // copy is how pop-out edits were overwritten on 2026-09-28 —
    // the next autosave here sent the 30-minute-old text back.
    if (isDetachedElsewhere("note", id)) renderNoteDetail();
    else selectNote(id);
  }
  if (kind === "document" && state.mode === "documents" && state.selectedDocId === id) {
    renderDocumentDetail({ force: true });
  }
}

// pywebview close-notify: launcher.py's bridge fires this custom event
// on the main window when a popped-out window's `closed` handler runs.
// Browser mode doesn't use this — see `_watchDetachedWindow` below.
window.addEventListener("corpus-detached-closed", (e) => {
  // launcher.py still names the field `slug`; it carries the opaque
  // "<kind>:<id>" key. Renaming it would need a matching launcher
  // change for no behavioural gain.
  const key = (e && e.detail && e.detail.slug) || null;
  if (!key) return;
  state.detachedWindows.delete(key);
  const i = key.indexOf(":");
  _afterDetachChange(i === -1 ? "paper" : key.slice(0, i),
                     i === -1 ? key : key.slice(i + 1));
});

// Poll a detached window for close (~700ms). Browser-mode only —
// pywebview uses the event above.
function _watchDetachedWindow(key, win) {
  const timer = setInterval(() => {
    if (!win.closed) return;
    clearInterval(timer);
    state.detachedWindows.delete(key);
    // Same path as the pywebview close event, so notes un-lock too. This
    // used to compare the full key against `selectedSlug` and so never
    // re-rendered anything.
    const i = key.indexOf(":");
    _afterDetachChange(i === -1 ? "paper" : key.slice(0, i),
                       i === -1 ? key : key.slice(i + 1));
  }, 700);
}

// ---------- Papers list ----------

async function loadPapers() {
  try {
    state.papers = await api(MODES_BY_ID.papers.listUrl);
    renderPapers();
  } catch (e) {
    if (e.status === 400 && String(e.body?.description || "").includes("corpus_not_set")) {
      showEmptyState();
      return;
    }
    toast("failed to load papers: " + e.message, "err");
  }
}

function renderPapers() {
  const list = $("#papers-list");
  const f = state.filter.trim().toLowerCase();
  const filtered = f
    ? state.papers.filter(p => modeRowMatches(MODES_BY_ID.papers, p, f))
    : state.papers;
  const sorted = Sorting.sortRows(MODES_BY_ID.papers.sorts, filtered,
                                  state.papersSort.field, state.papersSort.dir);
  list.innerHTML = sorted.map(p => `
    <li data-slug="${escAttr(p.slug)}" ${p.slug === state.selectedSlug ? 'class="selected"' : ""}${p.needs_doi ? ' data-no-doi="true"' : ""}>
      <div class="p-title">${escHtml(p.title)}${p.needs_doi ? ' <span class="p-no-doi">no DOI</span>' : ""}</div>
      <div class="p-meta">${escHtml(p.author)} · ${escHtml(String(p.year))}${
        p.publisher && p.publisher !== "unknown"
          ? " · <em>" + escHtml(p.publisher) + "</em>"
          : ""
      }</div>
    </li>
  `).join("");
  $("#count-line").textContent = state.papers.length === filtered.length
    ? `${state.papers.length} paper${state.papers.length === 1 ? "" : "s"}`
    : `${filtered.length} of ${state.papers.length} shown`;
}

function selectPaper(slug) {
  state.selectedSlug = slug;
  // Keep whatever subtab the user was last on: when
  // arrow-keying through papers, staying on PDF is expected. If the
  // next paper has no PDF, the render code falls back to info
  // automatically (activePdf becomes "" when hasPdf is false).
  renderPapers();
  loadPaperDetail(slug);
}

// ---------- Tab switcher ----------

function switchMode(id) {
  if (id === state.mode) return;
  const m = MODES_BY_ID[id];
  if (!m) return;
  state.mode = id;

  // Highlight the active tab button.
  document.querySelectorAll(".tabs .tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === id));

  // Show/hide sidebar + detail for every mode in one loop.
  for (const other of MODES) {
    const active = (other.id === id);
    $("#" + other.filterId).hidden = !active;
    $("#" + other.listId).hidden   = !active;
    $("#" + other.detailId).hidden = !active;
  }
  // Sort strip is Papers-only for now (will port to other modes per
  // the other modes once the pattern is settled).
  const sortWrap = $("#papers-sort-wrap");
  if (sortWrap) sortWrap.hidden = (id !== "papers");

  // Top-right action buttons, MODES-driven. A mode that declares
  // `actionBtnId` owns the action slot: its button shows and the
  // corpus-wide Add/Scan pair hides. This used to be a hard-coded
  // `isNotes` check; Projects would have made it a second one, which
  // is how the four hard-coded deep-link branches happened before they
  // were consolidated on 2026-08-27. Pinned by
  // tests/test_mode_action_buttons.py.
  const activeActionBtn = m.actionBtnId || null;
  const addBtn = $("#btn-add"), scanBtn = $("#btn-scan");
  if (addBtn)  addBtn.hidden  = Boolean(activeActionBtn);
  if (scanBtn) scanBtn.hidden = Boolean(activeActionBtn);
  for (const other of MODES) {
    if (!other.actionBtnId) continue;
    const btn = $("#" + other.actionBtnId);
    if (btn) btn.hidden = (other.actionBtnId !== activeActionBtn);
  }

  _recordPlace();

  // Load / render the list per the mode's loadPolicy.
  const corpusReady = Boolean(state.config?.corpus_dir);
  const listIsEmpty = state[m.stateKey].length === 0;
  if (m.loadPolicy === "always" && corpusReady) {
    m.load();
  } else if (m.loadPolicy === "lazy" && listIsEmpty && corpusReady) {
    m.load();
  } else {
    m.render();  // eager (papers) always re-renders; lazy re-renders once loaded
  }

  // Detail pane: render current selection, or fall back to the mode's
  // optional empty-state HTML (only Notes today).
  if (state[m.selectedKey]) {
    m.renderDetail();
  } else if (m.emptyStateHtml && listIsEmpty) {
    $("#" + m.detailId).innerHTML = m.emptyStateHtml();
  }
}

// ---------- Authors list ----------

async function loadAuthors() {
  try {
    state.authors = await api(MODES_BY_ID.authors.listUrl);
    renderAuthors();
  } catch (e) {
    if (e.status === 400) return;
    toast("failed to load authors: " + e.message, "err");
  }
}

function renderAuthors() {
  const list = $("#authors-list");
  const f = state.authorFilter.trim().toLowerCase();
  const filtered = f
    ? state.authors.filter(a => modeRowMatches(MODES_BY_ID.authors, a, f))
    : state.authors;
  list.innerHTML = filtered.map(a => {
    const displayName = a.given ? `${a.family}, ${a.given}` : a.family;
    const affil = a.primary_institution ? escHtml(a.primary_institution) : "";
    return `
      <li data-key="${escAttr(a.key)}" ${a.key === state.selectedAuthorKey ? 'class="selected"' : ""}>
        <div class="p-title">${escHtml(displayName)}</div>
        <div class="p-meta">${a.num_papers} paper${a.num_papers === 1 ? "" : "s"}${
          affil ? ' · <em>' + affil + '</em>' : ""
        }${
          typeof a.h_index === "number" ? ` · h-index ${a.h_index}` : ""
        }</div>
      </li>
    `;
  }).join("");
  $("#count-line").textContent = state.authors.length === filtered.length
    ? `${state.authors.length} author${state.authors.length === 1 ? "" : "s"}`
    : `${filtered.length} of ${state.authors.length} shown`;
}

function selectAuthor(key) {
  state.selectedAuthorKey = key;
  renderAuthors();
  loadAuthorDetail(key);
}

// ---------- Author detail ----------
// Moved to author-detail.js. See index.html <script> ordering.

// ---------- Institutions list ----------

async function loadInstitutions() {
  try {
    state.institutions = await api(MODES_BY_ID.institutions.listUrl);
    renderInstitutions();
  } catch (e) {
    if (e.status === 400) return;
    toast("failed to load institutions: " + e.message, "err");
  }
}

function renderInstitutions() {
  const list = $("#institutions-list");
  const f = state.institutionFilter.trim().toLowerCase();
  const filtered = f
    ? state.institutions.filter(i => modeRowMatches(MODES_BY_ID.institutions, i, f))
    : state.institutions;
  list.innerHTML = filtered.map(i => {
    const bits = [];
    if (i.num_papers)  bits.push(`${i.num_papers} paper${i.num_papers === 1 ? "" : "s"}`);
    if (i.num_authors) bits.push(`${i.num_authors} author${i.num_authors === 1 ? "" : "s"}`);
    if (i.country_code) bits.push(escHtml(Countries.name(i.country_code)));
    if (i.type)         bits.push(`<em>${escHtml(i.type)}</em>`);
    return `
      <li data-key="${escAttr(i.key)}" ${i.key === state.selectedInstitutionKey ? 'class="selected"' : ""}>
        <div class="p-title">${escHtml(i.name)}</div>
        <div class="p-meta">${bits.join(" · ")}</div>
      </li>
    `;
  }).join("");
  $("#count-line").textContent = state.institutions.length === filtered.length
    ? `${state.institutions.length} institution${state.institutions.length === 1 ? "" : "s"}`
    : `${filtered.length} of ${state.institutions.length} shown`;
}

function selectInstitution(key) {
  state.selectedInstitutionKey = key;
  renderInstitutions();
  loadInstitutionDetail(key);
}

// ---------- Institution detail ----------
// Moved to institution-detail.js. See index.html <script> ordering.

function _relativeTime(iso) {
  try {
    const then = new Date(iso).getTime();
    const secs = Math.round((Date.now() - then) / 1000);
    if (secs < 60)          return "just now";
    if (secs < 3600)        return `${Math.round(secs / 60)} min ago`;
    if (secs < 86400)       return `${Math.round(secs / 3600)} hr ago`;
    if (secs < 86400 * 30)  return `${Math.round(secs / 86400)} days ago`;
    return `${Math.round(secs / (86400 * 30))} mo ago`;
  } catch (_) { return "unknown"; }
}

// ---------- Journals list ----------

async function loadJournals() {
  try {
    state.journals = await api(MODES_BY_ID.journals.listUrl);
    renderJournals();
  } catch (e) {
    if (e.status === 400) return;
    toast("failed to load journals: " + e.message, "err");
  }
}

function renderJournals() {
  const list = $("#journals-list");
  const f = state.journalFilter.trim().toLowerCase();
  const filtered = f
    ? state.journals.filter(j => modeRowMatches(MODES_BY_ID.journals, j, f))
    : state.journals;
  list.innerHTML = filtered.map(j => {
    const bits = [];
    if (j.num_papers)         bits.push(`${j.num_papers} paper${j.num_papers === 1 ? "" : "s"}`);
    if (j.year_range)         bits.push(escHtml(j.year_range));
    if (j.host_organization)  bits.push(`<em>${escHtml(j.host_organization)}</em>`);
    if (j.venue_type)         bits.push(escHtml(j.venue_type));
    return `
      <li data-key="${escAttr(j.key)}" ${j.key === state.selectedJournalKey ? 'class="selected"' : ""}>
        <div class="p-title">${escHtml(j.name)}</div>
        <div class="p-meta">${bits.join(" · ")}</div>
      </li>
    `;
  }).join("");
  $("#count-line").textContent = state.journals.length === filtered.length
    ? `${state.journals.length} journal${state.journals.length === 1 ? "" : "s"}`
    : `${filtered.length} of ${state.journals.length} shown`;
}

function selectJournal(key) {
  state.selectedJournalKey = key;
  renderJournals();
  loadJournalDetail(key);
}

// ---------- Journal detail ----------
// Moved to journal-detail.js. See index.html <script> ordering.

// ---------- Notes ----------
// Moved to notes.js. See index.html <script> ordering.


// ---------- Paper detail ----------
// Moved to paper-detail.js. See index.html <script> ordering.

// ---------- Empty state ----------

// Two reasons the main pane can be empty, and they need different
// words. `reason: "no-corpus"` is the first-run case. `"empty-corpus"`
// is a corpus that IS set but holds no papers — previously that
// rendered NOTHING (loadPapers succeeded with [], then hideEmptyState
// ran), so pointing at the wrong folder looked exactly like a working
// app with no content. Naming the path is what makes a mis-point
// obvious at a glance.
function showEmptyState(reason = "no-corpus") {
  const title = $("#empty-state-title");
  const body  = $("#empty-state-body");
  const path  = $("#empty-state-path");
  const btn   = $("#empty-choose-dir");

  // Three reasons now, not two. "loading" exists because the first two
  // are CONCLUSIONS and boot cannot reach either until it has read the
  // corpus — which on a cold 209-summary corpus measured ~20s
  // (5.4 MB, ~95ms per file on first access). Until 2026-09-20 the
  // pane simply started on the no-corpus copy, so for those 20 seconds
  // Corpus told a user with a perfectly good corpus to "pick a corpus
  // directory". That read as the app forgetting the corpus, which
  // is exactly what it said.
  if (reason === "loading") {
    const dir = (state.config && state.config.corpus_dir) || "";
    title.textContent = "Loading…";
    body.textContent  = dir ? "Reading summaries from the folder below."
                            : "Reading your corpus.";
    path.textContent  = dir;
    path.hidden       = !dir;
    // No button: there is nothing to decide yet, and offering "choose a
    // folder" mid-load is what made this look like a lost setting.
    btn.hidden        = true;
    $("#empty-state").hidden = false;
    return;
  }
  btn.hidden = false;

  if (reason === "empty-corpus") {
    const dir = (state.config && state.config.corpus_dir) || "";
    title.textContent = "No papers in this corpus";
    body.textContent  = "Corpus is reading from the folder below and found no " +
                        "summaries in it. If that is not the folder you meant, " +
                        "pick another one. Otherwise use Add PDFs… to get started.";
    path.textContent  = dir;
    path.hidden       = !dir;
    btn.textContent   = "Choose a different folder…";
  } else {
    title.textContent = "Welcome to Corpus";
    body.textContent  = "Pick a corpus directory to get started. Corpus will " +
                        "store your extracted summaries next to your PDFs.";
    path.hidden       = true;
    btn.textContent   = "Choose corpus directory…";
  }

  $("#empty-state").hidden = false;
  $("#paper-detail").hidden = true;
}
function hideEmptyState() {
  $("#empty-state").hidden = true;
}

// ---------- Add / scan ----------

async function addPdfs(files) {
  if (!files || !files.length) return;
  const form = new FormData();
  for (const f of files) form.append("files", f);
  toast(`extracting ${files.length} file(s)…`);
  Progress.watch(() => loadPapers());
  try {
    const res = await api("/api/extract", { method: "POST", body: form });
    const ok = res.results.filter(r => r.status === "extracted").length;
    const skipped = res.results.filter(r => r.status === "exists").length;
    const failed = res.results.filter(r => r.status === "failed").length;
    const parts = [];
    if (ok)      parts.push(`${ok} extracted`);
    if (skipped) parts.push(`${skipped} already existed`);
    if (failed)  parts.push(`${failed} failed`);
    toast(parts.join(", ") || "no changes", failed ? "err" : "ok");
    await loadPapers();
  } catch (e) {
    // 409 = an import is already running (the server refuses a second
    // one; two at once raced over the same inbox and made the progress
    // total alternate between their two file counts). Not a failure —
    // say what is happening and leave the watch showing that job.
    if (e.status === 409) toast(e.message);
    else toast("extract failed: " + e.message, "err");
  }
}

async function rescan() {
  toast("scanning corpus…");
  // Watch BEFORE awaiting: /api/scan holds its request for the whole
  // import, and the bridge search keeps running after it returns, so
  // the poll is the only thing that can report either.
  Progress.watch(() => loadPapers());
  try {
    const res = await api("/api/scan", { method: "POST" });
    const inbox = (res.inbox_processed || []).filter(r => r.status === "extracted").length;
    const back  = (res.extracted || []).length;
    const total = inbox + back;
    const parts = [];
    if (inbox) parts.push(`${inbox} from inbox`);
    if (back)  parts.push(`${back} backfilled`);
    toast(total ? `extracted ${total} new paper(s) (${parts.join(", ")})`
                : "nothing new to extract", "ok");
    if (total) await loadPapers();
  } catch (e) {
    if (e.status === 409) toast(e.message);
    else toast("scan failed: " + e.message, "err");
  }
}

// ---------- Settings modal ----------

function openSettings() {
  const modal = $("#settings-modal");
  const cfg   = state.config || {};
  $("#cfg-corpus-dir").value = cfg.corpus_dir || "";
  $("#cfg-mailto").value     = cfg.mailto     || "";
  $("#cfg-s2-key").value = "";
  $("#cfg-oa-key").value = "";
  const s2 = cfg.keys?.semantic_scholar_key ? "✓ set" : "not set";
  const oa = cfg.keys?.openalex_key ? "✓ set" : "not set";
  $("#s2-status").textContent = s2;
  $("#s2-status").className = "status" + (cfg.keys?.semantic_scholar_key ? " set" : "");
  $("#oa-status").textContent = oa;
  $("#oa-status").className = "status" + (cfg.keys?.openalex_key ? " set" : "");
  modal.hidden = false;
}
function closeSettings() { $("#settings-modal").hidden = true; }

async function saveSettings() {
  const payload = {
    corpus_dir: $("#cfg-corpus-dir").value.trim(),
    mailto:     $("#cfg-mailto").value.trim(),
    keys: {},
  };
  // Only send key fields the user actually typed into.
  const s2 = $("#cfg-s2-key").value;
  const oa = $("#cfg-oa-key").value;
  if (s2) payload.keys.semantic_scholar_key = s2.trim();
  if (oa) payload.keys.openalex_key = oa.trim();
  try {
    await api("/api/config", {
      method:  "POST",
      headers: { "content-type": "application/json" },
      body:    JSON.stringify(payload),
    });
    toast("settings saved", "ok");
    closeSettings();
    await boot();  // reload everything with new config
  } catch (e) {
    toast("save failed: " + e.message, "err");
  }
}

async function pickCorpusDir() {
  // Try the native picker (only works under pywebview).
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
      const p = await window.pywebview.api.pick_folder();
      if (p) $("#cfg-corpus-dir").value = p;
      return;
    }
  } catch (_) { /* fall through */ }
  // Server-side fallback (also returns 501 in browser mode).
  try {
    const r = await api("/api/pick-corpus", { method: "POST" });
    if (r.path) $("#cfg-corpus-dir").value = r.path;
  } catch (_) {
    toast("native picker unavailable — paste the path into the text field", "err");
  }
}

// ---------- Escape helpers ----------

function escHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escAttr(s) {
  return escHtml(s).replace(/"/g, "&quot;");
}

// ---------- Wire events ----------

$("#btn-add").addEventListener("click", () => $("#pdf-picker").click());
$("#pdf-picker").addEventListener("change", (e) => {
  addPdfs(Array.from(e.target.files || []));
  e.target.value = "";  // reset so the same file can be picked again
});
$("#btn-scan").addEventListener("click", rescan);

$("#btn-settings").addEventListener("click", openSettings);
$("#settings-close").addEventListener("click", closeSettings);
$("#settings-cancel").addEventListener("click", closeSettings);
$("#settings-save").addEventListener("click", saveSettings);
$("#cfg-browse").addEventListener("click", pickCorpusDir);
$("#cfg-default").addEventListener("click", () => {
  // Frontend can't resolve ~, but the server expands it before saving.
  $("#cfg-corpus-dir").value = "~/Documents/Corpus";
});
$("#empty-choose-dir").addEventListener("click", openSettings);

// Per-mode filter input + list click delegator — one loop over MODES
// replaces 5 near-identical blocks per event. Adding a new mode = one
// MODES entry, zero changes here.
for (const m of MODES) {
  const filterEl = document.getElementById(m.filterId);
  if (filterEl) {
    // Name the searchable fields in the placeholder. The bug that
    // prompted this ("should be able to search by author here as
    // well") was partly a discoverability failure: a box saying only
    // "Filter papers…" gives no clue whether author counts. Driven
    // from the mode's `searchHint`, which sits beside `searchFields`,
    // so the promise and the behaviour are edited together. Modes
    // without one keep whatever index.html declares.
    if (m.searchHint) filterEl.placeholder = `Filter by ${m.searchHint}…`;
    filterEl.addEventListener("input", (e) => {
      state[m.filterKey] = e.target.value;
      m.render();
    });
  }
  const listEl = document.getElementById(m.listId);
  if (listEl) {
    listEl.addEventListener("click", (e) => {
      const li = e.target.closest(`li[${m.dataAttr}]`);
      if (!li) return;
      m.select(li.getAttribute(m.dataAttr));
    });
  }
}
$("#btn-new-note").addEventListener("click", createNote);
$("#btn-new-project").addEventListener("click", createProject);
$("#btn-back").addEventListener("click", goBack);
$("#btn-fwd").addEventListener("click", goForward);

// PDF Note Mode + highlight-notes bridge — postMessage between the
// PDF.js iframe (corpus-highlights.js) and this Corpus shell.
//
// Two message channels flow across the bridge:
//   * `source: "corpus-note-mode"`   — iframe → parent, Note Mode toggle
//   * `source: "corpus-highlights"`  — iframe → parent, current highlight
//                                       set (used to render gutter cards)
//   * `source: "corpus-shell"`       — parent → iframe, note-edit events
//
// Initial Note Mode state travels the OTHER way via the iframe URL hash
// (see paper-detail.js).
window.addEventListener("message", (e) => {
  const d = e.data;
  if (!d) return;
  // Every branch below writes into the PAPER pane (its note gutter, its
  // Note Mode class, its geometry cache), so only the paper pane's own
  // viewer may drive it.
  //
  // This used to accept a message from ANY frame. That was harmless
  // while one window held one viewer; the dev Testing tab (2026-09-21)
  // put a second viewer beside it, and `switchMode` only HIDES panes —
  // the paper pane's gutter stays in the DOM. A highlights message from
  // the test viewer would have repainted your open paper's anchored
  // notes with a different paper's, silently, until you clicked away.
  if (d.source === "corpus-note-mode" || d.source === "corpus-highlights") {
    const frame = _paperViewerFrame();
    if (!frame || e.source !== frame.contentWindow) return;
  }
  if (d.source === "corpus-note-mode") {
    state.noteMode = !!d.noteMode;
    const pdfPane = _pdfPaneRoot()?.querySelector(".pd-subpane-pdf");
    if (pdfPane) pdfPane.classList.toggle("note-mode", state.noteMode);
  } else if (d.source === "corpus-highlights" && d.type === "highlights") {
    if (d.viewer) _lastViewerGeom = d.viewer;
    _renderNoteGutter(d.highlights || [], { focusNoteId: d.focusNoteId });
    _syncGutterScroll();
  } else if (d.source === "corpus-highlights" && d.type === "scroll") {
    if (d.viewer) _lastViewerGeom = d.viewer;
    _syncGutterScroll();
  } else if (d.source === "corpus-highlights" && d.type === "focus-note") {
    _pingNoteCard(d.id);
  }
});

// Ping-on-click: scroll the note card into view + flash its border so
// the user can see which card is anchored to the highlight they just
// clicked. The .pinged class carries the CSS animation; we remove it
// after the animation duration so re-clicking the same highlight
// re-triggers cleanly. Called from the `focus-note` message branch.
function _pingNoteCard(id) {
  const card = _pdfPaneRoot()?.querySelector(
    `.pdf-note-card[data-note-id="${CSS.escape(id)}"]`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  card.classList.remove("pinged");
  // Force a reflow so re-adding the class restarts the animation even
  // if the class was still on the element from a fast double-click.
  void card.offsetWidth;
  card.classList.add("pinged");
  setTimeout(() => card.classList.remove("pinged"), 1000);
}

// Latest known geometry of the PDF viewer's scrollable container.
// Refreshed on every "highlights" and "scroll" message from the iframe.
// Cards live in an inner div sized to `contentHeight`; gutter scroll
// mirrors the iframe's scrollTop so cards line up with their anchors.
let _lastViewerGeom = { contentHeight: 0, scrollTop: 0, viewportHeight: 0 };

// Render the right-side gutter with one card per highlight that has an
// anchored note. Cards are positioned ABSOLUTELY at the anchor's y in
// the viewer content coord system by `_layoutCards`, which runs after
// the initial render AND on every card's ResizeObserver — so dragging
// a textarea taller cascades push-down through the cards below only if
// they'd otherwise collide, leaving non-colliding ones at their anchor.
const _noteSaveTimers = new Map();       // highlight id → timeout handle
const _CARD_GAP = 6;
let _cardResizeObserver = null;
let _layoutRAF = null;
function _renderNoteGutter(highlights, opts) {
  const gutter = _pdfPaneRoot()?.querySelector(".pdf-note-gutter");
  if (!gutter) return;
  // Observer teardown belongs to the paths that REPLACE nodes, not to
  // the top of the function. Disconnecting unconditionally would kill
  // resize-driven relayout on the in-place path below, which never
  // rebuilds and so never re-observes.
  const dropObserver = () => {
    if (_cardResizeObserver) { _cardResizeObserver.disconnect(); _cardResizeObserver = null; }
  };
  const withNotes = highlights.filter(h => typeof h.note === "string");
  if (!withNotes.length) {
    dropObserver();
    gutter.innerHTML = `
      <div class="pdf-note-gutter-empty">
        Anchored notes will appear here.<br>
        (Right-click a highlight in Note Mode to create one.)
      </div>`;
    // Clear the signature: the cards are gone, so the next render must
    // take the rebuild path even if the same note ids come back.
    delete gutter.dataset.noteSig;
    return;
  }
  // Sort by anchor y ascending — top of PDF → bottom. Missing absoluteY
  // (highlights on not-yet-rendered pages) go to the end; PDF.js will
  // send a follow-up "highlights" message once those pages render.
  withNotes.sort((a, b) => (a.absoluteY ?? Infinity) - (b.absoluteY ?? Infinity));

  // ---- Update in place when the SET of cards hasn't changed --------
  //
  // This function runs on every "highlights" message, and one of those
  // arrives ~1s after you stop typing: the card's 600ms input debounce
  // posts `update-note`, the iframe saves 200ms later, and its saveNow
  // wrapper notifies the parent. Rebuilding innerHTML at that moment
  // destroyed the textarea being typed in — losing focus and caret —
  // AND reset gutter.scrollTop to 0, which fired a scroll event that
  // the sync listener forwarded to the viewer as `set-scroll: 0`. The
  // PDF jumped to the top mid-sentence.
  //
  // So: only rebuild when the cards themselves change. Anything else
  // (a note's text round-tripping back from the server, anchors moving
  // as pages render) is applied to the existing nodes.
  const signature = withNotes.map(h => h.id).join("|");
  const existingInner = gutter.querySelector(".pdf-note-gutter-inner");
  if (existingInner && gutter.dataset.noteSig === signature) {
    for (const h of withNotes) {
      const card = existingInner.querySelector(
        `.pdf-note-card[data-note-id="${CSS.escape(h.id)}"]`);
      if (!card) continue;
      card.dataset.anchorY = (h.absoluteY ?? 0).toFixed(2);
      const anchor = card.querySelector(".pdf-note-card-anchor");
      if (anchor) {
        anchor.style.background = h.color || "#FFEB3B";
        anchor.title = (h.text || "").slice(0, 200);
      }
      const ta = card.querySelector(".pdf-note-card-text");
      // NEVER write into the textarea the user is typing in. Even
      // assigning an identical value moves the caret to the end.
      if (ta && ta !== document.activeElement && ta.value !== h.note) {
        ta.value = h.note;
      }
    }
    _scheduleLayout(gutter);
    if (opts && opts.focusNoteId) _focusNoteCard(existingInner, opts.focusNoteId);
    return;
  }

  // ---- Full rebuild (the card set really did change) ---------------
  // Preserve scroll across the rebuild for the same reason: innerHTML
  // replacement zeroes scrollTop, and the sync listener would forward
  // that to the viewer.
  dropObserver();
  const prevScroll = gutter.scrollTop;
  gutter.innerHTML = `<div class="pdf-note-gutter-inner"></div>`;
  gutter.dataset.noteSig = signature;
  const inner = gutter.querySelector(".pdf-note-gutter-inner");
  inner.innerHTML = withNotes.map(h => `
    <div class="pdf-note-card" data-note-id="${escAttr(h.id)}"
         data-anchor-y="${(h.absoluteY ?? 0).toFixed(2)}">
      <div class="pdf-note-card-anchor"
           style="background:${escAttr(h.color || "#FFEB3B")}"
           title="${escAttr((h.text || "").slice(0, 200))}"></div>
      <textarea class="pdf-note-card-text"
                data-note-id="${escAttr(h.id)}"
                placeholder="Note…">${escHtml(h.note)}</textarea>
    </div>
  `).join("");
  // Wire textareas + observe each card for resize.
  _cardResizeObserver = new ResizeObserver(() => _scheduleLayout(gutter));
  inner.querySelectorAll(".pdf-note-card").forEach(card => {
    _cardResizeObserver.observe(card);
    const ta = card.querySelector(".pdf-note-card-text");
    if (ta) {
      ta.addEventListener("input", (e) => {
        const id = e.target.dataset.noteId;
        const val = e.target.value;
        if (_noteSaveTimers.has(id)) clearTimeout(_noteSaveTimers.get(id));
        _noteSaveTimers.set(id, setTimeout(() => {
          _noteSaveTimers.delete(id);
          _postToViewer({ type: "update-note", id, note: val });
        }, 600));
      });
    }
  });
  _scheduleLayout(gutter);
  if (prevScroll) {
    _scrollSyncing = true;
    gutter.scrollTop = prevScroll;
    requestAnimationFrame(() => { _scrollSyncing = false; });
  }
  if (opts && opts.focusNoteId) _focusNoteCard(inner, opts.focusNoteId);
}

// Focus one card's textarea and put the caret at the end. Shared by the
// in-place and rebuild paths so "ping this note" behaves identically
// whichever way the gutter was updated.
function _focusNoteCard(inner, noteId) {
  const ta = inner.querySelector(
    `.pdf-note-card-text[data-note-id="${CSS.escape(noteId)}"]`);
  if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
}

// Debounce layout to one pass per animation frame — ResizeObserver
// fires per-observed-node, so a single re-render with N cards would
// otherwise trigger N layouts.
function _scheduleLayout(gutter) {
  if (_layoutRAF) return;
  _layoutRAF = requestAnimationFrame(() => {
    _layoutRAF = null;
    _layoutCards(gutter);
  });
}

// Greedy top-down collision pass using the cards' ACTUAL heights.
// - Each card wants to sit at its anchor y.
// - If that would put it inside the previous card's bottom edge (+gap),
//   push it just below. Otherwise leave it at its anchor.
// - Inner container height stretches to fit the last card OR the PDF
//   scrollable content, whichever is larger.
function _layoutCards(gutter) {
  const inner = gutter.querySelector(".pdf-note-gutter-inner");
  if (!inner) return;
  const cards = Array.from(inner.querySelectorAll(".pdf-note-card"));
  let previousBottom = -Infinity;
  for (const card of cards) {
    const anchor = parseFloat(card.dataset.anchorY) || 0;
    const top = Math.max(anchor, previousBottom + _CARD_GAP);
    card.style.top = `${top}px`;
    previousBottom = top + card.offsetHeight;
  }
  const need = Math.max(
    _lastViewerGeom.contentHeight,
    previousBottom > 0 ? previousBottom + 20 : 0,
    100
  );
  inner.style.height = `${need}px`;
}

// Bidirectional scroll sync between the iframe's PDF viewer and the
// gutter. `_scrollSyncing` is set by the side we're programmatically
// moving so the resulting scroll event on the OTHER side doesn't loop
// back. Cleared next frame — scroll fires synchronously so a single-
// frame window is enough.
let _scrollSyncing = false;
function _syncGutterScroll() {
  const gutter = _pdfPaneRoot()?.querySelector(".pdf-note-gutter");
  if (!gutter) return;
  const target = _lastViewerGeom.scrollTop || 0;
  if (Math.abs(gutter.scrollTop - target) < 1) return;
  _scrollSyncing = true;
  gutter.scrollTop = target;
  requestAnimationFrame(() => { _scrollSyncing = false; });
}

// Gutter → iframe scroll sync. Listens once on the gutter element per
// re-render; delegated via event bubbling on the paper-detail root so
// we don't have to re-attach when the gutter's contents are swapped.
document.addEventListener("scroll", (e) => {
  const gutter = e.target;
  if (!gutter || !gutter.classList || !gutter.classList.contains("pdf-note-gutter")) return;
  if (_scrollSyncing) return;
  _scrollSyncing = true;
  _postToViewer({ type: "set-scroll", scrollTop: gutter.scrollTop });
  requestAnimationFrame(() => { _scrollSyncing = false; });
}, true);   // capture — scroll doesn't bubble

// Ask the PAPER PANE's viewer to scroll to a highlight, retrying while
// the document loads. Mirrors NoteWorkspace._scrollWhenReady, which
// targets the workspace panel's iframe instead — two iframes, one
// behaviour, and neither owns the other's element.
function _scrollPaperPaneToHighlight(id, tries) {
  const left = tries == null ? 16 : tries;
  if (left <= 0 || !id) return;
  _postToViewer({ type: "scroll-to-highlight", id });
  setTimeout(() => _scrollPaperPaneToHighlight(id, left - 1),
             left > 13 ? 400 : 0);
}

/** The `src` for a Corpus PDF viewer iframe. The ONLY place it is built.
 *
 *  The table of contents must always start closed (2026-09-21). The
 *  paper pane had passed `pagemode=none` for months; the note-workspace
 *  panel and the Testing tab each built their own URL and left it out.
 *  Three copies of one fact, drifted — so there is now one.
 *
 *  `pagemode=none`          sidebar (table of contents) starts closed
 *  `annotationEditorMode=-1` pdf.js's own annotation editor off; Corpus
 *                           highlights are drawn by corpus-highlights.js
 *  `noteMode=1`             opt-in, paper pane only */
function pdfViewerSrc(pdfUrl, opts) {
  const o = opts || {};
  return `/vendor/pdfjs/web/viewer.html?file=${encodeURIComponent(pdfUrl)}` +
         `#zoom=page-width&annotationEditorMode=-1&pagemode=none` +
         (o.noteMode ? "&noteMode=1" : "");
}
window.pdfViewerSrc = pdfViewerSrc;

/** The PDF viewer + anchored-note gutter, for any pane that shows a PDF.
 *
 *  One definition for papers and documents (2026-09-25). The gutter code
 *  below finds its elements by these class names, so a second copy of
 *  this markup that drifted — a renamed class, a missing gutter — would
 *  silently lose highlights' notes in that pane. */
function pdfPaneHtml(pdfUrl, title, opts) {
  const o = opts || {};
  return `
      <div class="pd-subpane pd-subpane-pdf ${state.noteMode ? "note-mode" : ""}"
           ${o.hidden ? "hidden" : ""}>
        <div class="pdf-frame-and-gutter">
          <iframe class="pdf-viewer"
                  src="${escAttr(pdfViewerSrc(pdfUrl, { noteMode: state.noteMode }))}"
                  title="PDF viewer for ${escAttr(title)}"></iframe>
          <aside class="pdf-note-gutter" aria-label="Note gutter">
            <div class="pdf-note-gutter-empty">
              Anchored notes will appear here.<br>
              (Right-click a highlight in Note Mode to create one.)
            </div>
          </aside>
        </div>
      </div>`;
}

/** The pane whose PDF viewer and note gutter are live right now: the
 *  current tab's pane if that tab shows PDFs (`pdfPane: true` in MODES),
 *  else the paper pane. Every gutter / Note Mode / viewer lookup goes
 *  through here — they were hard-coded to #paper-detail until documents
 *  (2026-09-25) gave a second pane a viewer. */
function _pdfPaneRoot() {
  const m = MODES_BY_ID[state.mode];
  return document.getElementById(m && m.pdfPane ? m.detailId : "paper-detail");
}

/** The live PDF viewer iframe, or null.
 *
 *  ONE definition, used both to post TO that viewer and to decide
 *  whether a message came FROM it. Two copies of this selector drifting
 *  apart would mean posting to one frame while trusting another. */
function _paperViewerFrame() {
  const root = _pdfPaneRoot();
  return root ? root.querySelector(".pdf-viewer") : null;
}

function _postToViewer(payload) {
  const iframe = _paperViewerFrame();
  if (!iframe || !iframe.contentWindow) return;
  iframe.contentWindow.postMessage({ source: "corpus-shell", ...payload }, "*");
}

// Papers sidebar sort strip. Field select + direction toggle — both
// mutate state.papersSort and re-render. The arrow glyph on the
// direction button mirrors the current sort direction so the current
// state is legible without a tooltip.
const _sortField = $("#papers-sort-field");
const _sortDir   = $("#papers-sort-dir");
if (_sortField) {
  // Options come from MODES — the same list the note link picker offers.
  _sortField.innerHTML = MODES_BY_ID.papers.sorts
    .map(o => `<option value="${escAttr(o.key)}">${escHtml(o.label)}</option>`).join("");
  _sortField.value = state.papersSort.field;
}
if (_sortField && _sortDir) {
  _sortField.addEventListener("change", (e) => {
    state.papersSort.field = e.target.value;
    renderPapers();
  });
  _sortDir.addEventListener("click", () => {
    const next = state.papersSort.dir === "asc" ? "desc" : "asc";
    state.papersSort.dir = next;
    _sortDir.dataset.dir  = next;
    _sortDir.textContent  = next === "asc" ? "↑" : "↓";
    renderPapers();
  });
}

// Tab bar.
document.querySelector(".tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab[data-tab]");
  if (!btn) return;
  switchMode(btn.dataset.tab);
});

// Deep-links across detail panes — clicking a data-open-* link
// switches to the appropriate tab and selects the target. Keys are
// produced by EntityKeys.* on the emitting side (see paper-detail.js),
// matching the backend aggregators' key scheme.
document.addEventListener("click", (e) => {
  // Driven by MODES rather than one branch per entity type. Adding a
  // linkable entity is now one `linkAttr` on its MODES entry — the
  // click handler, the notes link picker, and the sanitizer's
  // allow-list all derive from that single declaration.
  const entityLink = LINKABLE_MODES
    .map(m => ({ m, el: e.target.closest(`a[data-open-${m.linkAttr}]`) }))
    .find(x => x.el);
  const revealLink      = e.target.closest("a[data-reveal-slug]");
  if (entityLink) {
    e.preventDefault();
    const linkId = entityLink.el.getAttribute(`data-open-${entityLink.m.linkAttr}`);
    // In a popped-out note, a paper link loads the PANEL rather than
    // navigating — keeping the note on screen is the whole point of the
    // workspace. Checked BEFORE switchMode: switching tabs in a
    // detached window tears down the split layout, so intercepting
    // afterwards would flash a broken pane on every link click.
    // Any other entity kind has nowhere to go here, so it is ignored
    // rather than blanking the window.
    if (state.detached && state.detached.kind === "note") {
      if (entityLink.m.linkAttr === "paper" || entityLink.m.linkAttr === "document") {
        const hid = entityLink.el.getAttribute("data-open-highlight") || null;
        NoteWorkspace.showPdf(entityLink.m.linkAttr, linkId, hid);
      }
      return;
    }
    switchMode(entityLink.m.id);
    entityLink.m.select(linkId);
    // Docked view: a highlight link still scrolls. A link must
    // bring up that paper and scroll to the highlight — the
    // popped-out panel is the main use, but the same link
    // in the Notes tab should not silently do half the job. Retried
    // briefly because the viewer has to open the document first, and
    // there is no ready message on the bridge.
    const hid = entityLink.el.getAttribute("data-open-highlight");
    // _postToViewer follows the live PDF pane, so this works for a
    // document's highlight too once its tab is showing.
    if (hid && (entityLink.m.linkAttr === "paper" || entityLink.m.linkAttr === "document")) {
      _scrollPaperPaneToHighlight(hid);
    }
  } else if (revealLink) {
    e.preventDefault();
    const kind = revealLink.dataset.revealKind || "pdf";
    api(`/api/paper/${encodeURIComponent(revealLink.dataset.revealSlug)}/reveal/${encodeURIComponent(kind)}`, { method: "POST" })
      .catch(err => toast("reveal failed: " + err.message, "err"));
  }
});

// "Refresh from source" — force-invalidate the OA enrichment cache
// and reload the affected detail pane. Buttons now share ONE
// attribute pattern (`data-refresh-entity="<entity>" data-refresh-key
// ="<key>"`) emitted by `EntityDetail.render`'s refresh bar, so one
// handler dispatches on the entity name.
const _REFRESH_TARGETS = {
  author:      { stateKey: "authorDetail",      render: renderAuthorDetail,      urlSegment: "author" },
  institution: { stateKey: "institutionDetail", render: renderInstitutionDetail, urlSegment: "institution" },
  journal:     { stateKey: "journalDetail",     render: renderJournalDetail,     urlSegment: "journal" },
};
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-refresh-entity]");
  if (!btn) return;
  const target = _REFRESH_TARGETS[btn.dataset.refreshEntity];
  if (!target) return;
  const key = btn.dataset.refreshKey;
  btn.disabled = true;
  btn.textContent = "Refreshing…";
  try {
    state[target.stateKey] = await api(`/api/${target.urlSegment}/${encodeURIComponent(key)}?refresh=1`);
    target.render();
    toast("enrichment refreshed", "ok");
  } catch (err) {
    toast("refresh failed: " + err.message, "err");
  }
});

// Arrow-key navigation through the active tab's list: down/up
// moves selection between adjacent items so a stack can be scanned
// without clicking each row.
//
// Suppressed when:
//   * User is typing in an <input> or <textarea> (filter box, add-task
//     input, etc.) — arrow keys have their normal in-input meaning.
//   * A modal is open (Planning / Tooltips / Settings / bug reporter).
//   * The PDF iframe has focus — inside the iframe the browser owns
//     arrows so they scroll the PDF, not the sidebar.
document.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const active = document.activeElement;
  const tag = (active?.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") return;
  if (active?.isContentEditable) return;
  // Iframe (PDF viewer) — only skip when it's actually visible on the
  // page. When the user switches from PDF to Paper info, focus stays
  // on the (now hidden) iframe; skipping arrow-nav in that state
  // silently breaks sidebar navigation. If we detect the iframe is
  // hidden, blur it and fall through so arrows drive the sidebar.
  if (tag === "iframe") {
    if (active.offsetParent !== null) return;   // iframe visible — PDF is showing, let it own arrows
    active.blur?.();                             // iframe hidden — reclaim focus for the document
  }
  // Any registered modal blocks list-nav. Dev-only overlays register
  // their own selectors via `Modals.watchSelector` at load-time, so
  // this file carries no dev-only class names. See `src/modals.js`.
  if (Modals.anyOpen()) return;

  // MODES tells us everything per-tab: which list id to query, which
  // data attribute identifies rows, which fn to call on select. The
  // pure arithmetic (which index is next given the current position)
  // lives in Nav.nextIndex — see `src/nav.js`.
  const m = MODES_BY_ID[state.mode];
  if (!m) return;
  const list = document.getElementById(m.listId);
  if (!list) return;
  // Walk visible <li>s — respects the filter, since renderXs() only
  // paints matching rows.
  const items = Array.from(list.querySelectorAll(`li[${m.dataAttr}]`));
  if (!items.length) return;
  e.preventDefault();
  const current = state[m.selectedKey];
  const currentIdx = items.findIndex(li => li.getAttribute(m.dataAttr) === current);
  const nextIdx = Nav.nextIndex({
    itemCount:    items.length,
    currentIndex: currentIdx,
    direction:    e.key === "ArrowDown" ? 1 : -1,
  });
  if (nextIdx == null) return;
  const nextItem = items[nextIdx];
  m.select(nextItem.getAttribute(m.dataAttr));
  // Keep the new selection in view — the selected class was just
  // updated by the render, so we can scroll after paint.
  requestAnimationFrame(() => nextItem.scrollIntoView({ block: "nearest" }));
});

// Cmd/Ctrl-[ and -] are the macOS browser chords; Alt+Arrow is the
// cross-platform one. Both are here because Corpus ships on both.
document.addEventListener("keydown", (e) => {
  const meta = e.metaKey || e.ctrlKey;
  if (meta && e.key === "[")  { e.preventDefault(); goBack();    return; }
  if (meta && e.key === "]")  { e.preventDefault(); goForward(); return; }
  if (e.altKey && e.key === "ArrowLeft")  { e.preventDefault(); goBack();    return; }
  if (e.altKey && e.key === "ArrowRight") { e.preventDefault(); goForward(); return; }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#settings-modal").hidden) closeSettings();
});

// Boot.
// A failed boot used to be a 3.5s toast over an otherwise empty window.
// Popping out a note showed a blank window (2026-09-21): the log showed boot stopping after /api/tooltips in both
// windows, and nothing on screen or on disk said why. Now it stays on
// screen, and in dev it lands in server.log with its stack.
boot().catch(e => {
  _reportClientError("boot", e);
  const title = document.getElementById("empty-state-title");
  const body  = document.getElementById("empty-state-body");
  const pane  = document.getElementById("empty-state");
  if (title) title.textContent = "Corpus hit an error starting up";
  if (body)  body.textContent  = String((e && e.message) || e);
  if (pane)  pane.hidden = false;
  try { toast("boot failed: " + ((e && e.message) || e), "err"); } catch (_) {}
});
