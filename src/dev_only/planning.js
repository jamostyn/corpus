// DEV-ONLY Planning page. NOT shipped.
//
// Adds a "📋 Planning" button to the topbar. Clicking opens a modal
// with the task list from ~/.corpus/planning.json.

// Register this modal's overlay selector with app.js's Modals registry
// so arrow-key sidebar-nav yields while the planning modal is open.
// In shipped builds, this file is not loaded, so app.js never sees
// this dev-only class name.
if (window.Modals) window.Modals.watchSelector(".dev-plan-modal-overlay");
//
// Interactions:
//   * Type in the "add task" input and hit Enter → new task at TOP.
//   * Click title text → inline-edit (contenteditable). Enter or blur
//     saves; Esc reverts.
//   * Click checkbox → toggle done. Done rows get strikethrough.
//   * Drag the ⋮⋮ handle to reorder → priority.
//   * ▲ / ▼ buttons also nudge one slot at a time (keyboard-friendly
//     fallback when drag is fiddly).
//   * Delete button removes.
//
// After every mutation the full new list POSTs to /api/dev/planning.
// Server truth-check + save; response reflects back into local state.

(function () {
  "use strict";

  function addButton() {
    const topbar = document.querySelector(".topbar");
    if (!topbar) return;
    if (document.getElementById("dev-plan-btn")) return;
    const btn = document.createElement("button");
    btn.id = "dev-plan-btn";
    btn.className = "btn";
    btn.textContent = "Planning";
    btn.title = "DEV-ONLY — task list with drag-reorder priority";
    btn.addEventListener("click", openModal);
    // Insert next to the other dev-only buttons (tooltip editor) —
    // before settings. Only use candidates that actually live in the
    // topbar (the bug button is now a body-level floating pill, so
    // `insertBefore` would throw NotFoundError against it).
    const candidates = ["dev-tt-btn", "btn-settings"];
    let anchor = null;
    for (const id of candidates) {
      const el = document.getElementById(id);
      if (el && el.parentNode === topbar) { anchor = el; break; }
    }
    if (anchor) topbar.insertBefore(btn, anchor);
    else topbar.appendChild(btn);
  }

  let currentModal = null;
  let tasks = [];              // in-modal working copy
  let savePending = null;      // pending debounced save timer

  function nowIso() { return new Date().toISOString(); }
  function newId()  { return "t-" + Math.random().toString(36).slice(2, 9); }
  // Placeholder shown in-place when a task's description is empty.
  const DESC_PLACEHOLDER = "add details…";

  async function openModal() {
    if (currentModal) return;
    // Fetch fresh from server so the modal reflects on-disk truth
    // (edits from other sessions / hand-edits to the JSON file).
    try {
      const r = await fetch("/api/dev/planning");
      const body = await r.json();
      tasks = Array.isArray(body.tasks) ? body.tasks : [];
    } catch (_) {
      tasks = [];
    }

    const overlay = document.createElement("div");
    overlay.className = "dev-plan-modal-overlay";
    overlay.innerHTML = `
      <div class="dev-plan-modal">
        <header>
          <h2>Planning</h2>
          <span class="dev-tag">DEV ONLY</span>
          <button class="btn ghost" data-act="close">✕</button>
        </header>
        <div class="toolbar">
          <input type="text" placeholder="add a task and hit Enter…" id="plan-add-input" autofocus>
          <button class="btn" data-act="clear-done">Clear done</button>
        </div>
        <div class="body" id="plan-body"></div>
        <footer>
          <span class="counts" id="plan-counts"></span>
          <button class="btn" data-act="close">Done</button>
        </footer>
      </div>
    `;
    document.body.appendChild(overlay);
    currentModal = overlay;
    renderList();

    // Add-task input.
    const addInput = overlay.querySelector("#plan-add-input");
    addInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const title = addInput.value.trim();
        if (!title) return;
        tasks.unshift({ id: newId(), title, description: "", done: false, created_at: nowIso(), updated_at: nowIso() });
        addInput.value = "";
        renderList();
        scheduleSave();
      }
    });

    // Modal-level click dispatch (close / clear-done).
    overlay.addEventListener("click", (e) => {
      const act = e.target.dataset && e.target.dataset.act;
      if (act === "close") closeModal();
      if (act === "clear-done") {
        const before = tasks.length;
        tasks = tasks.filter(t => !t.done);
        if (tasks.length !== before) { renderList(); scheduleSave(); }
      }
    });

    document.addEventListener("keydown", escToClose);
  }

  function renderList() {
    const body = currentModal.querySelector("#plan-body");
    if (!tasks.length) {
      body.innerHTML = `<div class="empty">no tasks yet — add one above</div>`;
    } else {
      body.innerHTML = tasks.map((t, i) => renderRow(t, i)).join("");
    }
    // Counts + drag events.
    const done = tasks.filter(t => t.done).length;
    currentModal.querySelector("#plan-counts").textContent =
      `${tasks.length} task${tasks.length === 1 ? "" : "s"} · ${done} done`;
    wireRowEvents();
  }

  function renderRow(t, i) {
    const descEmpty = !t.description;
    return `
      <div class="plan-row ${t.done ? "done" : ""}"
           data-id="${escAttr(t.id)}"
           data-idx="${i}"
           draggable="true">
        <span class="drag-handle" title="drag to reorder">⋮⋮</span>
        <input type="checkbox" ${t.done ? "checked" : ""} data-act="toggle">
        <div class="title-col">
          <div class="title" data-field="title">${escHtml(t.title)}</div>
          <div class="description ${descEmpty ? "empty" : ""}"
               data-field="description">${escHtml(descEmpty ? DESC_PLACEHOLDER : t.description)}</div>
        </div>
        <div class="up-down">
          <button data-act="up"   title="move up">▲</button>
          <button data-act="down" title="move down">▼</button>
        </div>
        <div class="rank">${i + 1}</div>
        <button class="del" data-act="del" title="delete">delete</button>
      </div>
    `;
  }

  function wireRowEvents() {
    const rows = currentModal.querySelectorAll(".plan-row");
    rows.forEach(row => {
      // Click dispatch.
      row.addEventListener("click", onRowClick);
      // Inline edit for title AND description. Both use the same
      // contenteditable pattern — Enter/blur saves, Esc reverts.
      // Title cannot be empty; description can (goes back to placeholder).
      row.querySelectorAll("[data-field]").forEach(el => {
        el.addEventListener("click", () => beginEdit(el));
        el.addEventListener("keydown", (e) => onEditKey(e, el, row));
        el.addEventListener("blur",    () => endEdit(el, row));
      });
      // Drag events for reorder.
      row.addEventListener("dragstart", onDragStart);
      row.addEventListener("dragend",   onDragEnd);
      row.addEventListener("dragover",  onDragOver);
      row.addEventListener("dragleave", onDragLeave);
      row.addEventListener("drop",      onDrop);
    });
  }

  function beginEdit(el) {
    // If this is an empty description showing the placeholder, wipe it
    // so the user starts from a clean slate.
    if (el.dataset.field === "description" && el.classList.contains("empty")) {
      el.textContent = "";
      el.classList.remove("empty");
    }
    el.setAttribute("contenteditable", "true");
    el.focus();
    // Select all so overwriting is one step (skip if we just wiped
    // placeholder — cursor is fine at position 0).
    if (el.textContent) {
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }
  function onEditKey(e, el, row) {
    // Title: Enter blurs. Description: Enter inserts newline (multi-line notes).
    if (e.key === "Enter" && el.dataset.field === "title" && !e.shiftKey) {
      e.preventDefault();
      el.blur();
    }
    if (e.key === "Escape") {
      const id = row.dataset.id;
      const t = tasks.find(x => x.id === id);
      if (!t) return;
      const field = el.dataset.field;
      const orig = t[field] || "";
      if (field === "description" && !orig) {
        el.textContent = DESC_PLACEHOLDER;
        el.classList.add("empty");
      } else {
        el.textContent = orig;
      }
      el.blur();
    }
  }
  function endEdit(el, row) {
    el.removeAttribute("contenteditable");
    const id = row.dataset.id;
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    const field = el.dataset.field;
    const next = el.textContent.trim();
    if (field === "title") {
      if (!next) { el.textContent = t.title; return; }  // never accept empty title
      if (next !== t.title) {
        t.title = next; t.updated_at = nowIso(); scheduleSave();
      }
    } else if (field === "description") {
      if (next !== (t.description || "")) {
        t.description = next; t.updated_at = nowIso(); scheduleSave();
      }
      if (!next) {
        el.textContent = DESC_PLACEHOLDER;
        el.classList.add("empty");
      }
    }
  }

  function onRowClick(e) {
    const row = e.currentTarget;
    const act = e.target.dataset && e.target.dataset.act;
    if (!act) return;
    const id  = row.dataset.id;
    const idx = tasks.findIndex(t => t.id === id);
    if (idx === -1) return;
    if (act === "toggle") {
      tasks[idx].done = !tasks[idx].done;
      tasks[idx].updated_at = nowIso();
      renderList(); scheduleSave();
    } else if (act === "del") {
      tasks.splice(idx, 1);
      renderList(); scheduleSave();
    } else if (act === "up" && idx > 0) {
      [tasks[idx - 1], tasks[idx]] = [tasks[idx], tasks[idx - 1]];
      renderList(); scheduleSave();
    } else if (act === "down" && idx < tasks.length - 1) {
      [tasks[idx + 1], tasks[idx]] = [tasks[idx], tasks[idx + 1]];
      renderList(); scheduleSave();
    }
  }

  // Drag-reorder — native HTML5 DnD, no libs.
  let dragSrcId = null;
  function onDragStart(e) {
    dragSrcId = e.currentTarget.dataset.id;
    e.currentTarget.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    // Firefox requires setData for drag to fire.
    e.dataTransfer.setData("text/plain", dragSrcId);
  }
  function onDragEnd(e) {
    e.currentTarget.classList.remove("dragging");
    currentModal.querySelectorAll(".plan-row").forEach(r =>
      r.classList.remove("drop-target-above", "drop-target-below"));
    dragSrcId = null;
  }
  function onDragOver(e) {
    e.preventDefault();  // Required to allow drop.
    const row = e.currentTarget;
    if (row.dataset.id === dragSrcId) return;
    // Split the row visually — top half = drop-above, bottom half = drop-below.
    const rect = row.getBoundingClientRect();
    const above = (e.clientY - rect.top) < rect.height / 2;
    row.classList.toggle("drop-target-above",  above);
    row.classList.toggle("drop-target-below", !above);
  }
  function onDragLeave(e) {
    e.currentTarget.classList.remove("drop-target-above", "drop-target-below");
  }
  function onDrop(e) {
    e.preventDefault();
    const target = e.currentTarget;
    const targetId = target.dataset.id;
    if (targetId === dragSrcId) return;
    const rect = target.getBoundingClientRect();
    const above = (e.clientY - rect.top) < rect.height / 2;
    const fromIdx = tasks.findIndex(t => t.id === dragSrcId);
    let   toIdx   = tasks.findIndex(t => t.id === targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    const [moved] = tasks.splice(fromIdx, 1);
    // Recompute target index after the splice (fromIdx removed shifts
    // everything after by one).
    if (fromIdx < toIdx) toIdx--;
    tasks.splice(above ? toIdx : toIdx + 1, 0, moved);
    renderList(); scheduleSave();
  }

  // Debounced save — every mutation schedules a save 300ms out, so a
  // burst of edits (e.g., drag through several slots) collapses to
  // one write.
  function scheduleSave() {
    if (savePending) clearTimeout(savePending);
    savePending = setTimeout(save, 300);
  }
  async function save() {
    savePending = null;
    try {
      const r = await fetch("/api/dev/planning", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tasks }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      // Reflect server-cleaned state back — trims empty rows the
      // server dropped, in case any snuck through.
      if (Array.isArray(body.tasks)) tasks = body.tasks;
    } catch (e) {
      toast("planning save failed: " + e.message);
    }
  }

  function escToClose(e) { if (e.key === "Escape") closeModal(); }
  function closeModal() {
    if (!currentModal) return;
    // Force a final save even if debounce is still pending.
    if (savePending) { clearTimeout(savePending); save(); }
    currentModal.remove();
    currentModal = null;
    document.removeEventListener("keydown", escToClose);
  }

  function toast(msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast err";
    el.hidden = false;
    setTimeout(() => { el.hidden = true; }, 2500);
  }

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escAttr(s) { return escHtml(s).replace(/"/g, "&quot;"); }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addButton);
  } else {
    addButton();
  }
})();
