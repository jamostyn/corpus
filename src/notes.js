// Corpus — Notes tab. Split from app.js on 2026-08-15.
//
// Owns everything under the Notes top-level tab: the sidebar list,
// the rich-text editor, the toolbar (bold/italic/font-size/lists/
// tables/undo/redo/clear), Excel-style table resize and right-click
// menu, and the per-note session undo/redo history.
//
// Depends on globals defined in app.js at load time: `state`, `api`,
// `toast`, `$`, `escHtml`, `escAttr`, `hideEmptyState`. This file is
// script-loaded AFTER app.js in index.html; function definitions here
// are hoisted at parse-time, so app.js's event wiring (which references
// createNote / selectNote etc.) resolves at event-fire time.

// ---------- Notes ----------
//
// Free-form rich-text notes. Storage: <corpus>/notes/<id>.json (see
// server.py). Editor is a contenteditable div with a small formatting
// toolbar; save is debounced on typing and forced on Cmd-S / blur /
// tab-away. Deliberately dependency-free — no ProseMirror/TipTap etc.
// The server sanitises the body HTML on every PUT so an errant paste
// can't smuggle scripts into a future session.

async function loadNotes() {
  try {
    state.notes = await api("/api/notes");
    renderNotes();
    if (state.selectedNoteId && !state.notes.find(n => n.id === state.selectedNoteId)) {
      state.selectedNoteId = null;
      state.noteDetail = null;
    }
    if (state.selectedNoteId) renderNoteDetail();
    else $("#note-detail").innerHTML = _noteEmptyStateHtml();
  } catch (e) {
    toast("notes load failed: " + e.message, "err");
  }
}

function renderNotes() {
  const list = $("#notes-list");
  const f = state.noteFilter.trim().toLowerCase();
  const filtered = f
    ? state.notes.filter(n =>
        (n.title || "").toLowerCase().includes(f) ||
        (n.snippet || "").toLowerCase().includes(f))
    : state.notes;
  list.innerHTML = filtered.map(n => `
    <li data-note-id="${escAttr(n.id)}" ${n.id === state.selectedNoteId ? 'class="selected"' : ""}>
      <div class="p-title">${escHtml(n.title || "Untitled note")}</div>
      <div class="p-meta">${escHtml(_noteRelTime(n.updated_at))}${
        n.snippet ? " · " + escHtml(n.snippet) : ""
      }</div>
    </li>
  `).join("");
  if (state.mode === "notes") {
    $("#count-line").textContent = state.notes.length === filtered.length
      ? `${state.notes.length} note${state.notes.length === 1 ? "" : "s"}`
      : `${filtered.length} of ${state.notes.length} shown`;
  }
}

function _noteRelTime(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!isFinite(t)) return "";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60)         return `${s}s ago`;
  if (s < 3600)       return `${Math.floor(s / 60)}m ago`;
  if (s < 86400)      return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

