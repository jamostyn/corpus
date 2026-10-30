// Projects tab — folders of papers and notes that don't move anything.
//
// A project stores the IDs of its members; the papers and notes
// themselves stay exactly where they are, and one can belong to any
// number of projects. See python/projects_api.py's module docstring
// for why membership is stored on the project rather than on each
// paper (short version: a re-extract rewrites the summary .md and
// would silently drop a `projects:` frontmatter key).
//
// Relies on globals from app.js resolved at CALL time, same contract
// as the other detail modules: state, api, toast, $, escHtml, escAttr,
// hideEmptyState, _relativeTime, MODES.

async function loadProjects() {
  try {
    state.projects = await api("/api/projects");
    renderProjects();
    if (state.selectedProjectId &&
        !state.projects.find(p => p.id === state.selectedProjectId)) {
      state.selectedProjectId = null;
      state.projectDetail = null;
    }
    if (state.selectedProjectId) renderProjectDetail();
    else $("#project-detail").innerHTML = _projectEmptyStateHtml();
  } catch (e) {
    toast("projects load failed: " + e.message, "err");
  }
}

function _projectCountLine(c) {
  const parts = [];
  for (const m of _memberModes()) {
    const n = (c && c[m.memberKind]) || 0;
    parts.push(`${n} ${n === 1 ? m.memberNoun : m.memberNounPlural}`);
  }
  return parts.join(" · ");
}

function renderProjects() {
  const list = $("#projects-list");
  const f = state.projectFilter.trim().toLowerCase();
  const filtered = f
    ? state.projects.filter(p =>
        (p.title || "").toLowerCase().includes(f) ||
        (p.description || "").toLowerCase().includes(f))
    : state.projects;
  list.innerHTML = filtered.map(p => `
    <li data-project-id="${escAttr(p.id)}" ${p.id === state.selectedProjectId ? 'class="selected"' : ""}>
      <div class="p-title">${escHtml(p.title || "Untitled project")}</div>
      <div class="p-meta">${escHtml(_projectCountLine(p.counts))}</div>
    </li>
  `).join("");
  if (state.mode === "projects") {
    $("#count-line").textContent = state.projects.length === filtered.length
      ? `${state.projects.length} project${state.projects.length === 1 ? "" : "s"}`
      : `${filtered.length} of ${state.projects.length} shown`;
  }
}

