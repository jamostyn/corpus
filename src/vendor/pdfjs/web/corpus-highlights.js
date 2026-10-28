// ============================================================================
// Corpus highlight plugin — Design Document (READ BEFORE EDITING)
// ============================================================================
//
// This block documents the actual PDF.js layout the plugin sits in. Every
// past bug in the highlight positioning came from guessing at these numbers
// instead of reading them. If a fix isn't derivable from this documentation,
// the documentation is wrong first — update it before editing code.
//
// ---- 1. PDF.js DOM structure (v4.4.168) -----------------------------------
//
//   <div class="page" data-page-number="N" style="width:Wpx; height:Hpx;
//                                                  border: 9px solid transparent">
//     <div class="canvasWrapper">
//       <canvas>          ← the visible page raster (glyphs drawn here)
//     </div>
//     <div class="textLayer">   ← position:absolute, inset:0, transform-origin:0 0
//       <span style="left:Xpx; top:Ypx; font-size:Fpx; transform:scale(1/M)">text</span>
//       ...
//     </div>
//   </div>
//
// Both .textLayer and .canvasWrapper fill .page's CONTENT box (excluding the
// 9px border). Selecting text works because each <span> is placed to overlap
// the glyphs on the canvas — the browser handles selection through the spans.
//
// ---- 2. How PDF.js positions each text span (from pdf.mjs TextLayer._render)
//
//   fontHeight = hypot(tx[2], tx[3])        // font size in device px
//   fontAscent = fontHeight * ascentRatio   // ascentRatio ≈ 0.8 for most fonts
//   left = tx[4]                            // baseline X
//   top  = tx[5] - fontAscent               // TOP OF THE ASCENDER (visible top)
//
//   divStyle.top        = calc(var(--total-scale-factor) * <top>px)
//   divStyle.fontSize   = calc(var(--total-scale-factor) * (minFontSize * fontHeight)px)
//   divStyle.transform  = scale(1/minFontSize)   // only when minFontSize > 1
//
// After the transform, the span's rendered box has:
//   * top  = scale × (baseline − fontAscent)  = top of visible glyph
//   * height ≈ fontHeight × scale             = full glyph height (cap-to-descender)
//
// So `span.getBoundingClientRect()` on a text span IS pixel-aligned with the
// visible glyphs on the canvas. This is the ground truth for highlight rects.
//
// ---- 3. Why range.getClientRects() is WRONG for our use case --------------
//
// `range.getClientRects()` returns rects that describe SELECTION LINE BOXES.
// Browsers compute those from the CSS-inherited line-height of the parent
// (.textLayer has line-height:1, but the range still uses each span's own
// baseline-based positioning + the browser's implicit half-leading rules).
// The result is offset from the visible glyphs by up to one ascender-height,
// depending on font metrics and zoom.
//
// Reading the range's midpoint and looking for a span containing it (the
// previous attempt) FAILS at line breaks: the range rect's midpoint often
// falls into the NEXT line's span, producing highlights one line below the
// selection.
//
// ---- 4. The correct approach: walk spans directly ------------------------
//
// 1. Use `range.getNodes(...)` / a TreeWalker to enumerate text NODES the
//    range touches. Their parentElements are the .textLayer spans that were
//    actually selected.
// 2. For each such span, use `span.getBoundingClientRect()` as the vertical
//    reference (glyph-aligned by construction, see §2).
// 3. For the FIRST selected span, clip horizontally to the range's first
//    client-rect (starts partway through the span).
//    For the LAST span, clip horizontally to the range's last client-rect.
//    Middle spans: use the full span width.
//
// This gives us glyph-aligned coordinates WITHOUT any empirical constants,
// derived only from what PDF.js's own DOM tells us.
//
// ---- 5. Coordinate storage ------------------------------------------------
//
// Highlights are stored as normalized rects (x, y, width, height ∈ [0,1])
// relative to the .textLayer's bounding rect. Rendering multiplies by the
// current textLayer dimensions, so the highlights track zoom and viewer size
// changes for free.
//
// The `.corpus-highlight-layer` is appended INSIDE .page (a sibling of
// .textLayer) with `position: absolute; inset: 0` — CRITICAL detail:
// position:absolute inside .page (position:relative) is anchored to
// .page's PADDING box, NOT its border-box. Since .page has a 9px
// transparent border and .textLayer uses `inset: 0` too, both fill the
// padding box exactly. Setting layer.style.top to the delta between
// .page's border-box-top and .textLayer's viewport top (= the 9px border
// width) DOUBLE-COUNTS the offset and shifts the layer 9px down + right
// from the text. Use inset:0 (or top:0/left:0/width:100%/height:100%),
// NOT a computed offset. This was the source of a persistent ~9px down-
// and-right highlight offset before commit <this one>.
//
// ---- 6. Overlap rules -----------------------------------------------------
//
//   * Anchor OUTSIDE any highlight, new selection overlaps 0 existing → add
//   * Anchor OUTSIDE, overlaps 1+ existing → remove those, add the new one
//   * Anchor INSIDE existing of the same color → remove that highlight
//   * Anchor INSIDE existing of a different color → recolor that highlight
//
// ERASE MODE (added 2026-08-27) bypasses all of the above: any drag
// removes every highlight it touches, regardless of where it started or
// what colour is active. It exists because the rules above make removal
// conditional on two things at once (start point AND colour match), so
// missing either produced a recolour or a new layered highlight instead
// of a removal. The original rules are unchanged — the eraser is an
// additional path, not a replacement.
//
// The anchor is `sel.anchorNode/anchorOffset` — the mouse-down point, NOT
// the mouse-up point. Testing "started inside" against `focusNode` would be
// wrong for backwards drags.
//
// "Overlaps" means RECT-TO-RECT, and that is load-bearing. Until
// 2026-09-09 the query compared each stored rect against the BOUNDING
// BOX of the new selection. Glyph rects are per-line, so any selection
// spanning more than one line has a bounding box far larger than the
// text in it: selecting the end of line 2 through line 3 produces a box
// that also covers the START of line 2. Highlights sitting there were
// deleted without ever being touched — and true of
// the eraser as well, where it silently destroyed notes. Both paths run
// through `highlightsOverlapping`, which now compares every stored rect
// against every selection rect.
//
// ---- 6b. Undo -------------------------------------------------------------
//
// ONE level, covering highlight/unhighlight only. Every mutation of
// state.highlights goes through commitHighlights(), which clones the
// array before mutating; undo swaps the clone back. The funnel is the
// design — there are five mutation sites and per-site snapshot calls
// would guarantee one gets missed.
//
// Note edits (update-note / delete-note from the parent) CLEAR the
// snapshot rather than being undoable. The snapshot is a whole-array
// clone, so applying it after a note edit would silently revert the
// user's typing along with the highlight change.
//
// ---- 7. Persistence -------------------------------------------------------
//
// Highlights per paper live in <corpus>/highlights/<slug>.json (outside
// summaries/ so Re-extract can't wipe them). Saves are debounced 200 ms.
// Server sanitizes on POST — drops empty-rect entries, coerces types.
// ============================================================================

