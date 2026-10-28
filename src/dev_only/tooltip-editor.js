// DEV-ONLY tooltip editor. NOT shipped.
//
// Adds a "💬 Tooltips" button to the topbar. Clicking opens a modal
// listing every tooltip key from window.TOOLTIPS_DEFAULT with a text
// field to override it. Save POSTs the diffs to /api/dev/tooltips
// (the dev-only endpoint), which persists to ~/.corpus/tooltips.json.
// Reload shows the new values everywhere the app calls tt(key).

// Register this modal's overlay selector with app.js's Modals registry
// (see planning.js header for details).
if (window.Modals) window.Modals.watchSelector(".dev-tt-modal-overlay");

(function () {
  "use strict";

  function addButton() {
    const topbar = document.querySelector(".topbar");
    if (!topbar) return;
    if (document.getElementById("dev-tt-btn")) return;
    const btn = document.createElement("button");
    btn.id = "dev-tt-btn";
    btn.className = "btn";
    btn.textContent = "Tooltips";
    btn.title = "DEV-ONLY — edit tooltips shown throughout the app";
    btn.addEventListener("click", openEditor);
    // Insert before the settings button so the row stays: Add · Scan ·
    // Settings, with the dev-only tools between. The bug button used to
    // live in the topbar too, but is now a floating body-level pill —
    // insertBefore only accepts a reference node that's an actual CHILD
    // of the parent, so only fall back to it if it's still in the topbar.
    const settingsBtn = document.getElementById("btn-settings");
    const bugBtn = document.getElementById("dev-bug-btn");
    let anchor = null;
    if (settingsBtn && settingsBtn.parentNode === topbar) anchor = settingsBtn;
    else if (bugBtn && bugBtn.parentNode === topbar)       anchor = bugBtn;
    if (anchor) topbar.insertBefore(btn, anchor);
    else topbar.appendChild(btn);
  }

  let currentModal = null;
  // Live edits keyed by tooltip key. On save, POSTs any keys whose
  // value differs from the current effective value (default OR override).
  const edits = {};

  async function openEditor() {
    if (currentModal) return;
    // Fetch the current overrides straight from the server so the
    // editor reflects what's persisted (state.tooltips in the main
    // app might be stale if a prior save happened this session).
    let overrides = {};
    try {
      const r = await fetch("/api/tooltips");
      if (r.ok) overrides = await r.json();
    } catch (_) { /* empty */ }

    const defaults = window.TOOLTIPS_DEFAULT || {};
    // Group keys by their first segment (source / coverage / meta / section).
    const groups = {};
    Object.keys(defaults).forEach(k => {
      const grp = k.split(".")[0] || "other";
      (groups[grp] = groups[grp] || []).push(k);
    });
    Object.keys(groups).forEach(g => groups[g].sort());
    const groupOrder = ["source", "coverage", "meta", "section"]
      .filter(g => groups[g]).concat(
        Object.keys(groups).filter(g => !["source","coverage","meta","section"].includes(g))
      );

    const groupTitles = {
      source:   "Source badges",
      coverage: "Coverage table",
      meta:     "Metadata grid",
      section:  "Section headings",
    };

    const rows = groupOrder.map(g => `
      <div class="tt-group" data-group="${g}">
        <h3>${groupTitles[g] || g} · ${groups[g].length}</h3>
        ${groups[g].map(k => {
          const def = defaults[k] || "";
          const ov  = (overrides[k] || "").trim();
          const val = ov || def;
          return `
            <div class="tt-row" data-tt-key="${escAttr(k)}">
              <div class="tt-key">${escHtml(k)}</div>
              <div class="tt-value">
                <textarea data-key="${escAttr(k)}" data-default="${escAttr(def)}" class="${ov ? "edited" : ""}">${escHtml(val)}</textarea>
                ${ov ? `<div class="tt-default">default: ${escHtml(def)}</div>` : ""}
              </div>
            </div>`;
        }).join("")}
      </div>
    `).join("");

    const overlay = document.createElement("div");
    overlay.className = "dev-tt-modal-overlay";
    overlay.innerHTML = `
      <div class="dev-tt-modal">
        <header>
          <h2>Tooltip Editor</h2>
          <span class="dev-tag">DEV ONLY</span>
          <button class="btn ghost" data-act="close">✕</button>
        </header>
        <div class="toolbar">
          <input type="search" placeholder="filter by key or text…" id="tt-filter">
          <button class="btn" data-act="reset">Reset all to defaults</button>
        </div>
        <div class="body">${rows}</div>
        <footer>
          <span class="counts">${Object.keys(defaults).length} keys · ${Object.keys(overrides).length} currently overridden</span>
          <div>
            <button class="btn" data-act="close">Cancel</button>
            <button class="btn primary" data-act="save">Save changes</button>
          </div>
        </footer>
      </div>
    `;
    document.body.appendChild(overlay);
    currentModal = overlay;
    Object.keys(edits).forEach(k => delete edits[k]);

    // Track edits as the user types.
    overlay.addEventListener("input", (e) => {
      const ta = e.target;
      if (!(ta instanceof HTMLTextAreaElement) || !ta.dataset.key) return;
      const key = ta.dataset.key;
      const def = ta.dataset.default || "";
      const val = ta.value.trim();
      // Match against effective value (default OR override) — sending
      // empty means "clear the override, fall back to default".
      edits[key] = (val === def) ? "" : val;
      if (val === def) ta.classList.remove("edited");
      else             ta.classList.add("edited");
    });

    // Filter as the user types in the toolbar search.
    overlay.querySelector("#tt-filter").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      overlay.querySelectorAll(".tt-row").forEach(row => {
        const key = row.dataset.ttKey || "";
        const txt = row.querySelector("textarea")?.value || "";
        row.style.display = (!q || key.toLowerCase().includes(q) || txt.toLowerCase().includes(q)) ? "" : "none";
      });
      overlay.querySelectorAll(".tt-group").forEach(g => {
        const anyVisible = Array.from(g.querySelectorAll(".tt-row")).some(r => r.style.display !== "none");
        g.style.display = anyVisible ? "" : "none";
      });
    });

    overlay.addEventListener("click", async (e) => {
      const act = e.target.dataset && e.target.dataset.act;
      if (act === "close")  closeEditor();
      if (act === "save")   await save();
      if (act === "reset")  {
        if (confirm("Clear ALL overrides and fall back to defaults everywhere?")) {
          // Set every override to "" — server treats empty as delete.
          Object.keys(overrides).forEach(k => { edits[k] = ""; });
          await save();
        }
      }
    });
    document.addEventListener("keydown", escToClose);
  }

  function escToClose(e) { if (e.key === "Escape") closeEditor(); }
  function closeEditor() {
    if (!currentModal) return;
    currentModal.remove();
    currentModal = null;
    document.removeEventListener("keydown", escToClose);
  }

  async function save() {
    if (Object.keys(edits).length === 0) { closeEditor(); return; }
    try {
      const r = await fetch("/api/dev/tooltips", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ updates: edits }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
      // Refresh live-tooltip state in the main app so re-opened detail
      // panels immediately reflect the changes.
      if (window.state) window.state.tooltips = body.overrides || {};
      toast("tooltips saved");
      closeEditor();
    } catch (e) {
      alert("save failed: " + e.message);
    }
  }

  function toast(msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast ok";
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