async function selectNote(id) {
  state.selectedNoteId = id;
  renderNotes();
  hideEmptyState();
  const pane = $("#note-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.noteDetail = await api(`/api/note/${encodeURIComponent(id)}`);
    renderNoteDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function _noteEmptyStateHtml() {
  return `
    <div class="note-empty">
      <h2>Notes</h2>
      <p>Free-form scratchpad. Rich-text notes live under
        <code>${escHtml((state.config?.corpus_dir || "") + "/notes/")}</code>
        as JSON files. Click <strong>New note</strong> to start one.</p>
    </div>
  `;
}

// Toolbar spec — one place so keyboard hooks and rendered buttons stay
// in sync. `cmd` is passed to document.execCommand; `arg` is the second
// arg. `fontSize: "class-suffix"` runs the custom span-wrap font-size
// path instead. Group separators render as visual dividers, not
// buttons.
//
// Tags NOT surfaced in the toolbar (H2/H3/P/blockquote/link) are still
// permitted by the sanitiser so pasted content keeps that formatting —
// they were removed here per direct user feedback that the buttons
// weren't earning their keep in the day-to-day workflow.
const _NOTE_TOOLBAR = [
  { label: "B",  cmd: "bold",         title: "Bold ⌘B",       key: "b" },
  { label: "I",  cmd: "italic",       title: "Italic ⌘I",     key: "i" },
  { label: "U",  cmd: "underline",    title: "Underline ⌘U",  key: "u" },
  { label: "S",  cmd: "strikeThrough",title: "Strikethrough ⌘S", key: "s" },
  { sep: true },
  { fontSizeSelect: true },   // rendered as <select> — see renderNoteDetail
  { sep: true },
  { label: "•",  cmd: "insertUnorderedList", title: "Bullet list"      },
  { label: "1.", cmd: "insertOrderedList",   title: "Numbered list"    },
  { label: "→",  cmd: "indent",              title: "Indent list item (Tab)"       },
  { label: "←",  cmd: "outdent",             title: "Outdent list item (Shift-Tab)" },
  { sep: true },
  { label: "⊞", tableInsert: true, title: "Insert table"              },
  { label: "🔗", entityLink: true, title: "Link to a paper, author, institution or journal" },
  { label: "↺", cmd: "removeFormat",  title: "Clear formatting"        },
  { sep: true },
  { label: "↶", historyUndo: true, title: "Undo ⌘Z"                    },
  { label: "↷", historyRedo: true, title: "Redo ⇧⌘Z"                   },
];

// Font-size input bounds. Numeric field, min/max clamp on both the
// input widget and the sanitiser so pasted or user-typed sizes outside
// the range get rejected client-side AND server-side.
const _NOTE_FONT_SIZE_MIN = 1;
const _NOTE_FONT_SIZE_MAX = 120;
const _NOTE_DEFAULT_FS    = 15;

// `host` lets the popped-out workspace render the same editor into its
// left pane instead of the docked #note-detail. Defaulting keeps every
// existing caller unchanged — there is ONE note editor, rendered in two
// places, not two editors to keep in step.
// The open editor's "save now if anything is pending", or null. Set by
// renderNoteDetail; called by openDetached before a note pops out.
let _flushNoteSave = null;
async function flushNoteSave() {
  if (_flushNoteSave) await _flushNoteSave();
}
// Fire-and-forget version for a closing window (see _wireNoteEditor).
let _flushNoteSaveOnExit = null;
window.addEventListener("pagehide", () => { if (_flushNoteSaveOnExit) _flushNoteSaveOnExit(); });

function renderNoteDetail(host) {
  const n = state.noteDetail;
  if (!n) return;
  const pane = host || $("#note-detail");
  const detachedNote = !!(state.detached && state.detached.kind === "note");

  // Popped out to another window: lock this copy. Two live editors on one
  // note, each autosaving, overwrite each other (2026-09-21).
  if (!detachedNote && isDetachedElsewhere("note", n.id)) {
    _flushNoteSave = null;
    _flushNoteSaveOnExit = null;
    pane.innerHTML = detachedPlaceholderHtml("note", n.id);
    return;
  }

  const toolbar = _NOTE_TOOLBAR.map(b => {
    if (b.sep) return `<span class="note-tb-sep" aria-hidden="true"></span>`;
    if (b.fontSizeSelect) {
      return `<input type="number" class="note-tb-fs" id="note-tb-fs"
                min="${_NOTE_FONT_SIZE_MIN}" max="${_NOTE_FONT_SIZE_MAX}"
                value="${_NOTE_DEFAULT_FS}" step="1"
                title="Font size (${_NOTE_FONT_SIZE_MIN}–${_NOTE_FONT_SIZE_MAX})">`;
    }
    return `
    <button type="button" class="note-tb-btn"
            ${b.cmd         ? `data-cmd="${escAttr(b.cmd)}"`           : ""}
            ${b.arg         ? `data-arg="${escAttr(b.arg)}"`           : ""}
            ${b.isLink      ? `data-link="1"`                          : ""}
            ${b.tableInsert ? `data-table-insert="1"`                  : ""}
            ${b.entityLink  ? `data-entity-link="1"`                   : ""}
            ${b.historyUndo ? `data-history-undo="1"`                  : ""}
            ${b.historyRedo ? `data-history-redo="1"`                  : ""}
            title="${escAttr(b.title)}">${escHtml(b.label)}</button>
  `;
  }).join("");

  pane.innerHTML = `
    <div class="note-head">
      <input class="note-title-input" id="note-title-input"
             value="${escAttr(n.title)}"
             placeholder="Untitled note">
      <div class="note-head-actions">
        <span class="note-status" id="note-save-status"></span>
        ${detachedNote
          ? `<button class="btn" id="btn-note-pick-hl">Link highlight</button>`
          : `<button class="btn" id="btn-note-popout" data-note-id="${escAttr(n.id)}">Pop out</button>`}
        <div class="note-settings">
          <button type="button" class="btn" id="btn-note-settings"
                  aria-haspopup="menu" aria-expanded="false">Settings</button>
          <div class="note-settings-menu" id="note-settings-menu" role="menu" hidden>
            <div class="note-settings-head">
              <span>Settings</span>
              <button type="button" class="note-settings-close"
                      id="btn-note-settings-close" aria-label="Close settings">×</button>
            </div>
            <button type="button" role="menuitem"
                    class="note-table-menu-item note-table-menu-item-danger"
                    id="btn-note-delete">Delete note</button>
          </div>
        </div>
      </div>
    </div>
    <div class="note-toolbar" id="note-toolbar" role="toolbar" aria-label="Formatting">
      ${toolbar}
    </div>
    <div class="note-body" id="note-body" contenteditable="true"
         spellcheck="true">${n.body_html || ""}</div>
    <div class="note-meta-line">
      created ${escHtml(_noteRelTime(n.created_at))} · last saved ${escHtml(_noteRelTime(n.updated_at))}
    </div>
  `;

  _wireNoteEditor(n);
}

function _wireNoteEditor(n) {
  const pane = $("#note-detail");
  const title = $("#note-title-input");
  const body  = $("#note-body");
  const status = $("#note-save-status");
  const toolbar = $("#note-toolbar");

  // Pop out (docked view) / Link highlight (popped-out view). Only one
  // of the two exists at a time — see renderNoteDetail.
  const popBtn = $("#btn-note-popout");
  if (popBtn) popBtn.addEventListener("click",
    () => openDetached("note", popBtn.dataset.noteId));

  const pickBtn = $("#btn-note-pick-hl");
  if (pickBtn) pickBtn.addEventListener("click", () => {
    // Remember where the caret is: arming the pick moves focus into
    // the PDF iframe, and without a saved Range the link would be
    // inserted wherever focus happened to land afterwards. Same
    // reasoning as _openEntityLinkPicker's savedRange.
    const sel = document.getSelection();
    const savedRange = (sel && sel.rangeCount) ? sel.getRangeAt(0).cloneRange() : null;
    NoteWorkspace.pickHighlight(({ kind, slug, id, text }) => {
      if (!slug || !id) return;
      _insertHighlightLink(body, savedRange, kind || "paper", slug, id, text);
      _historyCheckpoint(n.id, title, body);
      scheduleSave();
    });
  });

  // Ask the browser to wrap new paragraphs in <p> instead of <div> on
  // Enter — cleaner output and matches the sanitiser's preferred tag.
  // Chrome/WebKit honour this; Firefox silently ignores. Either way,
  // both <p> and <div> are on the server allow-list so Enter survives.
  try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (_) {}

  let saveTimer = null;
  // The revision this editor's text is based on. Every save sends it; the
  // server refuses a save based on an older revision instead of writing
  // over newer work (2026-09-28: pop-out edits were overwritten by
  // the main window's 30-minute-old copy). Advanced by each save.
  let baseRevision = n.revision || 0;
  // Set when the server has refused a stale save. Autosave stops until
  // the user picks "Load the saved version" or "Keep mine" — carrying on
  // would only be refused again, and silently.
  let conflict = false;
  const scheduleSave = () => {
    if (conflict) return;
    if (saveTimer) clearTimeout(saveTimer);
    status.textContent = "…";
    saveTimer = setTimeout(() => { saveTimer = null; commitSave(); }, 800);
  };
  const metaLine = pane.querySelector(".note-meta-line");
  const url = `/api/note/${encodeURIComponent(n.id)}`;
  const payloadNow = (force) => JSON.stringify({
    title: title.value, body_html: body.innerHTML, base_revision: baseRevision,
    ...(force ? { force: true } : {}),
  });
  // Exposed so popping the note out can land pending edits first.
  _flushNoteSave = () => (saveTimer ? commitSave() : Promise.resolve());
  // Closing a window with an edit still inside the 800ms debounce used to
  // drop it. `keepalive` lets the request outlive the page.
  _flushNoteSaveOnExit = () => {
    if (!saveTimer || conflict) return;
    clearTimeout(saveTimer); saveTimer = null;
    try {
      fetch(url, { method: "PUT", keepalive: true,
                   headers: { "content-type": "application/json" }, body: payloadNow(false) });
    } catch (_) {}
  };
  const commitSave = async (force) => {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    try {
      const updated = await api(url, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body:    payloadNow(force),
      });
      baseRevision = updated.revision || baseRevision + 1;
      conflict = false;
      const banner = pane.querySelector(".note-conflict");
      if (banner) banner.remove();
      // Do NOT replace body.innerHTML — destructive re-write mid-typing
      // was killing keystrokes (Enter → newline → autosave → innerHTML
      // reset → newline appeared to "undo itself"). The server-
      // sanitised version lands on next full re-render (tab switch /
      // re-select), which is fine for a single-user editor. Pasted
      // junk that survives on-screen until then is harmless because
      // the STORED version is already clean.
      state.noteDetail = updated;
      // Refresh sidebar list (title/snippet/updated_at may have changed).
      const idx = state.notes.findIndex(x => x.id === updated.id);
      if (idx >= 0) {
        state.notes[idx] = {
          id: updated.id,
          title: updated.title,
          created_at: updated.created_at,
          updated_at: updated.updated_at,
          snippet: (updated.body_html || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 120),
        };
        // Keep most-recently-updated at top.
        state.notes.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
        renderNotes();
      }
      // Refresh the meta-line so "last saved" reflects reality instead
      // of staying stuck at "0s ago" from the initial render.
      if (metaLine) {
        metaLine.textContent =
          `created ${_noteRelTime(updated.created_at)} · last saved ${_noteRelTime(updated.updated_at)}`;
      }
      status.textContent = "saved";
      setTimeout(() => { if (status.textContent === "saved") status.textContent = ""; }, 1500);
    } catch (e) {
      if (e.status === 409) { _showConflict(); return; }
      status.textContent = "save failed";
      toast("note save failed: " + e.message, "err");
    }
  };

  // The server refused this save: the note changed elsewhere (another
  // window) after this editor loaded it. Nothing is overwritten. The
  // user chooses; the editor never decides to discard either version.
  const _showConflict = () => {
    conflict = true;
    status.textContent = "not saved";
    if (pane.querySelector(".note-conflict")) return;
    const bar = document.createElement("div");
    bar.className = "note-conflict";
    bar.innerHTML = `
      <span>This note was changed in another window. What you see here is <strong>not saved</strong>.</span>
      <button type="button" class="btn" data-conflict="load">Load the saved version</button>
      <button type="button" class="btn" data-conflict="keep">Keep mine</button>`;
    pane.querySelector(".note-head").after(bar);
    bar.addEventListener("click", async (ev) => {
      const which = ev.target.closest("[data-conflict]")?.dataset.conflict;
      if (which === "keep") {
        await commitSave(true);                     // explicit overwrite, user's choice
      } else if (which === "load") {
        conflict = false;
        state.noteDetail = await api(url);
        renderNoteDetail(state.detached && state.detached.kind === "note"
                         ? document.getElementById("nw-note") : undefined);
      }
    });
  };

  // Initialise this note's history snapshot from the current state.
  _historyInit(n.id, title, body);

  const onEdit = () => {
    _historyOnEdit(n.id, title, body);
    scheduleSave();
  };
  title.addEventListener("input", onEdit);
  body.addEventListener("input",  onEdit);
  body.addEventListener("blur",   commitSave);
  title.addEventListener("blur",  commitSave);

  // Keyboard chords in the note editor:
  //   Cmd-B / U / I / S       — formatting, declared in _NOTE_TOOLBAR
  //                             and dispatched through the toolbar
  //                             buttons so both routes behave alike
  //   Cmd-Shift-S             — force flush save (was Cmd-S)
  //   Cmd-Z / Ctrl-Z          — undo    (preventDefault to block native)
  //   Cmd-Shift-Z / Ctrl-Y    — redo
  const keyHandler = (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;

    // Formatting chords are driven BY _NOTE_TOOLBAR's `key` field, and
    // dispatch by clicking the matching button rather than calling
    // execCommand here. That is deliberate: the click handler already
    // does focus restoration, the indent/outdent special-casing, the
    // history checkpoint and the save schedule. Re-implementing any of
    // that for the keyboard would be a second copy that drifts — press
    // ⌘B and get a different result from clicking B.
    //
    // The `key` field pre-dated this handler (declared on B/I/U, read
    // by nothing); wiring it up is what makes the toolbar spec the one
    // place a chord is declared.
    if (!e.shiftKey && !e.altKey) {
      const spec = _NOTE_TOOLBAR.find(
        b => b.key && b.key === String(e.key || "").toLowerCase());
      if (spec) {
        const btn = toolbar.querySelector(`.note-tb-btn[data-cmd="${spec.cmd}"]`);
        if (btn) { e.preventDefault(); btn.click(); return; }
      }
    }

    // Force-flush save moved to ⌘⇧S when ⌘S became strikethrough.
    // Kept rather than dropped: autosave covers the common case
    // (debounced on input, flushed on blur), but an explicit "write it
    // now" is cheap to keep and removing it was not asked for.
    if ((e.key === "s" || e.key === "S") && e.shiftKey) {
      e.preventDefault(); commitSave(); return;
    }
    if (e.key === "z" || e.key === "Z") {
      e.preventDefault();
      if (e.shiftKey) {
        if (_historyRedo(n.id, title, body)) scheduleSave();
      } else {
        if (_historyUndo(n.id, title, body)) scheduleSave();
      }
      return;
    }
    if (e.key === "y" || e.key === "Y") {
      // Windows convention — Ctrl-Y = redo.
      e.preventDefault();
      if (_historyRedo(n.id, title, body)) scheduleSave();
      return;
    }
  };
  title.addEventListener("keydown", keyHandler);
  body.addEventListener("keydown",  keyHandler);

  // Tab handler with three branches:
  //   1. Inside a list item → custom indent/outdent (see below).
  //      Browser's execCommand("indent") wraps a first-item in a
  //      blockquote instead of creating a nested list, which is why
  //      we roll our own — it always produces a proper nested
  //      <ul>/<ol>/<li> tree that the marker-cycling CSS can style.
  //   2. In plain text → insert 4 non-breaking spaces as a text indent.
  //      NBSP survives the sanitiser without needing `white-space:
  //      pre-wrap` (which would change paragraph rendering).
  //   3. Shift-Tab in plain text at start of a line → let the browser
  //      handle it (focus-nav fallback).
  body.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const sel = document.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    let node = sel.anchorNode;
    // Walk up looking for a <li>. Stop at the body root.
    let li = null;
    while (node && node !== body) {
      if (node.nodeType === 1 && node.tagName === "LI") { li = node; break; }
      node = node.parentNode;
    }
    if (li) {
      e.preventDefault();
      if (e.shiftKey) _outdentListItem(li);
      else            _indentListItem(li);
      _historyCheckpoint(n.id, title, body);
      scheduleSave();
      return;
    }
    // Plain text — insert 4 NBSPs on Tab. Shift-Tab falls through
    // to browser default (focus navigation to a prior element).
    if (!e.shiftKey) {
      e.preventDefault();
      document.execCommand("insertText", false, "    ");
      _historyCheckpoint(n.id, title, body);
      scheduleSave();
    }
  });

  // Toolbar clicks. Uses document.execCommand — deprecated in the spec
  // but every current browser (Chrome/WebKit/Firefox 2026) still
  // implements it, and it's the shortest path to rich-text without a
  // 100kb library. When it eventually goes away we swap this block for
  // Selection/Range API calls or bring in ProseMirror; the note storage
  // format (sanitised HTML) doesn't change.
  toolbar.addEventListener("mousedown", (e) => {
    // Prevent the toolbar button from stealing focus from the editor —
    // execCommand needs an active selection inside the contenteditable.
    if (e.target.closest(".note-tb-btn")) e.preventDefault();
  });
  toolbar.addEventListener("click", (e) => {
    const btn = e.target.closest(".note-tb-btn");
    if (!btn) return;
    // Undo / Redo — don't checkpoint (they're the ones moving through
    // history); the restore already updates `last`.
    if (btn.dataset.historyUndo) {
      if (_historyUndo(n.id, title, body)) scheduleSave();
      return;
    }
    if (btn.dataset.historyRedo) {
      if (_historyRedo(n.id, title, body)) scheduleSave();
      return;
    }
    body.focus({ preventScroll: true });
    if (btn.dataset.tableInsert) {
      _promptInsertNoteTable(body);
      _historyCheckpoint(n.id, title, body);
      scheduleSave();
      return;
    }
    if (btn.dataset.entityLink) {
      // The caret moves when the picker takes focus, so capture the
      // range NOW and restore it before inserting.
      const sel = document.getSelection();
      const savedRange = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
      _openEntityLinkPicker(savedRange, body, () => {
        _historyCheckpoint(n.id, title, body);
        scheduleSave();
      });
      return;
    }
    const cmd = btn.dataset.cmd;
    let arg = btn.dataset.arg || null;
    // Route indent/outdent through our custom DOM ops so the button
    // and Tab key behave identically (see _indentListItem docstring).
    if (cmd === "indent" || cmd === "outdent") {
      const sel = document.getSelection();
      let node = sel && sel.rangeCount ? sel.anchorNode : null;
      let li = null;
      while (node && node !== body) {
        if (node.nodeType === 1 && node.tagName === "LI") { li = node; break; }
        node = node.parentNode;
      }
      if (li) {
        if (cmd === "outdent") _outdentListItem(li);
        else                   _indentListItem(li);
        _historyCheckpoint(n.id, title, body);
        scheduleSave();
      }
      return;
    }
    if (btn.dataset.link) {
      const url = prompt("Link URL:", "https://");
      if (!url) return;
      arg = url;
    }
    document.execCommand(cmd, false, arg);
    _historyCheckpoint(n.id, title, body);
    scheduleSave();
  });

  // Table interactions (resize + right-click menu) — every table
  // mutation also checkpoints history so Cmd-Z reverts one edit at
  // a time (insert row, resize column, delete table, etc.).
  const onTableChanged = () => {
    _historyCheckpoint(n.id, title, body);
    scheduleSave();
  };
  _wireNoteTables(body, onTableChanged);
  _wireNoteEntityLinks(body, onTableChanged);

  // Font-size input: fires on Enter / blur / arrow-step, not per
  // keystroke — so typing "1"→"12" doesn't apply size 1 first.
  // Selection is captured before the input steals focus, then restored
  // right before wrapping, so the change lands on the text the user
  // last had selected in the editor.
  const fsInput = pane.querySelector("#note-tb-fs");
  if (fsInput) {
    let savedRange = null;
    const captureRange = () => {
      const sel = window.getSelection();
      if (sel && sel.rangeCount && body.contains(sel.anchorNode)) {
        savedRange = sel.getRangeAt(0).cloneRange();
      }
    };
    body.addEventListener("mouseup",  captureRange);
    body.addEventListener("keyup",    captureRange);
    // The mousedown-preserve pattern doesn't work for number inputs
    // (browsers always shift focus), so we cache the range from the
    // editor's own focus events and restore before applying.
    const applyFromInput = () => {
      let px = parseInt(fsInput.value, 10);
      if (!isFinite(px)) return;
      px = Math.max(_NOTE_FONT_SIZE_MIN, Math.min(_NOTE_FONT_SIZE_MAX, px));
      fsInput.value = String(px);
      _restoreCaret(body, savedRange);
      _applyNoteFontSizePx(body, px);
      _historyCheckpoint(n.id, title, body);
      scheduleSave();
    };
    fsInput.addEventListener("change", applyFromInput);
    fsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); applyFromInput(); }
    });
  }

  _wireNoteSettings(pane, () => {
    if (!confirm(`Delete "${state.noteDetail?.title || 'this note'}"? This can't be undone.`)) return;
    deleteNote(n.id);
  });

  // Paste-as-plain-text pathway isn't needed — the server-side
  // sanitiser strips everything not on the allow-list, so pasted rich
  // HTML degrades gracefully to just its surviving tags on the next
  // save round-trip.
}

