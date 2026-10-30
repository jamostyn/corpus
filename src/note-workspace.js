// Detached note workspace — the note on the left, a PDF on the right.
//
// Requirements (2026-09-21): a note pops out to fill the window, as papers
// do; a panel beside it shows the PDFs tagged in the note; clicking a
// paper link in the note shows that paper in the panel instead of
// navigating the main window; a link to a specific highlight brings up
// that paper and scrolls to the highlight.
//
// This module runs ONLY in a popped-out note window
// (`body.corpus-detached-note`). The docked Notes tab is untouched —
// that is deliberate: the workspace changes what a paper link DOES,
// and silently repurposing links in the main window would be a
// surprise.
//
// Relies at call time on app.js globals: state, api, toast, $, escHtml,
// escAttr, _postToViewer-style messaging is re-implemented here because
// the panel's iframe is a different element from the paper pane's.

window.NoteWorkspace = (function () {
  "use strict";

  function _panelIframe() {
    return document.querySelector("#nw-panel-body iframe");
  }

  /** Post to the PANEL's viewer. Deliberately not app.js's
   *  `_postToViewer`, which targets `#paper-detail .pdf-viewer` — a
   *  different iframe that does not exist in this window. */
  function postToPanel(payload) {
    const f = _panelIframe();
    if (!f || !f.contentWindow) return false;
    f.contentWindow.postMessage({ source: "corpus-shell", ...payload }, "*");
    return true;
  }

  /** This note window's key ("note:<id>"), as launcher.py knows it. */
  function _noteKey() {
    return (state.detached && state.detached.kind === "note")
      ? detachKey("note", state.detached.id) : null;
  }

  /** Ask the launcher for exclusive use of `key` — "<kind>:<id>", a paper
   *  or a document — or release, with null.
   *
   *  The panel is an editor — highlights save from it — so a paper must
   *  not be open here AND in its own window or another note's panel.
   *  Only launcher.py sees every window, so it decides. Outside pywebview
   *  (the browser dev fallback) there is no shared authority, and this
   *  answers "ok": best-effort there, enforced in the app. */
  async function _claim(itemKey) {
    const key = _noteKey();
    if (!key || !(window.pywebview && window.pywebview.api &&
                  window.pywebview.api.set_panel_paper)) return "ok";
    // Literal `window.pywebview.api.<method>` form: the bridge contract
    // test finds calls by it.
    try { return await window.pywebview.api.set_panel_paper(key, itemKey || null); }
    catch (_) { return "ok"; }
  }

  /** The PDF URL and panel title for a paper or a document. */
  function _pdfFor(kind, id) {
    if (kind === "document") {
      const row = (state.documents || []).find(d => d.id === id);
      return { url: `/document/${encodeURIComponent(id)}/pdf`, label: (row && row.title) || id };
    }
    const row = (state.papers || []).find(p => p.slug === id);
    return { url: "/pdf/" + id,
             label: (row && row.title && row.title !== "unknown") ? row.title : id };
  }

  /** Show a paper or a document in the right-hand panel. `kind` is
   *  "paper" or "document" (2026-09-25). `highlightId` optional — when
   *  given, the viewer scrolls to it once the document is ready. */
  async function showPdf(kind, id, highlightId) {
    if (!id) return;
    const itemKey = detachKey(kind, id);
    const ws = document.getElementById("note-workspace");
    const panel = document.getElementById("nw-panel");
    const split = document.getElementById("nw-split");
    const body = document.getElementById("nw-panel-body");
    const title = document.getElementById("nw-panel-title");
    if (!ws || !panel || !body) return;

    ws.classList.add("nw-open");
    panel.hidden = false;
    if (split) split.hidden = false;

    const { url, label } = _pdfFor(kind, id);
    if (title) title.textContent = label;

    // Reload only when the paper actually changes — re-assigning src
    // for the same slug would throw away scroll position and any
    // in-progress highlight.
    if (state.panelSlug !== itemKey) {
      const verdict = await _claim(itemKey);
      if (verdict !== "ok") {
        body.innerHTML = `
          <div class="pdf-detached-placeholder">
            <p>This paper is already open in another window.</p>
            <p class="nw-busy-hint">Close it there to open it here.</p>
          </div>`;
        _setTabs(false);
        return;
      }
      // Claimed the new paper; the launcher released the old one for us
      // (a note key holds at most one slug).
      // Holds the "<kind>:<id>" key, not a bare slug: the panel shows
      // documents too, and a paper slug can equal a document id.
      state.panelSlug = itemKey;
      state.panelTab = "pdf";
      body.innerHTML =
        `<div class="nw-panel-pane" id="nw-pane-pdf">` +
          `<iframe class="pdf-viewer" src="${escAttr(pdfViewerSrc(url))}"></iframe>` +
        `</div>` +
        `<div class="nw-panel-pane nw-info" id="nw-pane-info" hidden></div>`;
      // Paper info exists for papers only — a document has none to show.
      _setTabs(kind === "paper");
    }
    if (highlightId) { _showTab("pdf"); _scrollWhenReady(highlightId); }
  }

  // ---------- Info / PDF switch ------------------------------------
  //
  // The panel switches between an info tab and the PDF view. The info
  // view is the FULL paper view, rendered
  // by paper-detail.js's `renderPaperInto` — the same renderer as the
  // main pane. It was a compact copy (title, authors, year, venue, DOI,
  // abstract) until 2026-09-25, when it was changed to show all paper info. The PDF
  // iframe is hidden, never destroyed, so switching back keeps the
  // reading position.

  function _setTabs(on) {
    const tabs = document.getElementById("nw-panel-tabs");
    if (tabs) tabs.hidden = !on;
    if (on) _markTab(state.panelTab || "pdf");
  }

  function _markTab(which) {
    document.querySelectorAll("#nw-panel-tabs [data-nw-tab]").forEach(b =>
      b.classList.toggle("active", b.dataset.nwTab === which));
  }

  async function _showTab(which) {
    const pdf = document.getElementById("nw-pane-pdf");
    const info = document.getElementById("nw-pane-info");
    if (!pdf || !info) return;
    state.panelTab = which;
    _markTab(which);
    pdf.hidden = which !== "pdf";
    info.hidden = which !== "info";
    if (which === "info" && info.dataset.slug !== state.panelSlug) {
      info.dataset.slug = state.panelSlug;
      await _loadInfo(info, state.panelSlug);
    }
  }

  /** The paper slug behind the panel's key, or null for a document. */
  function _panelPaperSlug() {
    const k = state.panelSlug || "";
    return k.startsWith("paper:") ? k.slice("paper:".length) : null;
  }

  /** Fetch and render the full paper view into the panel's info pane.
   *  Also the pane's `reload`, so an action taken there (Find bridges)
   *  re-renders the panel rather than the main window's hidden pane. */
  async function _loadInfo(info, key) {
    const slug = _panelPaperSlug();
    if (!slug) return;                              // documents have no info tab
    info.innerHTML = `<p class="nw-info-muted">Loading…</p>`;
    try {
      const d = await api(`/api/paper/${encodeURIComponent(slug)}`);
      if (state.panelSlug !== key) return;          // the panel moved on meanwhile
      renderPaperInto(info, d, { panel: true, reload: () => _loadInfo(info, key) });
    } catch (e) {
      info.innerHTML = `<p class="nw-info-muted">Could not load paper info: ${escHtml(e.message)}</p>`;
    }
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("#nw-panel-tabs [data-nw-tab]");
    if (b) _showTab(b.dataset.nwTab);
  });

  // The first post can land before the viewer's script is listening (the
  // iframe exists but is still loading), and a message to a document that
  // is not listening is simply lost. There is no "ready" message on the
  // bridge, so re-send every 400ms for ~6s rather than adding one.
  //
  // Re-sending is safe: the viewer keeps ONE pending request per id,
  // jumps to the highlight's page once, and ignores repeats of a scroll
  // it has just completed. The previous version stopped after ~1.2s and
  // three sends — often before the viewer had loaded at all, which is
  // half of why highlight links landed on page 1 (2026-09-22).
  const _SCROLL_RESENDS = 15;
  function _scrollWhenReady(highlightId, tries) {
    const left = tries == null ? _SCROLL_RESENDS : tries;
    if (left <= 0) return;
    postToPanel({ type: "scroll-to-highlight", id: highlightId });
    setTimeout(() => _scrollWhenReady(highlightId, left - 1), 400);
  }

  function closePanel() {
    const ws = document.getElementById("note-workspace");
    const panel = document.getElementById("nw-panel");
    const split = document.getElementById("nw-split");
    const body = document.getElementById("nw-panel-body");
    if (ws) ws.classList.remove("nw-open");
    if (panel) panel.hidden = true;
    if (split) split.hidden = true;
    if (body) body.innerHTML = "";
    _setTabs(false);
    // Release the paper so it can be opened elsewhere again.
    if (state.panelSlug) _claim(null);
    state.panelSlug = null;
  }

  /** Arm highlight-pick mode: the next highlight clicked in the panel
   *  is returned to `onPicked({slug, id, text})`. */
  let _onPicked = null;
  function pickHighlight(onPicked) {
    if (!state.panelSlug) {
      toast("open a paper or document in the panel first", "err");
      return;
    }
    _onPicked = onPicked || null;
    state.pickingHighlight = true;
    document.body.classList.add("corpus-picking");
    postToPanel({ type: "pick-highlight", on: true });
    toast("click a highlight in the PDF");
  }

  function cancelPick() {
    if (!state.pickingHighlight) return;
    state.pickingHighlight = false;
    _onPicked = null;
    document.body.classList.remove("corpus-picking");
    postToPanel({ type: "pick-highlight", on: false });
  }

  /** Called by the message listener when the viewer reports a pick. */
  function _received(id, text) {
    const cb = _onPicked;
    const i = (state.panelSlug || "").indexOf(":");
    const kind = i === -1 ? "paper" : state.panelSlug.slice(0, i);
    const slug = i === -1 ? state.panelSlug : state.panelSlug.slice(i + 1);
    state.pickingHighlight = false;
    _onPicked = null;
    document.body.classList.remove("corpus-picking");
    if (cb) cb({ kind, slug, id, text: text || "" });
  }

  // Messages from the panel's viewer. A separate listener from
  // app.js's, because that one assumes the paper pane.
  window.addEventListener("message", (e) => {
    const d = e && e.data;
    if (!d || d.source !== "corpus-highlights") return;
    if (d.type === "highlight-picked") _received(d.id, d.text);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.pickingHighlight) cancelPick();
  });

  // ---------- the divider ------------------------------------------
  //
  // Dragging `#nw-split` sets how much of the window the note takes, as
  // `--nw-note-pct` on the workspace (styles.css sizes both sides from
  // it, so closing the panel still gives the note the whole window).
  // Double-click returns to half and half. The share is kept in
  // localStorage, so other note windows open at the same split.

  const SPLIT_MIN = 20, SPLIT_MAX = 80, SPLIT_DEFAULT = 50;
  const _SPLIT_KEY = "corpus.noteSplitPct";

  /** The note's share (percent) for a pointer at `x` over a workspace
   *  starting at `left` and `width` wide, kept within SPLIT_MIN..MAX so
   *  neither side can be dragged shut. null when the width is unknown. */
  function splitPercent(x, left, width) {
    if (!(width > 0)) return null;
    const pct = ((x - left) / width) * 100;
    return Math.round(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, pct)) * 10) / 10;
  }

  function _setSplit(ws, pct) {
    ws.style.setProperty("--nw-note-pct", String(pct));
  }

  function _savedSplit() {
    try {
      const v = parseFloat(localStorage.getItem(_SPLIT_KEY));
      return v >= SPLIT_MIN && v <= SPLIT_MAX ? v : SPLIT_DEFAULT;
    } catch (_) { return SPLIT_DEFAULT; }
  }

  function _wireSplit(ws, split) {
    if (!ws || !split) return;
    _setSplit(ws, _savedSplit());
    let dragging = false;
    const move = (e) => {
      if (!dragging) return;
      const r = ws.getBoundingClientRect();
      const pct = splitPercent(e.clientX, r.left, r.width);
      if (pct != null) _setSplit(ws, pct);
    };
    const end = () => {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("nw-resizing");
      try { localStorage.setItem(_SPLIT_KEY, ws.style.getPropertyValue("--nw-note-pct")); }
      catch (_) {}
    };
    split.addEventListener("pointerdown", (e) => {
      dragging = true;
      // The PDF iframe would swallow pointer events crossing it, ending
      // the drag; `nw-resizing` turns them off while dragging, and the
      // capture keeps the moves coming to the divider.
      document.body.classList.add("nw-resizing");
      try { split.setPointerCapture(e.pointerId); } catch (_) {}
      e.preventDefault();
    });
    split.addEventListener("pointermove", move);
    split.addEventListener("pointerup", end);
    split.addEventListener("pointercancel", end);
    split.addEventListener("dblclick", () => {
      _setSplit(ws, SPLIT_DEFAULT);
      try { localStorage.setItem(_SPLIT_KEY, String(SPLIT_DEFAULT)); } catch (_) {}
    });
  }

  if (document.getElementById) {
    _wireSplit(document.getElementById("note-workspace"),
               document.getElementById("nw-split"));
  }

  return { showPdf, closePanel, postToPanel, pickHighlight, cancelPick,
           _received, splitPercent, _wireSplit,
           SPLIT_MIN, SPLIT_MAX, SPLIT_DEFAULT };
})();