async function selectProject(id) {
  state.selectedProjectId = id;
  renderProjects();
  hideEmptyState();
  const pane = $("#project-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.projectDetail = await api(`/api/project/${encodeURIComponent(id)}`);
    renderProjectDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function _projectEmptyStateHtml() {
  return `
    <div class="project-empty">
      <h2>Projects</h2>
      <p>A project is a folder of papers and notes that doesn't move them.
         Anything can belong to several projects at once.</p>
      <p>Project files live under
        <code>${escHtml((state.config?.corpus_dir || "") + "/projects/")}</code>.
        Deleting a project never deletes its papers or notes.</p>
    </div>`;
}

// ---------- Member modes ---------------------------------------------
//
// Which MODES can be filed into a project. A mode qualifies exactly
// when it declares `memberKind` — nothing here keeps a second list of
// member types, and python/projects_api.py's _PROJECT_MEMBER_KINDS is
// held to the same list by tests/test_project_member_kinds.py.

function _memberModes() {
  return (window.PROJECT_MEMBER_MODES || []);
}

function _memberModeByKind(kind) {
  return _memberModes().find(m => m.memberKind === kind) || null;
}

// Label for one member row. Papers already carry a `linkLabel` (used
// by the notes entity-link picker); reusing it keeps a single
// definition of "how a paper is named in a list" rather than a second
// copy that drifts.
// Placeholder naming what the filter actually searches. A box
// labelled only "Filter papers…" gave no hint whether author was searched.
//
// `searchHint` lives on the MODES entry directly beside `searchFields`
// so the prose and the field list are read and edited together. An
// earlier draft of this kept a `{papers: "title, author, year"}` map
// here — a second copy of the field list, in a different file from the
// one it describes, which is precisely the drift this codebase keeps
// getting bitten by.
function _memberSearchHint(mode) {
  return mode.searchHint
    ? `Filter by ${mode.searchHint}…`
    : `Filter ${mode.memberNounPlural}…`;
}

function _memberLabel(mode, row) {
  const fn = mode.memberLabel || mode.linkLabel;
  return fn ? fn(row) : (row.title || row.id);
}

// ---------- Detail ----------------------------------------------------

function renderProjectDetail() {
  const p = state.projectDetail;
  if (!p) return;
  const pane = $("#project-detail");

  const sections = _memberModes().map(m => {
    const rows = (p.resolved && p.resolved[m.memberKind]) || [];
    const items = rows.length
      ? rows.map(r => `
          <li>
            <a href="#" class="pj-member-open" data-member-kind="${escAttr(m.memberKind)}" data-member-id="${escAttr(r.id)}">${escHtml(_memberLabel(m, r))}</a>
            <button class="btn ghost pj-remove" data-kind="${escAttr(m.memberKind)}"
                    data-id="${escAttr(r.id)}" aria-label="Remove from project">✕</button>
          </li>`).join("")
      : `<li class="pj-empty">No ${escHtml(m.memberNounPlural)} yet.</li>`;
    return `
      <section class="pj-section">
        <header class="pj-section-head">
          <h3>${escHtml(m.memberNounPlural.replace(/^./, c => c.toUpperCase()))}
            <span class="pj-count">${rows.length}</span></h3>
          <button class="btn pj-add" data-kind="${escAttr(m.memberKind)}">Add ${escHtml(m.memberNounPlural)}…</button>
        </header>
        <ul class="pj-member-list">${items}</ul>
      </section>`;
  }).join("");

  pane.innerHTML = `
    <div class="pj-head">
      <input class="pj-title" id="pj-title" type="text"
             value="${escAttr(p.title || "")}" placeholder="Untitled project"
             aria-label="Project title">
      <button class="btn" id="pj-export-refs"${(p.counts && p.counts.paper) ? "" : " disabled"}>Export references…</button>
      <button class="btn danger" id="pj-delete">Delete project</button>
    </div>
    <textarea class="pj-desc" id="pj-desc" rows="2"
              placeholder="Description (optional)"
              aria-label="Project description">${escHtml(p.description || "")}</textarea>
    <div class="pj-meta">Updated ${escHtml(_relativeTime(p.updated_at))}</div>
    ${sections}
  `;
  _wireProjectDetail();
}

function _wireProjectDetail() {
  const pane = $("#project-detail");
  const p = state.projectDetail;
  if (!pane || !p) return;

  // References of every paper in the project, in a chosen style (cite-ui.js).
  const exp = $("#pj-export-refs");
  if (exp) exp.addEventListener("click", () => CiteUI.openProjectExport(p));

  // Title + description: debounced save, same feel as the note editor.
  let t = null;
  const save = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      try {
        const body = {
          title: $("#pj-title").value,
          description: $("#pj-desc").value,
        };
        const updated = await api(`/api/project/${encodeURIComponent(p.id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        // Keep resolved members from the pane's copy — the PUT
        // response deliberately carries no `resolved` block.
        state.projectDetail = { ...updated, resolved: p.resolved, counts: p.counts };
        const row = state.projects.find(r => r.id === p.id);
        if (row) { row.title = updated.title; row.description = updated.description; }
        renderProjects();
      } catch (e) {
        toast("save failed: " + e.message, "err");
      }
    }, 500);
  };
  $("#pj-title").addEventListener("input", save);
  $("#pj-desc").addEventListener("input", save);

  $("#pj-delete").addEventListener("click", async () => {
    if (!confirm(`Delete "${p.title}"? The papers and notes inside it are not deleted.`)) return;
    try {
      await api(`/api/project/${encodeURIComponent(p.id)}`, { method: "DELETE" });
      state.selectedProjectId = null;
      state.projectDetail = null;
      await loadProjects();
      $("#project-detail").innerHTML = _projectEmptyStateHtml();
      toast("Project deleted");
    } catch (e) {
      toast("delete failed: " + e.message, "err");
    }
  });

  pane.querySelectorAll(".pj-add").forEach(btn =>
    btn.addEventListener("click", () => _openMemberPicker(btn.dataset.kind)));

  pane.querySelectorAll(".pj-remove").forEach(btn =>
    btn.addEventListener("click", () =>
      _editMember(btn.dataset.kind, btn.dataset.id, "remove")));

  // Jump to a member. Deliberately NOT the `data-open-<attr>` deep-link
  // delegation in app.js: that handler iterates LINKABLE_MODES, which
  // covers papers but not notes (a note is not a link TARGET for the
  // notes editor). Emitting `data-open-note` would therefore render a
  // link that silently does nothing. Going through the mode's own
  // `select` works for every member kind by construction.
  pane.querySelectorAll(".pj-member-open").forEach(a =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const mode = _memberModeByKind(a.dataset.memberKind);
      if (!mode) return;
      switchMode(mode.id);
      mode.select(a.dataset.memberId);
    }));
}

async function _editMember(kind, id, op) {
  const p = state.projectDetail;
  if (!p) return;
  try {
    state.projectDetail = await api(
      `/api/project/${encodeURIComponent(p.id)}/members`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, id, op }),
      });
    renderProjectDetail();
    const row = state.projects.find(r => r.id === p.id);
    if (row) { row.counts = state.projectDetail.counts; }
    renderProjects();
  } catch (e) {
    toast(`${op} failed: ` + e.message, "err");
  }
}

// ---------- Member picker ---------------------------------------------
//
// Deliberately NOT notes.js's _openEntityLinkPicker: that one takes a
// saved DOM Range and writes an <a> into a contenteditable body, so
// reusing it would mean gutting it. What the two DO share — how a row
// is labelled and identified — comes from the same MODES functions, so
// the duplicated part is modal markup, not a fact. Extracting a shared
// picker shell is a planned cleanup.

function _dismissMemberPicker() {
  const old = document.querySelector(".pj-picker-overlay");
  if (old) old.remove();
}

// The shell both pickers share: overlay, filter box, list, dismissal.
//
// Added when the second picker arrived (paper → projects, 2026-09-21).
// The first one's comment above already called the duplicated modal
// markup out; a third copy of it was the point at which "we'll extract
// it later" stops being a plan. Only the SHELL is shared — what a row
// means and what a pick does stay with each caller.
//
// `rows`: [{id, label, selected, row}] — `row` is the source object the
// filter runs against, so filtering can search fields the label does
// not show. `keepOpen` is for the membership toggle, where the user is
// likely to file a paper into two projects at once.
function _pickerShell({ title, placeholder, rows, filter, onPick, keepOpen }) {
  _dismissMemberPicker();
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay pj-picker-overlay";
  overlay.innerHTML = `
    <div class="modal pj-picker-modal">
      <header class="modal-header">
        <h2>${escHtml(title)}</h2>
        <button class="btn ghost" data-close="1">✕</button>
      </header>
      <div class="modal-body">
        <input type="search" class="pj-picker-filter" id="pj-picker-filter"
               placeholder="${escAttr(placeholder)}" autofocus>
        <ul class="pj-picker-list" id="pj-picker-list"></ul>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const listEl = overlay.querySelector("#pj-picker-list");
  const draw = (f) => {
    const q = (f || "").trim().toLowerCase();
    const shown = q ? rows.filter(r => filter(r, q)) : rows;
    listEl.innerHTML = shown.length
      ? shown.slice(0, 200).map(r =>
          `<li><button class="pj-picker-row${r.selected ? " is-member" : ""}"
                       data-id="${escAttr(r.id)}"
                       aria-pressed="${r.selected ? "true" : "false"}">${escHtml(r.label)}</button></li>`).join("")
      : `<li class="pj-empty">Nothing to add.</li>`;
  };
  draw("");

  overlay.querySelector("#pj-picker-filter").addEventListener("input", e => draw(e.target.value));
  overlay.addEventListener("click", async (e) => {
    if (e.target.dataset.close || e.target === overlay) { _dismissMemberPicker(); return; }
    const rowEl = e.target.closest(".pj-picker-row");
    if (!rowEl) return;
    const picked = rows.find(r => String(r.id) === rowEl.dataset.id);
    if (!keepOpen) _dismissMemberPicker();
    const nowSelected = await onPick(rowEl.dataset.id, !!(picked && picked.selected));
    if (keepOpen && picked) {
      // Re-read from the caller's answer rather than assuming the
      // toggle flipped: a failed request must not leave a checkmark
      // claiming the paper was filed.
      picked.selected = !!nowSelected;
      draw(overlay.querySelector("#pj-picker-filter").value);
    }
  });
  document.addEventListener("keydown", function esc(ev) {
    if (ev.key === "Escape") { _dismissMemberPicker(); document.removeEventListener("keydown", esc); }
  });
  return overlay;
}

async function _openMemberPicker(kind) {
  const mode = _memberModeByKind(kind);
  const p = state.projectDetail;
  if (!mode || !p) return;
  _dismissMemberPicker();

  // Fresh rows every time, not just when the tab was never opened: a
  // paper imported from another window would otherwise be missing here
  // (same defect as the note link picker — see app.js::fetchModeList).
  try { await fetchModeList(mode); } catch (e) { /* show what state has */ }
  const already = new Set((p.resolved?.[kind] || []).map(r => r.id));
  const idOf = mode.linkId || (r => r.id);
  // Keep the source row: the filter runs against `modeRowMatches`,
  // which reads fields the LABEL does not show (a paper's author, for
  // one — the whole point of this picker's filter).
  const rows = (state[mode.stateKey] || [])
    .map(r => ({ id: idOf(r), label: _memberLabel(mode, r), row: r }))
    .filter(r => r.id && !already.has(r.id));

  _pickerShell({
    title: `Add ${mode.memberNounPlural}`,
    placeholder: _memberSearchHint(mode),
    rows,
    filter: (r, q) => modeRowMatches(mode, r.row, q),
    onPick: (id) => _editMember(kind, id, "add"),
  });
}

// ---------- The inverse: file THIS paper into projects ----------------
//
// Requirement (2026-09-21): a button in the paper view header adds the
// paper to a project.
//
// Membership was only ever editable from the project side — open a
// project, add papers to it. This is the reverse entry point: file the
// paper you are reading without leaving it.
//
// It lives in projects.js rather than paper-detail.js because this is
// project membership, and every rule about it (which kinds can be
// members, how a project is labelled, what an edit posts) already lives
// here. paper-detail.js only renders a button and calls in.
//
// Shows EVERY project with the current ones ticked, and toggles on
// click, so one control both files and unfiles. An add-only list would
// leave "get it out again" reachable only from the project side — the
// exact asymmetry this is fixing.

async function openProjectPickerFor(kind, id) {
  if (!kind || !id) return;
  if (!state.projects || !state.projects.length) {
    try { await loadProjects(); } catch (e) { /* loadProjects toasts */ }
  }
  if (!state.projects || !state.projects.length) {
    toast("no projects yet — create one in the Projects tab");
    return;
  }

  let member = new Set();
  try {
    const rows = await api(`/api/member-projects/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`);
    member = new Set(rows.map(r => r.id));
  } catch (e) {
    toast("could not read project membership: " + e.message, "err");
    return;
  }

  const mode = MODES_BY_ID.projects;
  const rows = state.projects.map(p => ({
    id: p.id,
    label: p.title || "Untitled project",
    selected: member.has(p.id),
    row: p,
  }));

  _pickerShell({
    title: "Add to project",
    placeholder: _memberSearchHint(mode),
    rows,
    filter: (r, q) => modeRowMatches(mode, r.row, q),
    keepOpen: true,
    onPick: (pid, wasSelected) => _toggleMembership(pid, kind, id, wasSelected),
  });
}

/** Add or remove one member from one project. Returns the membership
 *  state AFTER the call, so the picker can tick the row from what the
 *  server actually did rather than from what was hoped. */
async function _toggleMembership(pid, kind, id, wasSelected) {
  const op = wasSelected ? "remove" : "add";
  try {
    const updated = await api(`/api/project/${encodeURIComponent(pid)}/members`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, id, op }),
    });
    // Keep the sidebar counts honest without a refetch.
    const row = state.projects.find(r => r.id === pid);
    if (row) row.counts = updated.counts;
    if (state.mode === "projects") renderProjects();
    // If the very project being edited is open behind the modal, its
    // member list is now stale.
    if (state.projectDetail && state.projectDetail.id === pid) {
      state.projectDetail = updated;
      renderProjectDetail();
    }
    toast(op === "add" ? `Added to ${updated.title || "project"}`
                       : `Removed from ${updated.title || "project"}`);
    return op === "add";
  } catch (e) {
    toast(`${op} failed: ` + e.message, "err");
    return wasSelected;           // unchanged — do not tick a failed add
  }
}

// paper-detail.js (and, later, the note pane) call in here.
window.ProjectMembership = { openFor: openProjectPickerFor };

async function createProject() {
  try {
    const p = await api("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Untitled project" }),
    });
    await loadProjects();
    await MODES_BY_ID.projects.select(p.id);  // wrapped: records history
    const input = $("#pj-title");
    if (input) { input.focus(); input.select(); }
  } catch (e) {
    toast("create failed: " + e.message, "err");
  }
}