// ---- Keep your place when a note pops out --------------------------
//
// Popping out a note used to lose the scroll position (2026-09-29). The
// pop-out is a fresh window that loads the note at the
// top. It is also a different width, so text reflows and a pixel offset
// would land somewhere else; the place is recorded as the top-level block
// at the top of the view plus how far into it, which survives reflow.
//
// Which element scrolls differs by layout (the docked editor scrolls
// `.note-body`; the pop-out's workspace may scroll its column instead),
// so both sides look for the nearest scrolling ancestor rather than
// assuming one.

function _noteScrollParent(el) {
  for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
    const oy = getComputedStyle(n).overflowY;
    if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight) return n;
  }
  return document.scrollingElement || document.documentElement;
}

/** {i, f}: index of the first top-level block of `body` still visible at
 *  the top of its scroller, and the fraction of that block scrolled past
 *  (0 at its top edge). null if the note is not scrolled. */
function noteScrollAnchor(body) {
  if (!body || !body.children.length) return null;
  const scroller = _noteScrollParent(body);
  if (!scroller || scroller.scrollTop <= 0) return null;
  const top = scroller.getBoundingClientRect().top;
  const kids = body.children;
  for (let i = 0; i < kids.length; i++) {
    const r = kids[i].getBoundingClientRect();
    if (r.bottom > top) {
      const f = r.height > 0 ? Math.min(1, Math.max(0, (top - r.top) / r.height)) : 0;
      return { i, f: Math.round(f * 1000) / 1000 };
    }
  }
  return null;
}