(function () {
  "use strict";

  // Where this PDF's highlights live, from viewer.html's ?file=<pdf-url>:
  //   /pdf/<slug>          -> a paper    -> /api/paper/<slug>/highlights
  //   /document/<id>/pdf   -> a document -> /api/document/<id>/highlights
  // Anything else = no persistence. Documents (2026-09-25) are the same
  // PDF, same highlights, same anchored notes; only the endpoint differs.
  const params = new URLSearchParams(location.search);
  const API = highlightsApiFor(params.get("file") || "");
  if (!API) return;

  function highlightsApiFor(fileUrl) {
    const paper = fileUrl.match(/^\/pdf\/([^/?#]+)/);
    if (paper) return `/api/paper/${encodeURIComponent(decodeURIComponent(paper[1]))}/highlights`;
    const doc = fileUrl.match(/^\/document\/([^/?#]+)\/pdf/);
    if (doc) return `/api/document/${encodeURIComponent(decodeURIComponent(doc[1]))}/highlights`;
    return null;
  }

  // 16-color palette — highlighter tones, semi-transparent when rendered.
  const PALETTE = [
    "#FFEB3B", "#FFC107", "#FF9800", "#FF5722",
    "#F44336", "#E91E63", "#9C27B0", "#673AB7",
    "#3F51B5", "#2196F3", "#03A9F4", "#00BCD4",
    "#009688", "#4CAF50", "#8BC34A", "#CDDC39",
  ];

  // Read the noteMode flag from the URL hash — parent passes
  // `#…&noteMode=1` when the user's global preference is on, so the
  // Note Mode button in the toolbar renders in the correct toggle
  // position on paper-switch. Absence = off. Bidirectional bridge is
  // one-way iframe→parent (see notifyParentNoteMode below) — the
  // parent already knows its own state and doesn't need to be told.
  function readNoteModeFromHash() {
    const raw = (location.hash || "").replace(/^#/, "");
    for (const pair of raw.split("&")) {
      const [k, v] = pair.split("=");
      if (k === "noteMode" && v === "1") return true;
    }
    return false;
  }

  const state = {
    highlights: [],
    highlightMode: false,
    eraseMode:      false,
    // Single-step undo. See `commitHighlights` — {label, highlights} or null.
    undo:           null,
    showHighlights: true,
    noteMode:       readNoteModeFromHash(),
    currentColor: PALETTE[0],
  };

  // Post the current Note Mode value up to the parent Corpus shell so
  // it can class-flip .pd-subpane-pdf and open/close the note gutter.
  // Same-origin so targetOrigin can be `*` without leaking anything.
  function notifyParentNoteMode() {
    try {
      window.parent.postMessage(
        { source: "corpus-note-mode", noteMode: state.noteMode },
        "*"
      );
    } catch (_) { /* iframe not embedded — no-op */ }
  }

  // Toggle the `corpus-note-only` class on <body>. Active ONLY when
  // Note Mode is ON and Highlight Mode is OFF — the "notes-active"
  // configuration. In that mode CSS inverts pointer-events so:
  //   * textLayer stops eating clicks and stops showing the I-beam
  //     (the I-beam was causing macOS to auto-select the word on
  //     right-click, which then defeated our contextmenu handler's
  //     "user is text-selecting" guard).
  //   * .corpus-highlight rects receive clicks, so both left-click
  //     (ping note) and right-click (create note) land cleanly.
  // Highlight Mode ON keeps the defaults (textLayer interactive) so
  // drag-select for drawing new highlights still works.
  function refreshInteractionMode() {
    // Erase mode drag-selects text just like Highlight mode, so it must
    // also keep the text layer interactive. Without `!state.eraseMode`
    // here, turning the eraser on while Note Mode is active leaves
    // pointer-events on the highlight rects and the eraser cannot
    // select anything at all.
    const noteOnly = state.noteMode && !state.highlightMode && !state.eraseMode;
    document.body.classList.toggle("corpus-note-only", noteOnly);
  }


  // ---- Data flow ---------------------------------------------------

  async function loadHighlights() {
    try {
      const r = await fetch(API);
      const data = await r.json();
      state.highlights = Array.isArray(data.highlights) ? data.highlights : [];
    } catch (_) { state.highlights = []; }
  }

  let saveTimer = null;
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 200);
  }
  async function saveNow() {
    saveTimer = null;
    try {
      await fetch(API, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ highlights: state.highlights }),
      });
    } catch (_) { /* silent */ }
  }

  // ---- Rendering ---------------------------------------------------

  function renderHighlightsOnPage(pageDiv, pageNumber) {
    const existing = pageDiv.querySelector(".corpus-highlight-layer");
    if (existing) existing.remove();
    if (!state.showHighlights) return;
    // The layer is a position:absolute child of .page (position:relative).
    // .page has a 9px transparent border. position:absolute uses the
    // PADDING box as its containing block, so top/left of 0 aligns with
    // .textLayer (which also uses inset:0). Setting them to the delta
    // between page's border-box top and textLayer's viewport top =
    // 9px would shift the layer 9px past padding-box top → highlights
    // land 9px below+right of the text. See design doc §5.
    const ref = pageDiv.querySelector(".textLayer")
             || pageDiv.querySelector(".canvasWrapper");
    if (!ref) return;   // page not fully rendered yet
    const layer = document.createElement("div");
    layer.className = "corpus-highlight-layer";
    layer.style.inset = "0";   // = top:0; right:0; bottom:0; left:0
    const pageHighlights = state.highlights.filter(h => h.page === pageNumber);
    for (const h of pageHighlights) {
      for (const r of (h.rects || [])) {
        const el = document.createElement("div");
        el.className = "corpus-highlight";
        el.dataset.highlightId = h.id;
        el.style.left   = (r.x * 100).toFixed(4) + "%";
        el.style.top    = (r.y * 100).toFixed(4) + "%";
        el.style.width  = (r.width  * 100).toFixed(4) + "%";
        el.style.height = (r.height * 100).toFixed(4) + "%";
        el.style.backgroundColor = h.color;
        layer.appendChild(el);
      }
    }
    pageDiv.appendChild(layer);
  }

  function renderAllHighlights() {
    document.querySelectorAll(".page").forEach(pd => {
      const pn = parseInt(pd.getAttribute("data-page-number"), 10);
      if (pn) renderHighlightsOnPage(pd, pn);
    });
  }

  // ---- Selection → highlight ---------------------------------------

  function findPageDiv(node) {
    for (let n = node; n && n !== document.body; n = n.parentNode) {
      if (n.classList && n.classList.contains("page")) return n;
    }
    return null;
  }

  // Collect the .textLayer spans a range actually touches, in document
  // order. Walks TEXT NODES inside the range (not the range rects) so
  // we're using the DOM as PDF.js built it — see §4 of the design
  // doc above.
  function collectSelectedSpans(range) {
    const root = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                  ? range.commonAncestorContainer
                  : range.commonAncestorContainer.parentElement;
    if (!root) return [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const spans = [];
    const seen = new Set();
    let n = walker.nextNode();
    while (n) {
      if (range.intersectsNode(n)) {
        const span = n.parentElement && n.parentElement.closest(".textLayer span");
        if (span && !seen.has(span)) { seen.add(span); spans.push(span); }
      }
      n = walker.nextNode();
    }
    return spans;
  }

  // Build the highlight rects for a selection by walking span-by-span
  // and using each span's own bounding rect for vertical alignment
  // (glyph-aligned by construction, see design doc §2 & §4). Horizontal
  // clipping: first and last spans clip against range.getClientRects()
  // so partial-word selects don't over-highlight.
  //
  // Returns an array of normalized rects ready for storage.
  function buildHighlightRects(range, pageDiv) {
    const spans = collectSelectedSpans(range);
    if (!spans.length) return [];
    const ref = pageDiv.querySelector(".textLayer")
             || pageDiv.querySelector(".canvasWrapper") || pageDiv;
    const pr = ref.getBoundingClientRect();
    // First-span horizontal clip: the range's first client rect starts
    // at the actual start of the selection within the first span.
    const rangeClientRects = Array.from(range.getClientRects())
      .filter(r => r.width > 0.5 && r.height > 0.5);
    const firstClipLeft  = rangeClientRects.length ? rangeClientRects[0].left  : null;
    const lastClipRight  = rangeClientRects.length ? rangeClientRects[rangeClientRects.length - 1].right : null;

    const out = [];
    for (let i = 0; i < spans.length; i++) {
      const b = spans[i].getBoundingClientRect();
      let left = b.left, right = b.right;
      if (i === 0 && firstClipLeft != null) left = Math.max(b.left, firstClipLeft);
      if (i === spans.length - 1 && lastClipRight != null) right = Math.min(b.right, lastClipRight);
      if (right <= left + 0.5) continue;
      out.push({
        x:      (left - pr.left) / pr.width,
        y:      (b.top - pr.top) / pr.height,
        width:   (right - left) / pr.width,
        height:  b.height       / pr.height,
      });
    }
    return out;
  }

  // Debug overlay: when window.CORPUS_HIGHLIGHT_DEBUG === true, draws
  // a red outline showing exactly where getClientRects() reported the
  // selection to be, and a blue outline for a nearby text-span's own
  // bounding rect. Also writes measurement numbers on-screen so we
  // can see what the browser is telling us WITHOUT guessing.
  function debugRects(clientRects, pageDiv, textSpans) {
    if (!window.CORPUS_HIGHLIGHT_DEBUG) return;
    const dbg = document.createElement("div");
    dbg.className = "corpus-hl-debug";
    dbg.style.cssText =
      "position:fixed; top:60px; right:20px; z-index:99999; " +
      "background:#000; color:#0f0; font:11px/1.4 ui-monospace,Menlo,monospace; " +
      "padding:8px; max-width:340px; border-radius:4px; white-space:pre;";
    const pageRect = pageDiv.getBoundingClientRect();
    const tl = pageDiv.querySelector(".textLayer");
    const tlRect = tl && tl.getBoundingClientRect();
    let msg = `page rect: ${pageRect.top.toFixed(1)},${pageRect.left.toFixed(1)} ${pageRect.width.toFixed(1)}x${pageRect.height.toFixed(1)}\n`;
    if (tlRect) msg += `textLayer: ${tlRect.top.toFixed(1)},${tlRect.left.toFixed(1)} ${tlRect.width.toFixed(1)}x${tlRect.height.toFixed(1)}\n`;
    msg += `selection rects (${clientRects.length}):\n`;
    for (const r of clientRects) {
      msg += `  ${r.top.toFixed(1)},${r.left.toFixed(1)}  ${r.width.toFixed(1)}x${r.height.toFixed(1)}\n`;
      const box = document.createElement("div");
      box.style.cssText =
        `position:fixed; top:${r.top}px; left:${r.left}px; ` +
        `width:${r.width}px; height:${r.height}px; ` +
        `border:1px solid red; pointer-events:none; z-index:99998;`;
      box.className = "corpus-hl-debug";
      document.body.appendChild(box);
    }
    if (textSpans && textSpans.length) {
      msg += `text-span rects (${textSpans.length}):\n`;
      for (const s of textSpans.slice(0, 3)) {
        const b = s.getBoundingClientRect();
        msg += `  ${b.top.toFixed(1)},${b.left.toFixed(1)}  ${b.width.toFixed(1)}x${b.height.toFixed(1)}  "${s.textContent.slice(0,20)}"\n`;
        const box = document.createElement("div");
        box.style.cssText =
          `position:fixed; top:${b.top}px; left:${b.left}px; ` +
          `width:${b.width}px; height:${b.height}px; ` +
          `border:1px solid blue; pointer-events:none; z-index:99998;`;
        box.className = "corpus-hl-debug";
        document.body.appendChild(box);
      }
    }
    dbg.textContent = msg;
    document.body.appendChild(dbg);
    // Auto-clear after 8 seconds so it doesn't pile up.
    setTimeout(() => document.querySelectorAll(".corpus-hl-debug")
                        .forEach(el => el.remove()), 8000);
  }

  function rectsOverlap(a, b) {
    return !(a.x + a.width  <= b.x || b.x + b.width  <= a.x ||
             a.y + a.height <= b.y || b.y + b.height <= a.y);
  }

  // Compute where the selection's ANCHOR (mouse-down point) sits in
  // normalized page coords. Used to decide the overlap rule: only
  // treat this selection as edit-an-existing-highlight when the user
  // STARTED inside one. Extending INTO an existing highlight from
  // outside creates a new highlight on top.
  function anchorInNormalizedCoords(sel, pageDiv) {
    if (!sel.anchorNode) return null;
    const r = document.createRange();
    r.setStart(sel.anchorNode, sel.anchorOffset);
    r.setEnd(sel.anchorNode, sel.anchorOffset);
    const rr = r.getBoundingClientRect();
    const ref = pageDiv.querySelector(".textLayer")
             || pageDiv.querySelector(".canvasWrapper") || pageDiv;
    const pr = ref.getBoundingClientRect();
    return {
      x: (rr.left - pr.left) / pr.width,
      y: (rr.top  - pr.top)  / pr.height,
    };
  }

  function pointInsideAny(pt, highlights) {
    for (const h of highlights) {
      for (const r of (h.rects || [])) {
        if (pt.x >= r.x && pt.x <= r.x + r.width &&
            pt.y >= r.y && pt.y <= r.y + r.height) return h;
      }
    }
    return null;
  }

  // ---- Single-step undo --------------------------------------------
  //
  // EVERY mutation of state.highlights goes through commitHighlights.
  // That is the whole design: the snapshot is taken in exactly one
  // place, so a new mutation site cannot forget to make itself
  // undoable. There are five such sites (add, recolour, same-colour
  // remove, subsume-on-overlap, erase, right-click remove) and
  // sprinkling snapshot calls across them would guarantee one gets
  // missed.
  //
  // One level only: just the last action. Undo restores the
  // snapshot and clears it; there is no redo.
  //
  // Notes are NOT undoable here, and editing one CLEARS the snapshot.
  // Reason: the snapshot is a whole-array clone, so undoing a highlight
  // action after a note edit would silently revert the user's typing
  // too. Better to have nothing to undo than to undo something the user
  // did not ask about.
  function cloneHighlights() {
    return state.highlights.map(h => Object.assign({}, h, {
      rects: (h.rects || []).map(r => Object.assign({}, r)),
    }));
  }

  function commitHighlights(label, mutate) {
    state.undo = { label: label, highlights: cloneHighlights() };
    mutate();
    renderAllHighlights();
    scheduleSave();
    notifyParentHighlights();
    refreshUndoButton();
  }

  function undoLast() {
    if (!state.undo) return;
    state.highlights = state.undo.highlights;
    state.undo = null;                 // one level, no redo
    renderAllHighlights();
    scheduleSave();
    notifyParentHighlights();
    refreshUndoButton();
  }

  // Called when something happens that the snapshot cannot represent.
  function clearUndo() {
    if (!state.undo) return;
    state.undo = null;
    refreshUndoButton();
  }

  function refreshUndoButton() {
    const b = document.getElementById("corpusUndoBtn");
    if (!b) return;
    b.disabled = !state.undo;
    b.title = state.undo
      ? `Undo ${state.undo.label}`
      : "Nothing to undo";
  }

  // Resolve a live selection to the page it lands on plus glyph-aligned
  // rects. Shared by the highlight and erase paths — both need exactly
  // this, and a second copy would drift from design-doc §3 (spans, not
  // range client rects).
  function resolveSelection(sel) {
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    const pageDiv = findPageDiv(range.commonAncestorContainer);
    if (!pageDiv) return null;
    const pageNumber = parseInt(pageDiv.getAttribute("data-page-number"), 10);
    const rects = buildHighlightRects(range, pageDiv);
    if (!rects.length) return null;
    return { sel, range, pageDiv, pageNumber, rects };
  }

  // Every stored highlight on `pageNumber` that actually intersects the
  // selection — rect-to-rect on BOTH sides. The single overlap query
  // used by the subsume-on-highlight rule and by the eraser.
  //
  // This used to compare each stored rect against the BOUNDING BOX of
  // the new selection, which is wrong for anything spanning more than
  // one line. A selection covering the end of line 2 and the start of
  // line 3 has a bounding box that also covers the whole START of line
  // 2 — text the user never selected. Highlights living there were
  // treated as overlapping and silently deleted (reported 2026-09-09:
  // highlighting lines 2-3 erased an untouched highlight on lines 1-2).
  //
  // Glyph rects are per-line, so comparing them pairwise is the only
  // thing that matches what the user sees. Cost is
  // O(stored rects x selection rects) per highlight, and both are a
  // handful of line boxes.
  // Scroll the viewer to a highlight and flash it.
  //
  // Returns false when the id is unknown — a link to a highlight the
  // user has since erased must leave the paper open where it is, not
  // jump somewhere arbitrary. The caller retries while the document
  // loads, so "not found yet" and "gone for good" look the same here
  // and both are safe.
  //
  // Bug (2026-09-22): highlight links did not scroll to the highlight. PDF.js renders pages lazily,
  // and a highlight's box is only drawn when its page renders. This used
  // to look for the box and give up when it was not there — which is
  // every highlight on a page you had not scrolled to yet. So the link
  // opened the paper and stayed on page 1.
  //
  // Now: if the box is not drawn, jump to the highlight's PAGE (from the
  // stored highlight), and finish the scroll when that page renders
  // (`_tryPendingScroll` runs on every `pagerendered` and on `pagesinit`).
  // A request that arrives before the highlights or the document have
  // loaded is kept and resolved when they do.
  //
  // The jump happens ONCE per request and the request expires. Without
  // both, a highlight whose box never appears would yank the viewer back
  // to its page on every later page render while the user scrolled away.
  const _PENDING_SCROLL_MS = 10000;
  // Senders retry for a few seconds because the viewer may not be
  // listening yet when the first request is posted. A repeat of a scroll
  // that JUST completed is ignored, or each retry would re-center the
  // page under a user who has already started reading.
  const _REPEAT_IGNORE_MS = 6000;
  let _pendingScroll = null;          // { id, at, jumped }
  let _lastScrolled = null;           // { id, at }

  function _flashHighlightEl(el) {
    _lastScrolled = { id: el.dataset.highlightId, at: Date.now() };
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.classList.add("corpus-highlight-flash");
    setTimeout(() => el.classList.remove("corpus-highlight-flash"), 1600);
  }

  function _tryPendingScroll() {
    const p = _pendingScroll;
    if (!p) return;
    if (Date.now() - p.at > _PENDING_SCROLL_MS) { _pendingScroll = null; return; }
    const el = document.querySelector(
      `.corpus-highlight[data-highlight-id="${CSS.escape(p.id)}"]`);
    if (el) { _pendingScroll = null; _flashHighlightEl(el); return; }
    if (p.jumped) return;
    const h = (state.highlights || []).find(x => x.id === p.id);
    const app = window.PDFViewerApplication;
    if (!h || !h.page || !app || !app.pdfDocument) return;   // not loaded yet
    p.jumped = true;
    app.page = h.page;            // renders the page; pagerendered finishes the job
  }

  function scrollToHighlight(id) {
    if (!id) return false;
    if (_lastScrolled && _lastScrolled.id === id &&
        Date.now() - _lastScrolled.at < _REPEAT_IGNORE_MS) return true;
    // A second click on the same link while the first is still resolving
    // must not reset `jumped` and re-trigger the jump.
    if (!_pendingScroll || _pendingScroll.id !== id) {
      _pendingScroll = { id, at: Date.now(), jumped: false };
    }
    _tryPendingScroll();
    return true;
  }

  function highlightsOverlapping(pageNumber, rects) {
    return state.highlights.filter(h =>
      h.page === pageNumber &&
      (h.rects || []).some(r => rects.some(sel => rectsOverlap(r, sel))));
  }

  // ---- Eraser ------------------------------------------------------
  //
  // Drag across text; every highlight the drag touches is removed. This
  // exists because the original removal path was hard to hit: it fired
  // only when the drag STARTED inside a highlight AND the active swatch
  // matched that highlight's colour. Miss either condition and you got
  // a recolour or a new highlight layered on top instead of a removal.
  // The eraser has no colour condition and no start-point condition.
  //
  // Notes cascade with their highlight (single-record model — the note
  // lives on the highlight object). Erasing is silent EXCEPT when the
  // doomed set contains notes, which are real user writing and are not
  // recoverable; that case confirms first. Confirming on every erase
  // would make the tool as annoying as the thing it replaces.
  function eraseSelection() {
    const sel = window.getSelection();
    const hit = resolveSelection(sel);
    if (!hit) return;
    const doomed = highlightsOverlapping(hit.pageNumber, hit.rects);
    if (!doomed.length) { sel.removeAllRanges(); return; }

    const withNotes = doomed.filter(h => typeof h.note === "string" && h.note.trim());
    if (withNotes.length) {
      const msg = withNotes.length === 1
        ? "Erase 1 highlight that has a note? The note is deleted too and this can't be undone."
        : `Erase ${withNotes.length} highlights that have notes? Their notes are deleted too and this can't be undone.`;
      if (!window.confirm(msg)) { sel.removeAllRanges(); return; }
    }

    const kill = new Set(doomed);
    // commitHighlights also notifies the parent, which erasing needs:
    // a highlight that carried a note must lose its gutter card rather
    // than orphan it.
    commitHighlights(doomed.length > 1 ? "erase highlights" : "erase highlight",
                     () => {
      state.highlights = state.highlights.filter(h => !kill.has(h));
    });
    sel.removeAllRanges();
  }

  function handleSelection() {
    // Erase mode takes precedence; the two toolbar toggles are mutually
    // exclusive, but guard here too so a stale state can never both
    // draw and erase from one drag.
    if (state.eraseMode) { eraseSelection(); return; }
    if (!state.highlightMode) return;
    const sel = window.getSelection();
    const hit = resolveSelection(sel);
    if (!hit) return;
    const { range, pageDiv, pageNumber, rects } = hit;
    debugRects(Array.from(range.getClientRects()), pageDiv,
               collectSelectedSpans(range));
    const text  = sel.toString().trim();

    // Overlap rule: only touch existing
    // highlights when the user STARTED inside one. Starting outside
    // and dragging over an existing one is a "highlight over top",
    // not an edit.
    const anchor = anchorInNormalizedCoords(sel, pageDiv);
    const pageHighlights = state.highlights.filter(h => h.page === pageNumber);
    const startedInside = anchor ? pointInsideAny(anchor, pageHighlights) : null;

    const cur = state.currentColor.toLowerCase();
    const label = startedInside
      ? ((startedInside.color || "").toLowerCase() === cur ? "remove highlight" : "recolour")
      : "highlight";
    commitHighlights(label, () => {
      if (startedInside) {
        // We're editing the highlight the anchor sits inside (plus any
        // adjacent same-color contiguous ones — but for MVP just this one).
        const target = startedInside;
        if ((target.color || "").toLowerCase() === cur) {
          // Same color → remove.
          state.highlights = state.highlights.filter(h => h !== target);
        } else {
          // Different color → recolor.
          target.color = state.currentColor;
        }
      } else {
        // Started outside any highlight. Remove any existing highlights
        // this new selection overlaps at all (in whole OR in part) so
        // the new highlight subsumes them — no stacked layers left
        // underneath.
        const doomed = new Set(highlightsOverlapping(pageNumber, rects));
        state.highlights = state.highlights.filter(h => !doomed.has(h));
        state.highlights.push({
          id:         `h_${Math.random().toString(36).slice(2, 10)}`,
          page:       pageNumber,
          color:      state.currentColor,
          text:       text,
          rects:      rects,
          created_at: new Date().toISOString(),
        });
      }
    });
    sel.removeAllRanges();
  }

  // ---- Toolbar UI --------------------------------------------------

  function ensureToolbarUI() {
    // Anchor: the RIGHT toolbar section. PDF.js's left section is full
    // of pagination controls and its middle section holds the zoom
    // dropdown; adding Corpus buttons to the left pushed them past the
    // absolutely-centered middle so they visually overlapped the zoom
    // dropdown (2026-08-19 screenshot). The right section holds only
    // the annotation-editor buttons and print/save — all disabled or
    // no-op in the Corpus config — so there's plenty of room.
    const anchor = document.getElementById("toolbarViewerRight")
                || document.getElementById("toolbarViewerLeft")
                || document.getElementById("toolbarContainer");
    if (!anchor) return;
    if (document.getElementById("corpusHighlightBtn")) return; // already added

    // Highlight-mode toggle. Deliberately NOT using PDF.js's
    // .toolbarButton class — that class brings ::before/::after
    // pseudo-elements meant to render icon backgrounds, which show
    // up as empty grey boxes under a text-only button. Our own
    // class carries all styling.
    const btn = document.createElement("button");
    btn.id = "corpusHighlightBtn";
    btn.className = "corpus-toolbar-btn";
    btn.title = "Toggle highlight mode";
    btn.textContent = "Highlight";
    btn.addEventListener("click", () => {
      state.highlightMode = !state.highlightMode;
      if (state.highlightMode && state.eraseMode) {
        state.eraseMode = false;
        const eb = document.getElementById("corpusEraseBtn");
        if (eb) eb.classList.remove("toggled");
        document.body.classList.remove("corpus-erasing");
      }
      btn.classList.toggle("toggled", state.highlightMode);
      updateSwatchVisibility();
      refreshInteractionMode();
    });
    anchor.appendChild(btn);

    // Eraser. Mutually exclusive with Highlight so one drag can never
    // mean both; flipping either off-switches the other.
    const eraseBtn = document.createElement("button");
    eraseBtn.id = "corpusEraseBtn";
    eraseBtn.className = "corpus-toolbar-btn";
    eraseBtn.title = "Erase highlights — drag over text to remove any highlight it touches";
    eraseBtn.textContent = "Erase";
    eraseBtn.addEventListener("click", () => {
      state.eraseMode = !state.eraseMode;
      if (state.eraseMode && state.highlightMode) {
        state.highlightMode = false;
        btn.classList.remove("toggled");
      }
      eraseBtn.classList.toggle("toggled", state.eraseMode);
      document.body.classList.toggle("corpus-erasing", state.eraseMode);
      updateSwatchVisibility();
      refreshInteractionMode();
    });
    anchor.appendChild(eraseBtn);

    // Undo. Starts disabled — refreshUndoButton() is the single place
    // that decides its enabled state, driven off state.undo.
    const undoBtn = document.createElement("button");
    undoBtn.id = "corpusUndoBtn";
    undoBtn.className = "corpus-toolbar-btn";
    undoBtn.textContent = "Undo";
    undoBtn.disabled = true;
    undoBtn.title = "Nothing to undo";
    undoBtn.addEventListener("click", undoLast);
    anchor.appendChild(undoBtn);
    refreshUndoButton();

    // 'show' checkbox — dimensions/layout live in corpus-highlights.css
    // so the pair aligns with PDF.js's float-based toolbar layout.
    const show = document.createElement("label");
    show.id = "corpusShowLabel";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.id = "corpusShowHighlights";
    cb.addEventListener("change", () => {
      state.showHighlights = cb.checked;
      renderAllHighlights();
    });
    show.appendChild(cb);
    show.appendChild(document.createTextNode("show"));
    anchor.appendChild(show);

    // Note Mode button — same iframe toolbar as Highlight + show so all
    // three PDF controls stay together. Clicks flip iframe-local state
    // and post up to the parent, which class-flips .pd-subpane-pdf to
    // open/close the note gutter. Initial position mirrors the parent's
    // global preference (see readNoteModeFromHash).
    const noteBtn = document.createElement("button");
    noteBtn.id = "corpusNoteModeBtn";
    noteBtn.className = "corpus-toolbar-btn";
    noteBtn.title = "Toggle Note Mode — opens a side gutter for notes anchored to highlights.";
    noteBtn.textContent = "Note Mode";
    if (state.noteMode) noteBtn.classList.add("toggled");
    noteBtn.addEventListener("click", () => {
      state.noteMode = !state.noteMode;
      noteBtn.classList.toggle("toggled", state.noteMode);
      notifyParentNoteMode();
      refreshInteractionMode();
    });
    anchor.appendChild(noteBtn);
  }

  function ensureSwatch() {
    if (document.getElementById("corpusColorSwatch")) return;
    const s = document.createElement("div");
    s.id = "corpusColorSwatch";
    s.title = "Highlight color — click to pick";
    s.style.backgroundColor = state.currentColor;
    s.addEventListener("click", (e) => { e.stopPropagation(); openPicker(s); });
    document.body.appendChild(s);
    updateSwatchVisibility();
  }

  function updateSwatchVisibility() {
    const s = document.getElementById("corpusColorSwatch");
    if (s) s.style.display = (state.highlightMode && !state.eraseMode) ? "block" : "none";
  }

  function openPicker(swatch) {
    const existing = document.getElementById("corpusColorPicker");
    if (existing) { existing.remove(); return; }
    const picker = document.createElement("div");
    picker.id = "corpusColorPicker";
    for (const color of PALETTE) {
      const c = document.createElement("div");
      c.className = "corpus-color-cell";
      c.style.backgroundColor = color;
      if (color === state.currentColor) c.classList.add("selected");
      c.addEventListener("click", (e) => {
        e.stopPropagation();
        state.currentColor = color;
        swatch.style.backgroundColor = color;
        picker.remove();
      });
      picker.appendChild(c);
    }
    document.body.appendChild(picker);
    // Close on outside click. Deferred so this same click event doesn't
    // instantly re-close it.
    setTimeout(() => {
      document.addEventListener("click", function close(e) {
        if (!picker.contains(e.target) && e.target !== swatch) {
          picker.remove();
          document.removeEventListener("click", close);
        }
      });
    }, 0);
  }

  // ---- Right-click on highlight → Create / Focus note (Note Mode) --
  //
  // Rules:
  //   * Note Mode OFF        → do nothing (browser default menu wins —
  //                             users get Look Up 'word' / Copy on any
  //                             text selection).
  //   * Note Mode ON         → menu with Create/Focus note, regardless
  //                             of Highlight Mode. Left-click drag-
  //                             select is untouched so highlighting
  //                             still works normally.
  //   * User is text-selecting (selection non-collapsed) → skip the
  //                             menu so the browser default menu can
  //                             expose Copy / Look Up on the selection.
  //
  // Detection: `.corpus-highlight` has `pointer-events: none` so the
  // browser routes contextmenu to the textLayer span underneath. We
  // still need to know if the click point was inside a highlight rect —
  // scan the visible `.corpus-highlight` elements and point-in-rect
  // against their bounding boxes. Cheap for typical highlight counts.

  let _cornerMenu = null;
  function _dismissCornerMenu() {
    if (_cornerMenu) { _cornerMenu.remove(); _cornerMenu = null; }
  }
  document.addEventListener("mousedown", (e) => {
    if (_cornerMenu && !_cornerMenu.contains(e.target)) _dismissCornerMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") _dismissCornerMenu();
  });

  function showCreateNoteMenu(x, y, highlight) {
    _dismissCornerMenu();
    const menu = document.createElement("div");
    menu.className = "corpus-highlight-menu";
    menu.style.left = `${x}px`;
    menu.style.top  = `${y}px`;
    const existing = typeof highlight.note === "string";

    const noteBtn = document.createElement("button");
    noteBtn.type = "button";
    noteBtn.className = "corpus-highlight-menu-item";
    noteBtn.textContent = existing ? "Focus note" : "Create note";
    noteBtn.addEventListener("click", () => {
      _dismissCornerMenu();
      if (!existing) {
        // Attach an empty note. Save + notify parent so the gutter
        // renders the new card and focuses its textarea.
        highlight.note = "";
        scheduleSave();
      }
      notifyParentHighlights({ focusNoteId: highlight.id });
    });
    menu.appendChild(noteBtn);

    const sep = document.createElement("div");
    sep.className = "corpus-highlight-menu-sep";
    menu.appendChild(sep);

    // Remove highlight (and its attached note, if any). Confirmation
    // uses window.confirm — same-origin iframe, so the OS-native dialog
    // is available and blocks until the user decides. Cascade: removing
    // the highlight also removes any note anchored to it (single-record
    // data model — the note lives on the highlight object).
    const rmBtn = document.createElement("button");
    rmBtn.type = "button";
    rmBtn.className = "corpus-highlight-menu-item corpus-highlight-menu-item-danger";
    rmBtn.textContent = existing ? "Remove highlight + note" : "Remove highlight";
    rmBtn.addEventListener("click", () => {
      _dismissCornerMenu();
      const msg = existing
        ? "Remove this highlight and its note? This can't be undone."
        : "Remove this highlight? This can't be undone.";
      if (!window.confirm(msg)) return;
      commitHighlights(existing ? "remove highlight + note" : "remove highlight",
                       () => {
        state.highlights = state.highlights.filter(h => h.id !== highlight.id);
      });
    });
    menu.appendChild(rmBtn);

    document.body.appendChild(menu);
    _cornerMenu = menu;
    // Clip to viewport.
    const r = menu.getBoundingClientRect();
    if (r.right  > window.innerWidth ) menu.style.left = `${window.innerWidth  - r.width  - 4}px`;
    if (r.bottom > window.innerHeight) menu.style.top  = `${window.innerHeight - r.height - 4}px`;
  }

  // Return the highlight object whose visible bounding box contains
  // the given viewport point, or null. Since `.corpus-highlight` has
  // pointer-events: none we can't use `e.target` — walk the DOM
  // instead. Cheap since we only inspect currently-rendered pages.
  function highlightAtPoint(x, y) {
    const els = document.querySelectorAll(".corpus-highlight");
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
        const id = el.dataset.highlightId;
        const h = state.highlights.find(x => x.id === id);
        if (h) return h;
      }
    }
    return null;
  }

  document.addEventListener("contextmenu", (e) => {
    // Note-adding is disabled during Highlight Mode — drag-select
    // needs the textLayer active + I-beam cursor for drawing new
    // highlights, and right-click there falls through to
    // the browser default (Look Up 'word' etc.).
    if (state.highlightMode) return;
    if (!state.noteMode) return;                        // browser default OK
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;                // user is selecting text
    const h = highlightAtPoint(e.clientX, e.clientY);
    if (!h) return;
    e.preventDefault();
    showCreateNoteMenu(e.clientX, e.clientY, h);
  });

  // Left-click on a highlight (Highlight Mode OFF, Note Mode ON, no
  // selection in flight, highlight has a note) → ping its gutter card:
  // scroll it into view, flash the border briefly. Delegated to the
  // parent via `focus-note`; the iframe only decides IF it should ping.
  //
  // Same point-in-rect trick as the contextmenu handler because
  // `.corpus-highlight` has pointer-events: none (so drag-select stays
  // uninterrupted in Highlight Mode).
  document.addEventListener("click", (e) => {
    // Pick mode wins over every other click rule, including the
    // Note Mode and Highlight Mode guards below. The parent armed it
    // and is waiting for exactly one answer, so a click on a highlight
    // must report rather than do its usual job — otherwise the user
    // would have to turn Note Mode on first just to pick one.
    if (state.pickMode) {
      const picked = highlightAtPoint(e.clientX, e.clientY);
      if (!picked) return;                              // missed — stay armed
      e.preventDefault();
      e.stopPropagation();
      state.pickMode = false;
      document.body.classList.remove("corpus-picking");
      try {
        window.parent.postMessage({
          source: "corpus-highlights",
          type:   "highlight-picked",
          id:     picked.id,
          text:   String(picked.text || ""),
        }, "*");
      } catch (_) {}
      return;
    }
    if (state.highlightMode) return;                    // drag-select owns clicks
    if (!state.noteMode)     return;                    // gutter is hidden
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;                // text-selecting
    const h = highlightAtPoint(e.clientX, e.clientY);
    if (!h || typeof h.note !== "string") return;       // nothing to focus
    try {
      window.parent.postMessage({
        source: "corpus-highlights",
        type:   "focus-note",
        id:     h.id,
      }, "*");
    } catch (_) {}
  });

  // ---- Cross-frame bridge for notes --------------------------------
  //
  // Parent (Corpus shell) renders the gutter card and its textarea; we
  // hold the source of truth for the highlight+note data and persist
  // it. On any highlights change we push the current list up so the
  // parent can re-render. On user edits in the gutter, parent posts
  // `update-note` back and we save.

  // Compute the highlight's absolute y in the viewer's scrollable
  // content coord system (invariant of current scroll). Returns null
  // when the target page hasn't been laid out yet — the caller drops
  // that highlight and revisits after the next 'pagerendered'.
  function highlightAbsoluteY(h) {
    const pageView = window.PDFViewerApplication &&
                     PDFViewerApplication.pdfViewer &&
                     PDFViewerApplication.pdfViewer.getPageView(h.page - 1);
    if (!pageView || !pageView.div) return null;
    const yNorm = (h.rects && h.rects[0]) ? h.rects[0].y : 0;
    return pageView.div.offsetTop + yNorm * pageView.div.offsetHeight;
  }

  // Snapshot of the PDF.js scroll container's geometry — the parent
  // sizes the gutter's inner absolutely-positioned canvas to
  // contentHeight and mirrors scrollTop so gutter cards line up with
  // their highlights across pages.
  function getViewerGeometry() {
    const viewer    = document.getElementById("viewer");
    const container = window.PDFViewerApplication &&
                      PDFViewerApplication.pdfViewer &&
                      PDFViewerApplication.pdfViewer.container;
    return {
      contentHeight:  viewer    ? viewer.offsetHeight   : 0,
      scrollTop:      container ? container.scrollTop   : 0,
      viewportHeight: container ? container.clientHeight : 0,
    };
  }

  function notifyParentHighlights(extra) {
    const augmented = state.highlights.map(h => {
      const y = highlightAbsoluteY(h);
      return y != null ? Object.assign({}, h, { absoluteY: y }) : h;
    });
    try {
      window.parent.postMessage({
        source:     "corpus-highlights",
        type:       "highlights",
        highlights: augmented,
        viewer:     getViewerGeometry(),
        ...(extra || {}),
      }, "*");
    } catch (_) { /* not embedded */ }
  }

  function notifyParentScroll() {
    try {
      window.parent.postMessage({
        source: "corpus-highlights",
        type:   "scroll",
        viewer: getViewerGeometry(),
      }, "*");
    } catch (_) {}
  }

  // Track when we're programmatically scrolling the PDF viewer so the
  // resulting scroll event doesn't echo back up as a "scroll" message
  // (which would loop indefinitely through the parent's gutter sync).
  let _incomingScrollSync = false;

  window.addEventListener("message", (e) => {
    const d = e.data;
    if (!d || d.source !== "corpus-shell") return;
    if (d.type === "update-note") {
      const h = state.highlights.find(x => x.id === d.id);
      if (!h) return;
      h.note = String(d.note || "");
      clearUndo();      // snapshot can no longer be applied safely
      scheduleSave();
    } else if (d.type === "delete-note") {
      const h = state.highlights.find(x => x.id === d.id);
      if (!h) return;
      delete h.note;
      clearUndo();      // snapshot can no longer be applied safely
      scheduleSave();
      notifyParentHighlights();
    } else if (d.type === "pick-highlight") {
      // Arm/disarm highlight picking. While armed, a click on a
      // highlight reports its id to the parent instead of opening the
      // note editor — the note workspace uses this to build a link to
      // one exact spot.
      state.pickMode = !!d.on;
      document.body.classList.toggle("corpus-picking", state.pickMode);
    } else if (d.type === "scroll-to-highlight") {
      scrollToHighlight(String(d.id || ""));
    } else if (d.type === "set-scroll") {
      // Parent gutter was scrolled; mirror it in the PDF viewer.
      const container = window.PDFViewerApplication &&
                        PDFViewerApplication.pdfViewer &&
                        PDFViewerApplication.pdfViewer.container;
      if (!container) return;
      const target = Number(d.scrollTop) || 0;
      if (Math.abs(container.scrollTop - target) < 1) return;
      _incomingScrollSync = true;
      container.scrollTop = target;
      requestAnimationFrame(() => { _incomingScrollSync = false; });
    }
  });

  // Wrap saveNow / addOrUpdate paths so the parent gutter stays in
  // sync after highlights themselves change (add / recolor / delete
  // via re-drag). We piggyback on the existing scheduleSave() timer:
  // after we write, tell the parent.
  const _origSaveNow = saveNow;
  saveNow = async function () {          // eslint-disable-line no-func-assign
    await _origSaveNow();
    notifyParentHighlights();
  };

  // Cmd-Z / Ctrl-Z. A button alone is discoverable but an undo feature
  // without the standard shortcut reads as broken, and inside this
  // iframe the chord has no competing meaning (PDF.js binds it to
  // nothing, and the notes editor lives in the parent document with its
  // own separate history).
  document.addEventListener("keydown", (e) => {
    if (e.key !== "z" && e.key !== "Z") return;
    if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return;
    if (!state.undo) return;
    e.preventDefault();
    undoLast();
  });

  // ---- Viewer failed to start --------------------------------------
  //
  // viewer.mjs publishes `window.PDFViewerApplication` at its top level,
  // and module scripts run before this `defer` script (same ordered
  // list). So if it is missing here, pdf.js never ran, and the pane
  // would otherwise be a toolbar over an empty (dark-mode: black) page
  // with no message anywhere a user can see (Windows, 2026-09-29).
  // The readout names each viewer module and the type it was served
  // with, which is the first thing to know on a machine we cannot
  // attach a debugger to.
  const _VIEWER_MODULES = ["../build/pdf.mjs", "viewer.mjs"];

  async function _viewerModuleTypes(fetchFn) {
    const lines = [];
    for (const url of _VIEWER_MODULES) {
      let type;
      try {
        const r = await fetchFn(url, { method: "HEAD", cache: "no-store" });
        type = r.ok ? (r.headers.get("Content-Type") || "no type") : `HTTP ${r.status}`;
      } catch (e) {
        type = "not reachable";
      }
      lines.push(`${url.split("/").pop()}: ${type}`);
    }
    return lines;
  }

  async function reportViewerLoadFailure() {
    const box = document.createElement("div");
    box.id = "corpusViewerFailure";
    box.setAttribute("role", "alert");
    box.style.cssText = "position:fixed;inset:48px 16px auto 16px;z-index:100000;" +
      "padding:12px 14px;border-radius:6px;background:#fff;color:#111;" +
      "font:13px/1.45 system-ui,sans-serif;white-space:pre-wrap";
    box.textContent = "The PDF viewer did not start.";
    document.body.appendChild(box);
    const lines = await _viewerModuleTypes(window.fetch.bind(window));
    box.textContent = "The PDF viewer did not start.\n" + lines.join("\n");
  }
  // ---- end viewer-failure readout

  // ---- Init --------------------------------------------------------

  async function init() {
    if (typeof window.PDFViewerApplication === "undefined") {
      reportViewerLoadFailure();
      return;
    }
    await loadHighlights();
    if (typeof PDFViewerApplication !== "undefined" &&
        PDFViewerApplication.initializedPromise) {
      try { await PDFViewerApplication.initializedPromise; } catch (_) {}
    }
    // A highlight link may have arrived before the highlights loaded.
    _tryPendingScroll();
    ensureToolbarUI();
    ensureSwatch();
    refreshInteractionMode();     // apply initial pointer-events mode
    // Redraw highlights every time PDF.js finishes rendering a page
    // (initial load, zoom change, scroll-triggered lazy render). Also
    // re-notify the parent so gutter cards for that page's highlights
    // pick up their now-computable absolute-y positions.
    if (window.PDFViewerApplication && PDFViewerApplication.eventBus) {
      PDFViewerApplication.eventBus.on("pagerendered", (evt) => {
        renderHighlightsOnPage(evt.source.div, evt.pageNumber);
        notifyParentHighlights();
        _tryPendingScroll();          // a highlight link may be waiting on this page
      });
      // The document is ready to navigate: a link that arrived during
      // load can jump now.
      PDFViewerApplication.eventBus.on("pagesinit", _tryPendingScroll);
      // Zoom / rotation / spread changes: all page dimensions shift, so
      // every highlight's absoluteY changes. Re-send.
      PDFViewerApplication.eventBus.on("scalechanging", notifyParentHighlights);
      PDFViewerApplication.eventBus.on("rotationchanging", notifyParentHighlights);
    }
    // Sync the note gutter's scroll with the PDF viewer's scroll. Cheap
    // rAF-throttled event on the actual scroll container. Sends geometry
    // only (no highlight recomputation).
    const scrollContainer = window.PDFViewerApplication &&
                            PDFViewerApplication.pdfViewer &&
                            PDFViewerApplication.pdfViewer.container;
    if (scrollContainer) {
      let scrollScheduled = false;
      scrollContainer.addEventListener("scroll", () => {
        // Skip programmatic scrolls we made in response to the parent's
        // gutter scroll — otherwise we'd loop forever.
        if (_incomingScrollSync) return;
        if (scrollScheduled) return;
        scrollScheduled = true;
        requestAnimationFrame(() => {
          scrollScheduled = false;
          notifyParentScroll();
        });
      });
    }
    // Also render any pages already on-screen at plugin-init time.
    renderAllHighlights();
    document.addEventListener("mouseup", () => {
      // Small delay so the browser has finalized the selection.
      setTimeout(handleSelection, 10);
    });
    // Tell the parent about our highlights so the gutter can render.
    notifyParentHighlights();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