/** Scroll so block `i` of `body` sits at the top of its scroller, `f` of
 *  the way in. Out-of-range anchors (the note shrank) are ignored. */
function restoreNoteScrollAnchor(body, anchor) {
  if (!body || !anchor || !(anchor.i >= 0)) return;
  const block = body.children[anchor.i];
  if (!block) return;
  const scroller = _noteScrollParent(body);
  const r = block.getBoundingClientRect();
  scroller.scrollTop += (r.top - scroller.getBoundingClientRect().top) + (anchor.f || 0) * r.height;
}
// ---- end keep-your-place

// ---- Note settings dropdown ----------------------------------------
//
// Delete sits behind a settings button that opens a dropdown with a close
// control (2026-09-29); delete is the only option for now. The menu lives
// in the note header's own markup (renderNoteDetail), so it is rebuilt
// with the note and never outlives it. New note-level options go in that
// markup as another `role="menuitem"` button, wired here.
//
// Closes on ×, Escape, or a click outside. `onDelete` runs after the menu
// has closed, so the confirm() dialog is not drawn over an open menu.
function _wireNoteSettings(root, onDelete) {
  const btn   = root.querySelector("#btn-note-settings");
  const menu  = root.querySelector("#note-settings-menu");
  const close = root.querySelector("#btn-note-settings-close");
  const del   = root.querySelector("#btn-note-delete");
  if (!btn || !menu) return;

  function onOutside(e) {
    if (!menu.contains(e.target) && !btn.contains(e.target)) setOpen(false);
  }
  function onKey(e) {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    setOpen(false);
    btn.focus();
  }
  function setOpen(open) {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    // Document-level listeners exist only while the menu is open.
    const method = open ? "addEventListener" : "removeEventListener";
    document[method]("mousedown", onOutside, true);
    document[method]("keydown", onKey, true);
  }

  btn.addEventListener("click", () => setOpen(menu.hidden));
  if (close) close.addEventListener("click", () => setOpen(false));
  if (del) del.addEventListener("click", () => { setOpen(false); onDelete(); });
}
// ---- end note settings dropdown

async function createNote() {
  if (!state.config?.corpus_dir) { toast("pick a corpus dir first", "err"); return; }
  try {
    const n = await api("/api/notes", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body:    JSON.stringify({ title: "Untitled note", body_html: "" }),
    });
    // Push to top of list and select immediately.
    state.notes.unshift({
      id: n.id, title: n.title, created_at: n.created_at,
      updated_at: n.updated_at, snippet: "",
    });
    renderNotes();
    await MODES_BY_ID.notes.select(n.id);   // wrapped: records history
    // Focus the title so the user can start typing right away.
    setTimeout(() => { const t = $("#note-title-input"); if (t) { t.focus(); t.select(); } }, 0);
  } catch (e) {
    toast("new note failed: " + e.message, "err");
  }
}

async function deleteNote(id) {
  try {
    await api(`/api/note/${encodeURIComponent(id)}`, { method: "DELETE" });
    state.notes = state.notes.filter(n => n.id !== id);
    if (state.selectedNoteId === id) {
      state.selectedNoteId = null;
      state.noteDetail = null;
      $("#note-detail").innerHTML = _noteEmptyStateHtml();
    }
    // Drop this note's undo/redo stacks so _noteHistory doesn't grow
    // across a long session as notes come and go.
    _noteHistory.delete(id);
    renderNotes();
    toast("note deleted", "ok");
  } catch (e) {
    toast("delete failed: " + e.message, "err");
  }
}

// --- list indent / outdent ---
//
// Manual DOM manipulation rather than execCommand("indent"/"outdent").
// Reasons:
//   1. execCommand("indent") on the FIRST item of a list wraps the
//      whole list in a <blockquote> instead of creating a nested
//      <ul>/<ol>. That means the marker never cycles.
//   2. execCommand("outdent") in some browsers deletes text nodes it
//      shouldn't.
//   3. Doing it ourselves lets us tag the phantom parent <li> (the
//      empty one that has to exist because <ul> can only contain
//      <li> per HTML spec) so CSS can hide its otherwise-orphaned
//      bullet.
//
// After indent, the DOM looks like:
//   <ul>                       (level 1)
//     <li>A</li>               (prior sibling — parent)
//     <li>                     (moved into A's sub-list)
//       ...                    ← the caret's original <li> lands here
//   -- OR, if there was no prior sibling --
//     <li class="li-phantom">  (empty parent, marker hidden by CSS)
//       <ul>                   (level 2)
//         <li>A</li>           (caret's original <li>)
//       </ul>
//     </li>
//   </ul>
// The CSS selector `.note-body ul ul` catches the level-2 list and
// switches its marker to `circle`. Same idea for ol → lower-alpha.

function _indentListItem(li) {
  const parentList = li.parentNode;
  if (!parentList) return;
  const tag = parentList.tagName;
  if (tag !== "UL" && tag !== "OL") return;

  // Save the current caret so we can restore it after DOM mutation —
  // moving nodes with appendChild would otherwise blow the selection
  // out to some default (usually far-left in the editor).
  const restoreCaret = _saveCaretIn(li);

  const prior = li.previousElementSibling;
  if (prior && prior.tagName === "LI") {
    // Standard case: nest under the prior sibling. Reuse an existing
    // sub-list on that sibling if it already has one, else create one.
    let subList = null;
    for (const child of prior.children) {
      if (child.tagName === tag) { subList = child; break; }
    }
    if (!subList) {
      subList = document.createElement(tag.toLowerCase());
      prior.appendChild(subList);
    }
    subList.appendChild(li);
  } else {
    // First item in its list — no sibling to nest under. Insert a
    // phantom <li> (class="li-phantom", CSS hides its marker) with
    // a fresh sub-list, then move THIS li AND every sibling that
    // follows it into the sub-list. Rationale: tabbing a first
    // item is expected to "make this whole list a sub-list."
    // Indenting just one lone item at the top and leaving the rest
    // flat reads as broken.
    const phantom  = document.createElement("li");
    phantom.className = "li-phantom";
    const subList  = document.createElement(tag.toLowerCase());
    // Collect siblings from THIS li onward before mutating.
    const toMove = [];
    let cursor = li;
    while (cursor) {
      toMove.push(cursor);
      cursor = cursor.nextElementSibling;
    }
    parentList.insertBefore(phantom, li);
    phantom.appendChild(subList);
    for (const item of toMove) subList.appendChild(item);
  }

  restoreCaret();
}

function _outdentListItem(li) {
  const subList = li.parentNode;
  if (!subList) return;
  const subTag = subList.tagName;
  if (subTag !== "UL" && subTag !== "OL") return;
  const parentLi = subList.parentNode;

  // True top-level case: no wrapping <li> to escape from. Do nothing —
  // outdenting at the highest tier should not destroy the list.
  if (!parentLi || parentLi.tagName !== "LI") return;

  // Phantom-wrapped case: the phantom was created by an "indent first
  // item" (visually: "indent the whole list by one notch"). Its mirror
  // is "outdent from within → undo the phantom entirely." Promote every
  // sub-list item to be a sibling of the phantom, then remove the
  // phantom + its now-empty sub-list. Without this branch, outdenting
  // any item in a phantom-wrapped list would move that item alone out
  // one level and leave the others behind — reads as broken because
  // visually all the items look top-tier (the phantom marker is hidden).
  if (parentLi.classList.contains("li-phantom")) {
    _unwrapPhantom(parentLi, subList, li);
    return;
  }

  const grandparent = parentLi.parentNode;
  if (!grandparent) return;
  const restoreCaret = _saveCaretIn(li);
  // Regular nested case — move just this one item out one level.
  grandparent.insertBefore(li, parentLi.nextSibling);
  // Cleanup: only remove the sub-list AND its parent li if the sub-list
  // is now actually empty. Previous version short-circuited on
  // `.li-phantom` regardless of remaining children, which deleted any
  // siblings still living inside the phantom's sub-list.
  if (subList.children.length === 0) {
    subList.remove();
    if (parentLi.children.length === 0 && !parentLi.textContent.trim()) {
      parentLi.remove();
    }
  }
  restoreCaret();
}

// Undo a phantom wrapper: move every <li> child of the phantom's
// sub-list to sit as a sibling of the phantom (in order), then remove
// the phantom. This is the mirror of `_indentListItem`'s "wrap all
// siblings in phantom sub-list" branch — after this, the DOM state
// matches what it was BEFORE that indent.
function _unwrapPhantom(phantom, subList, caretLi) {
  const outerList = phantom.parentNode;
  if (!outerList) return;
  const restoreCaret = _saveCaretIn(caretLi);
  const anchor = phantom.nextSibling;
  for (const item of Array.from(subList.children)) {
    if (item.tagName === "LI") outerList.insertBefore(item, anchor);
  }
  phantom.remove();
  restoreCaret();
}


// Save the current caret position IF it's inside `container`. Returns
// a restore() function that puts the selection back after DOM mutation
// (works because moving a node via appendChild keeps its child text
// nodes attached — the saved Range's endpoints stay valid).
function _saveCaretIn(container) {
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0) return () => {};
  const r = sel.getRangeAt(0);
  // Only save if both endpoints are inside `container` — otherwise
  // the selection spans elements we're about to move around and
  // restoration would land in the wrong place.
  if (!container.contains(r.startContainer) || !container.contains(r.endContainer)) {
    return () => {};
  }
  const startContainer = r.startContainer;
  const startOffset    = r.startOffset;
  const endContainer   = r.endContainer;
  const endOffset      = r.endOffset;
  return () => {
    try {
      const range = document.createRange();
      range.setStart(startContainer, startOffset);
      range.setEnd(endContainer, endOffset);
      const s = document.getSelection();
      if (s) { s.removeAllRanges(); s.addRange(range); }
    } catch (_) {
      // Range invalidated (e.g. text node was rewritten). Best-effort;
      // browser will place the caret somewhere reasonable.
    }
  };
}

// --- per-note undo / redo history (session-scoped) ---
// In-memory map, never persisted, so it resets naturally on page
// reload / app close. Each note gets its own undo + redo stack:
//   * typing coalesces into one entry per ~500ms pause
//   * every toolbar / table operation creates one explicit entry
//   * undo pops from undo → push current to redo → restore
//   * redo pops from redo → push current to undo → restore
//   * a new edit after an undo clears the redo stack
const _noteHistory = new Map();  // noteId → history record

function _historyFor(id) {
  if (!_noteHistory.has(id)) {
    _noteHistory.set(id, {
      undo: [], redo: [],
      last: null,          // last-known committed state; snapshotted before next change
      pending: null,       // debounce timer for typing coalescence
      isRestoring: false,  // set while we're mid-restore so input event doesn't loop
    });
  }
  return _noteHistory.get(id);
}

function _snapshotEditor(title, body) {
  return { title: title.value, body_html: body.innerHTML };
}

function _statesEqual(a, b) {
  return !!a && !!b && a.title === b.title && a.body_html === b.body_html;
}

function _historyInit(noteId, title, body) {
  const h = _historyFor(noteId);
  if (!h.last) h.last = _snapshotEditor(title, body);
}

function _historyCommitPending(noteId, title, body) {
  const h = _historyFor(noteId);
  if (!h.pending) return;
  clearTimeout(h.pending);
  h.pending = null;
  const cur = _snapshotEditor(title, body);
  if (!h.last || _statesEqual(cur, h.last)) { h.last = cur; return; }
  h.undo.push(h.last);
  if (h.undo.length > 200) h.undo.shift();
  h.redo.length = 0;
  h.last = cur;
}

function _historyOnEdit(noteId, title, body) {
  const h = _historyFor(noteId);
  if (h.isRestoring) return;
  if (h.pending) clearTimeout(h.pending);
  if (!h.last) h.last = _snapshotEditor(title, body);
  h.pending = setTimeout(() => _historyCommitPending(noteId, title, body), 500);
}

function _historyCheckpoint(noteId, title, body) {
  const h = _historyFor(noteId);
  if (h.isRestoring) return;
  if (h.pending) { clearTimeout(h.pending); h.pending = null; }
  const cur = _snapshotEditor(title, body);
  if (!h.last) { h.last = cur; return; }
  if (_statesEqual(cur, h.last)) return;
  h.undo.push(h.last);
  if (h.undo.length > 200) h.undo.shift();
  h.redo.length = 0;
  h.last = cur;
}

function _historyRestore(h, snap, title, body) {
  h.isRestoring = true;
  title.value = snap.title;
  body.innerHTML = snap.body_html;
  h.last = snap;
  h.isRestoring = false;
}

function _historyUndo(noteId, title, body) {
  const h = _historyFor(noteId);
  // Flush any pending edit into undo first, so Cmd-Z after typing
  // reverts the just-typed burst rather than nothing.
  if (h.pending) _historyCommitPending(noteId, title, body);
  if (!h.undo.length) return false;
  const cur = _snapshotEditor(title, body);
  h.redo.push(cur);
  _historyRestore(h, h.undo.pop(), title, body);
  return true;
}

function _historyRedo(noteId, title, body) {
  const h = _historyFor(noteId);
  if (h.pending) _historyCommitPending(noteId, title, body);
  if (!h.redo.length) return false;
  const cur = _snapshotEditor(title, body);
  h.undo.push(cur);
  _historyRestore(h, h.redo.pop(), title, body);
  return true;
}

// --- font-size wrapping ---
// execCommand("fontSize") uses the legacy 1-7 HTML-font scale and
// produces <font size="N"> which we don't want. Instead: wrap the
// current Range in a <span style="font-size: Npx"> — inline style,
// arbitrary px value, sanitiser allow-lists font-size on span and
// clamps to the [_NOTE_FONT_SIZE_MIN, _NOTE_FONT_SIZE_MAX] range.
// If nothing is selected, insert an empty span at the caret so the
// next typed characters inherit the size.

function _applyNoteFontSizePx(root, px) {
  if (!isFinite(px) || px < _NOTE_FONT_SIZE_MIN || px > _NOTE_FONT_SIZE_MAX) return;
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return;
  const range = sel.getRangeAt(0);
  const span = document.createElement("span");
  span.style.fontSize = `${px}px`;
  if (range.collapsed) {
    span.appendChild(document.createTextNode("​")); // zero-width space
    range.insertNode(span);
    const r = document.createRange();
    r.setStart(span.firstChild, 1);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    return;
  }
  try {
    span.appendChild(range.extractContents());
    range.insertNode(span);
    const r = document.createRange();
    r.selectNodeContents(span);
    sel.removeAllRanges();
    sel.addRange(r);
  } catch (e) { /* selection spans odd boundaries — noop */ }
}

// --- tables ---
// Model: a <table class="note-table"> with a <colgroup> that owns
// per-column widths (px), <tr>s that own per-row heights (px) via
// their inline style, and empty <td><br></td> cells. The table's own
// style holds total width (kept in sync with sum of col widths so
// browsers with fixed table-layout don't collapse cells).
//
// Interactions (Excel-style, no visible handles — cursor tells the
// user what will happen):
//   * cursor near the table's RIGHT edge → col-resize whole table
//   * cursor near the BOTTOM edge → row-resize whole table
//   * near the bottom-right CORNER → proportional both
//   * in the TOP ROW, near a cell's right border → resize that column
//   * in the LEFT COLUMN, near a cell's bottom border → resize that row
//
// Right-click a cell for insert/delete row/column and delete-table.

const _NOTE_TABLE_EDGE_PX = 6;       // proximity zone for the resize cursor
const _NOTE_TABLE_MIN_CELL = 24;      // don't let a col/row shrink below this
const _NOTE_TABLE_MAX_TOTAL = 4000;   // matches server sanitiser cap

function _promptInsertNoteTable(body) {
  const rowsIn = prompt("Rows?", "3");
  if (rowsIn == null) return;
  const colsIn = prompt("Columns?", "3");
  if (colsIn == null) return;
  const rows = Math.max(1, Math.min(50, parseInt(rowsIn, 10) || 0));
  const cols = Math.max(1, Math.min(20, parseInt(colsIn, 10) || 0));
  if (!rows || !cols) return;
  _insertNoteTable(body, rows, cols);
}

function _insertNoteTable(body, rows, cols) {
  // Pick a starting total width sized for the editor. Default 480px
  // divided evenly; row height 32px.
  const totalW = 480;
  const colW = Math.floor(totalW / cols);
  const rowH = 32;

  const table = document.createElement("table");
  table.className = "note-table";
  table.style.width = `${colW * cols}px`;

  const colgroup = document.createElement("colgroup");
  for (let c = 0; c < cols; c++) {
    const col = document.createElement("col");
    col.style.width = `${colW}px`;
    colgroup.appendChild(col);
  }
  table.appendChild(colgroup);

  const tbody = document.createElement("tbody");
  for (let r = 0; r < rows; r++) {
    const tr = document.createElement("tr");
    tr.style.height = `${rowH}px`;
    for (let c = 0; c < cols; c++) {
      const td = document.createElement("td");
      td.appendChild(document.createElement("br"));  // makes empty cell clickable
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  // Insert at caret if we have one in the body, else append.
  const sel = window.getSelection();
  let inserted = false;
  if (sel && sel.rangeCount && body.contains(sel.anchorNode)) {
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(table);
    inserted = true;
  }
  if (!inserted) body.appendChild(table);

  // Add a trailing empty paragraph so the caret has somewhere to land
  // below the table (otherwise contenteditable can trap it inside).
  const trailer = document.createElement("p");
  trailer.appendChild(document.createElement("br"));
  table.parentNode.insertBefore(trailer, table.nextSibling);

  // Move caret into first cell.
  const firstCell = table.querySelector("td");
  if (firstCell) {
    const r = document.createRange();
    r.selectNodeContents(firstCell);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
  }
}

// Detect which resize zone (if any) the cursor is over, given a mouse
// event and the table element. Returns null (no zone) or an object
// { mode: "table-h"|"table-v"|"table-corner"|"col"|"row", idx?, ... }.
function _noteTableHitTest(e, table) {
  const r = table.getBoundingClientRect();
  const x = e.clientX, y = e.clientY;
  const E = _NOTE_TABLE_EDGE_PX;
  // Bottom-right corner — must be inside the outer proximity zone
  // AND near both edges. Prioritised so corner drags aren't stolen
  // by the individual edge branches.
  if (Math.abs(x - r.right) <= E && Math.abs(y - r.bottom) <= E) {
    return { mode: "table-corner" };
  }
  if (Math.abs(x - r.right) <= E && y >= r.top && y <= r.bottom) {
    return { mode: "table-h" };
  }
  if (Math.abs(y - r.bottom) <= E && x >= r.left && x <= r.right) {
    return { mode: "table-v" };
  }
  // Individual column border — cursor in TOP ROW, near a cell's right border.
  const topRow = table.querySelector("tr");
  if (topRow) {
    const tr = topRow.getBoundingClientRect();
    if (y >= tr.top && y <= tr.bottom) {
      const cells = topRow.children;
      for (let i = 0; i < cells.length - 1; i++) {
        const cr = cells[i].getBoundingClientRect();
        if (Math.abs(x - cr.right) <= E) return { mode: "col", idx: i };
      }
    }
  }
  // Individual row border — cursor in LEFT COLUMN, near a cell's bottom border.
  const rows = table.querySelectorAll("tr");
  if (rows.length) {
    const firstCellRect = rows[0].firstElementChild?.getBoundingClientRect();
    if (firstCellRect && x >= firstCellRect.left && x <= firstCellRect.right) {
      for (let i = 0; i < rows.length - 1; i++) {
        const cell = rows[i].firstElementChild;
        if (!cell) continue;
        const cr = cell.getBoundingClientRect();
        if (Math.abs(y - cr.bottom) <= E) return { mode: "row", idx: i };
      }
    }
  }
  return null;
}

function _cursorForMode(mode) {
  switch (mode) {
    case "table-corner": return "nwse-resize";
    case "table-h":
    case "col":          return "col-resize";
    case "table-v":
    case "row":          return "row-resize";
  }
  return "";
}

function _wireNoteTables(body, onChanged) {
  // Set cursor on move over any table in the editor.
  body.addEventListener("mousemove", (e) => {
    const table = e.target.closest("table.note-table");
    if (!table) { body.style.cursor = ""; return; }
    const hit = _noteTableHitTest(e, table);
    body.style.cursor = _cursorForMode(hit?.mode) || "";
  });
  body.addEventListener("mouseleave", () => { body.style.cursor = ""; });

  // Start a drag on mousedown if we're in a resize zone.
  body.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const table = e.target.closest("table.note-table");
    if (!table) return;
    const hit = _noteTableHitTest(e, table);
    if (!hit) return;
    e.preventDefault();
    _startNoteTableResize(e, table, hit, onChanged);
  });

  // Right-click inside a table cell → context menu.
  body.addEventListener("contextmenu", (e) => {
    const cell = e.target.closest("td, th");
    if (!cell || !cell.closest("table.note-table")) return;
    e.preventDefault();
    _showNoteTableContextMenu(e, cell, onChanged);
  });
}

function _startNoteTableResize(e, table, hit, onChanged) {
  const cols = Array.from(table.querySelectorAll("colgroup > col"));
  const rows = Array.from(table.querySelectorAll("tr"));
  const origColW = cols.map(c => parseFloat(c.style.width) || c.getBoundingClientRect().width);
  const origRowH = rows.map(r => parseFloat(r.style.height) || r.getBoundingClientRect().height);
  const origTotalW = origColW.reduce((a, b) => a + b, 0);
  const origTotalH = origRowH.reduce((a, b) => a + b, 0);
  const startX = e.clientX, startY = e.clientY;

  const doMove = (ev) => {
    const dx = ev.clientX - startX;
    const dy = ev.clientY - startY;
    if (hit.mode === "table-h" || hit.mode === "table-corner") {
      const newW = Math.max(cols.length * _NOTE_TABLE_MIN_CELL,
                     Math.min(_NOTE_TABLE_MAX_TOTAL, origTotalW + dx));
      const scale = newW / origTotalW;
      cols.forEach((c, i) => { c.style.width = `${Math.max(_NOTE_TABLE_MIN_CELL, origColW[i] * scale)}px`; });
      table.style.width = `${newW}px`;
    }
    if (hit.mode === "table-v" || hit.mode === "table-corner") {
      const newH = Math.max(rows.length * _NOTE_TABLE_MIN_CELL,
                     Math.min(_NOTE_TABLE_MAX_TOTAL, origTotalH + dy));
      const scale = newH / origTotalH;
      rows.forEach((r, i) => { r.style.height = `${Math.max(_NOTE_TABLE_MIN_CELL, origRowH[i] * scale)}px`; });
    }
    if (hit.mode === "col") {
      // Only the dragged column changes; total width shifts by dx.
      const newColW = Math.max(_NOTE_TABLE_MIN_CELL, origColW[hit.idx] + dx);
      cols[hit.idx].style.width = `${newColW}px`;
      table.style.width = `${origTotalW - origColW[hit.idx] + newColW}px`;
    }
    if (hit.mode === "row") {
      const newRowH = Math.max(_NOTE_TABLE_MIN_CELL, origRowH[hit.idx] + dy);
      rows[hit.idx].style.height = `${newRowH}px`;
    }
  };
  const doUp = () => {
    document.removeEventListener("mousemove", doMove);
    document.removeEventListener("mouseup",   doUp);
    onChanged();
  };
  document.addEventListener("mousemove", doMove);
  document.addEventListener("mouseup",   doUp);
}

// --- Table right-click context menu ---
// Renders a floating menu at the click point. Actions operate on the
// cell right-clicked. Menu auto-dismisses on any outside click or Esc.
let _noteTableMenu = null;
function _dismissNoteTableMenu() {
  if (_noteTableMenu) { _noteTableMenu.remove(); _noteTableMenu = null; }
}
// Generic popup menu used by BOTH the table context menu and the
// entity-link context menu. Extracted when links were added rather
// than copied — the two menus differ only in their action list, and a
// second copy of the build/position/dismiss logic would drift.
//
// `actions` items: {label, fn} or {sep: true}; `danger: true` tints one
// red. Returns nothing; the menu closes on click, Escape, or an
// outside click (handlers registered once, below).
function _showNoteMenu(clientX, clientY, actions, onChanged) {
  _dismissNoteTableMenu();
  const menu = document.createElement("div");
  menu.className = "note-table-menu";
  menu.style.left = `${clientX}px`;
  menu.style.top  = `${clientY}px`;
  actions.forEach(a => {
    if (a.sep) {
      const sep = document.createElement("div");
      sep.className = "note-table-menu-sep";
      menu.appendChild(sep);
      return;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "note-table-menu-item" + (a.danger ? " note-table-menu-item-danger" : "");
    btn.textContent = a.label;
    btn.addEventListener("click", () => {
      _dismissNoteTableMenu();
      a.fn();
      if (onChanged) onChanged();
    });
    menu.appendChild(btn);
  });
  document.body.appendChild(menu);
  _noteTableMenu = menu;
  // Clip to viewport.
  const mr = menu.getBoundingClientRect();
  if (mr.right > window.innerWidth)  menu.style.left = `${window.innerWidth  - mr.width  - 4}px`;
  if (mr.bottom > window.innerHeight) menu.style.top  = `${window.innerHeight - mr.height - 4}px`;
}

function _showNoteTableContextMenu(e, cell, onChanged) {
  const table = cell.closest("table.note-table");
  const tr = cell.parentElement;
  const rowIdx = Array.prototype.indexOf.call(tr.parentElement.children, tr);
  const colIdx = Array.prototype.indexOf.call(tr.children, cell);
  _showNoteMenu(e.clientX, e.clientY, [
    { label: "Insert row above",    fn: () => _tableInsertRow(table, rowIdx) },
    { label: "Insert row below",    fn: () => _tableInsertRow(table, rowIdx + 1) },
    { label: "Insert column left",  fn: () => _tableInsertCol(table, colIdx) },
    { label: "Insert column right", fn: () => _tableInsertCol(table, colIdx + 1) },
    { sep: true },
    { label: "Delete row",          fn: () => _tableDeleteRow(table, rowIdx) },
    { label: "Delete column",       fn: () => _tableDeleteCol(table, colIdx) },
    { sep: true },
    { label: "Delete table",        fn: () => table.remove(), danger: true },
  ], onChanged);
}
document.addEventListener("click", (e) => {
  if (!_noteTableMenu) return;
  if (_noteTableMenu.contains(e.target)) return;
  _dismissNoteTableMenu();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") _dismissNoteTableMenu();
});

function _tableInsertRow(table, idx) {
  const tbody = table.querySelector("tbody") || table;
  const rows = tbody.querySelectorAll("tr");
  const cols = table.querySelectorAll("colgroup > col").length ||
               (rows[0]?.children.length || 1);
  const tr = document.createElement("tr");
  // Copy height of an adjacent row if available.
  const template = rows[Math.min(idx, rows.length - 1)] || rows[0];
  if (template) tr.style.height = template.style.height || "32px";
  for (let c = 0; c < cols; c++) {
    const td = document.createElement("td");
    td.appendChild(document.createElement("br"));
    tr.appendChild(td);
  }
  if (idx >= rows.length) tbody.appendChild(tr);
  else                     tbody.insertBefore(tr, rows[idx]);
}

function _tableInsertCol(table, idx) {
  const colgroup = table.querySelector("colgroup");
  const cols     = colgroup ? Array.from(colgroup.children) : [];
  // New col inherits width of an adjacent col.
  const template = cols[Math.min(idx, cols.length - 1)] || cols[0];
  const w = template ? (parseFloat(template.style.width) || 100) : 100;
  const col = document.createElement("col");
  col.style.width = `${w}px`;
  if (colgroup) {
    if (idx >= cols.length) colgroup.appendChild(col);
    else                     colgroup.insertBefore(col, cols[idx]);
  }
  // Add a td in each row at the same index.
  table.querySelectorAll("tr").forEach(tr => {
    const td = document.createElement("td");
    td.appendChild(document.createElement("br"));
    if (idx >= tr.children.length) tr.appendChild(td);
    else                            tr.insertBefore(td, tr.children[idx]);
  });
  // Update table total width.
  const total = Array.from(table.querySelectorAll("colgroup > col"))
    .reduce((a, c) => a + (parseFloat(c.style.width) || 0), 0);
  if (total) table.style.width = `${total}px`;
}

function _tableDeleteRow(table, idx) {
  const rows = table.querySelectorAll("tr");
  if (rows.length <= 1) { table.remove(); return; }
  rows[idx]?.remove();
}

function _tableDeleteCol(table, idx) {
  const colgroup = table.querySelector("colgroup");
  const cols     = colgroup ? colgroup.children : [];
  if (cols.length <= 1) { table.remove(); return; }
  cols[idx]?.remove();
  table.querySelectorAll("tr").forEach(tr => tr.children[idx]?.remove());
  const total = Array.from(table.querySelectorAll("colgroup > col"))
    .reduce((a, c) => a + (parseFloat(c.style.width) || 0), 0);
  if (total) table.style.width = `${total}px`;
}


// ---------- Entity links ----------
//
// A note can link to a paper / author / institution / journal. The link
// is an ordinary <a> carrying `data-open-<type>="<id>"` — the SAME
// attribute the detail panes emit, so app.js's existing deep-link
// handler navigates it with no new routing. The set of linkable types
// comes from `window.LINKABLE_MODES` (the MODES entries declaring
// `linkAttr`); nothing here keeps its own list.
//
// The sanitiser must preserve these attributes or links die silently on
// reload — see `_NOTE_LINK_DATA_ATTRS` in python/notes_api.py and the
// parity test that keeps the two lists together.

let _entityPicker = null;

function _dismissEntityPicker() {
  if (_entityPicker) { _entityPicker.remove(); _entityPicker = null; }
}

function _linkableModes() {
  return Array.isArray(window.LINKABLE_MODES) ? window.LINKABLE_MODES : [];
}

/** Build the <a> for one entity. Kept separate so tests can exercise
 *  the markup without a DOM selection. */
function _entityLinkHtml(mode, id, label) {
  return `<a href="#" class="note-entity-link" ` +
         `data-open-${mode.linkAttr}="${escAttr(id)}">${escHtml(label)}</a>`;
}

/** A link to one highlight inside a paper or a document.
 *
 *  Carries BOTH `data-open-<kind>` and `data-open-highlight`. The kind
 *  attribute is what makes it degrade well: anywhere that does not
 *  understand highlights (the docked view, an older build) it is just
 *  an ordinary paper / document link, and a highlight that has since
 *  been deleted still opens its PDF. `kind` is "paper" or "document"
 *  (documents 2026-09-25) — a document's highlight id means nothing
 *  under a paper slug.
 */
function _highlightLinkHtml(kind, id, highlightId, label) {
  return `<a href="#" class="note-entity-link" ` +
         `data-open-${kind === "document" ? "document" : "paper"}="${escAttr(id)}" ` +
         `data-open-highlight="${escAttr(highlightId)}">${escHtml(label)}</a>`;
}

/** Give the editor focus back and put the caret where it was, WITHOUT
 *  scrolling.
 *
 *  Adding a paper via a link used to scroll the note to the top
 *  (2026-09-25). A picker or input had taken focus; a plain
 *  focus call with no options scrolls the editor to where the browser puts a fresh
 *  caret — the top — before the saved range is restored, so a link
 *  added at the bottom of a long note left the view at its first line.
 *  One helper for every caller that hands focus back, so no copy of the
 *  pattern keeps the old behaviour. */
function _restoreCaret(body, savedRange) {
  body.focus({ preventScroll: true });
  if (savedRange) {
    const sel = document.getSelection();
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }
}

function _insertHighlightLink(body, savedRange, kind, slug, highlightId, text) {
  _restoreCaret(body, savedRange);
  // The highlight's own text is the label — that is the "linked full
  // quote". Falls back to the slug when the viewer
  // could not read any text for it.
  const label = (text || "").trim() || slug;
  document.execCommand("insertHTML", false,
                       _highlightLinkHtml(kind, slug, highlightId, label) + "&nbsp;");
}

// The link picker's sort choice per type, e.g. {papers: {key: "added_at",
// dir: "desc"}}. A per-viewer convenience, so browser storage; every
// access is guarded because storage can be unavailable.
const _LINK_SORT_KEY = "corpus.linkPickerSort";
function _linkSortPrefs() {
  try { return JSON.parse(localStorage.getItem(_LINK_SORT_KEY) || "{}") || {}; }
  catch (_) { return {}; }
}
function _saveLinkSortPrefs(prefs) {
  try { localStorage.setItem(_LINK_SORT_KEY, JSON.stringify(prefs)); } catch (_) {}
}

function _openEntityLinkPicker(savedRange, body, onInserted) {
  _dismissEntityPicker();
  const modes = _linkableModes();
  if (!modes.length) { toast("No linkable entities available"); return; }

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay note-link-overlay";
  overlay.innerHTML = `
    <div class="modal note-link-modal">
      <header class="modal-header">
        <h2>Insert link</h2>
        <button class="btn ghost" data-close="1">✕</button>
      </header>
      <div class="modal-body">
        <div class="note-link-types"></div>
        <div class="note-link-controls">
          <input type="search" class="note-link-filter" placeholder="Filter…">
          <label class="note-link-sort-label">Sort by
            <select class="note-link-sort"></select>
          </label>
          <button type="button" class="btn note-link-sort-dir" aria-label="Sort direction">↑</button>
        </div>
        <ol class="note-link-results"></ol>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  _entityPicker = overlay;

  const typesEl   = overlay.querySelector(".note-link-types");
  const filterEl  = overlay.querySelector(".note-link-filter");
  const resultsEl = overlay.querySelector(".note-link-results");
  const sortEl    = overlay.querySelector(".note-link-sort");
  const dirEl     = overlay.querySelector(".note-link-sort-dir");
  let active = modes[0];

  // Sort choice per type, remembered across pickers (2026-09-28),
  // e.g. most recently added papers first. Options come
  // from each MODES entry's `sorts` (the same list as the Papers sidebar).
  const prefs = _linkSortPrefs();
  const sortFor = (m) => {
    const saved = prefs[m.id];
    if (saved && Sorting.spec(m.sorts, saved.key)) return saved;
    const key = ((m.sorts || [])[0] || {}).key;
    return { key, dir: Sorting.defaultDir(m.sorts, key) };
  };
  const showSort = () => {
    const cur = sortFor(active);
    sortEl.innerHTML = (active.sorts || [])
      .map(o => `<option value="${escAttr(o.key)}">${escHtml(o.label)}</option>`).join("");
    sortEl.value = cur.key;
    dirEl.textContent = cur.dir === "desc" ? "↓" : "↑";
    sortEl.parentElement.hidden = dirEl.hidden = !(active.sorts || []).length;
  };
  const setSort = (next) => {
    prefs[active.id] = next;
    _saveLinkSortPrefs(prefs);
    showSort();
    renderResults();
  };
  sortEl.addEventListener("change", () =>
    // A new field starts in its natural direction: newest first for dates,
    // most first for counts, A→Z for names.
    setSort({ key: sortEl.value, dir: Sorting.defaultDir(active.sorts, sortEl.value) }));
  dirEl.addEventListener("click", () => {
    const cur = sortFor(active);
    setSort({ key: cur.key, dir: cur.dir === "desc" ? "asc" : "desc" });
  });

  const insert = (id, label) => {
    _dismissEntityPicker();
    // Restore the caret the picker stole, then insert. Without this the
    // link lands wherever the browser last had focus.
    _restoreCaret(body, savedRange);
    document.execCommand("insertHTML", false,
                         _entityLinkHtml(active, id, label) + "&nbsp;");
    if (onInserted) onInserted();
  };

  const renderResults = () => {
    const q = (filterEl.value || "").trim().toLowerCase();
    const rows = (state[active.stateKey] || []);
    // Filter on the ROW, not the rendered label: `modeRowMatches` reads
    // fields the label doesn't show (a paper's author, an author's
    // institution). Filtering the label alone meant typing an author
    // name here matched nothing — the same defect the
    // project member picker had on 2026-09-14.
    // Sort BEFORE the 200-row cap, or "newest first" would only reorder
    // whichever 200 rows happened to come first.
    const cur = sortFor(active);
    const items = Sorting.sortRows(active.sorts, rows.filter(r => modeRowMatches(active, r, q)),
                                   cur.key, cur.dir)
      .map(r => ({ id: active.linkId(r), label: active.linkLabel(r) }))
      .filter(x => x.id)
      .slice(0, 200);
    if (!items.length) {
      resultsEl.innerHTML = `<li class="muted note-link-empty">${
        rows.length ? "No matches." : "Nothing to link to yet."}</li>`;
      return;
    }
    resultsEl.innerHTML = items.map(x =>
      `<li><button type="button" class="note-link-hit" data-id="${escAttr(x.id)}"
           >${escHtml(x.label)}</button></li>`).join("");
    resultsEl.querySelectorAll(".note-link-hit").forEach(btn => {
      btn.addEventListener("click", () => insert(btn.dataset.id, btn.textContent));
    });
  };

  const selectType = async (m) => {
    active = m;
    typesEl.querySelectorAll("button").forEach(b =>
      b.classList.toggle("active", b.dataset.mode === m.id));
    showSort();
    // Show what this window already has at once, then refetch: the list
    // may be stale (a paper imported from another window never reaches a
    // popped-out note's state) or never loaded (lazy tabs). See
    // app.js::fetchModeList.
    if ((state[m.stateKey] || []).length) renderResults();
    else resultsEl.innerHTML = `<li class="muted note-link-empty">Loading…</li>`;
    try { await fetchModeList(m); } catch (_) { /* keep what is shown */ }
    // The user may have switched type or closed the picker meanwhile.
    if (active === m && _entityPicker === overlay) renderResults();
  };

  typesEl.innerHTML = modes.map(m =>
    `<button type="button" class="btn note-link-type" data-mode="${escAttr(m.id)}"
      >${escHtml(m.linkNoun)}</button>`).join("");
  typesEl.querySelectorAll("button").forEach(b =>
    b.addEventListener("click", () => selectType(MODES_BY_ID[b.dataset.mode])));

  filterEl.addEventListener("input", renderResults);
  overlay.querySelector('[data-close="1"]').addEventListener("click", _dismissEntityPicker);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) _dismissEntityPicker(); });

  selectType(active).then(() => filterEl.focus());
}

/** Right-click an entity link in the editor: jump to it, or unlink. */
function _wireNoteEntityLinks(body, onChanged) {
  body.addEventListener("contextmenu", (e) => {
    const modes = _linkableModes();
    const hit = modes
      .map(m => ({ m, el: e.target.closest(`a[data-open-${m.linkAttr}]`) }))
      .find(x => x.el);
    if (!hit) return;
    e.preventDefault();
    const id = hit.el.getAttribute(`data-open-${hit.m.linkAttr}`);
    _showNoteMenu(e.clientX, e.clientY, [
      { label: `Go to ${hit.m.linkNoun}`, fn: () => {
          switchMode(hit.m.id);
          hit.m.select(id);
        } },
      { sep: true },
      { label: "Remove link", danger: true, fn: () => {
          // Unwrap rather than delete — the words stay, the link goes.
          const parent = hit.el.parentNode;
          while (hit.el.firstChild) parent.insertBefore(hit.el.firstChild, hit.el);
          parent.removeChild(hit.el);
          if (onChanged) onChanged();
        } },
    ]);
  });
}
