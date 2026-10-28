// DEV-ONLY bug reporter. NOT to be shipped.
//
// Injected into the DOM when /api/config returns dev_mode:true.
// Adds a "Bug report" button to the topbar. Clicking:
//   1. captures a screenshot of the current window via html2canvas
//   2. opens a modal with the screenshot + draw-boxes canvas + textarea
//   3. on submit, composites boxes onto the screenshot and POSTs to
//      /api/dev/bug-report

// Register this modal's overlay selector with app.js's Modals registry
// (see planning.js header for details).
if (window.Modals) window.Modals.watchSelector(".dev-bug-modal-overlay");

(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  // ---------- Inject topbar button ----------

  function addButton() {
    if (document.getElementById("dev-bug-btn")) return;  // already there
    const btn = document.createElement("button");
    btn.id = "dev-bug-btn";
    // NB: NOT .btn — floating-button styling in bug-reporter.css takes
    // over (position:fixed, bottom-right, z-index above all modals).
    btn.type = "button";
    btn.textContent = "Bug";
    // Advertise the shortcut too — button + shortcut are redundant on
    // purpose so nothing blocks reporting.
    const shortcutLabel = (navigator.platform || "").toLowerCase().includes("mac")
      ? "⌘⇧B" : "Ctrl+Shift+B";
    btn.title = `DEV-ONLY — capture a screenshot + describe a bug (${shortcutLabel})`;
    btn.addEventListener("click", onBugClick);
    // Live at the body level so it isn't trapped inside any stacking
    // context that a modal could cover.
    document.body.appendChild(btn);
  }

  // Global keyboard shortcut — reaches over any modal (Planning,
  // Tooltips, Settings) since the topbar button is covered by them.
  // Capture-phase listener + explicit modal-ignore so text inputs
  // inside modals don't swallow it.
  document.addEventListener("keydown", (e) => {
    const combo = (e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "B" || e.key === "b");
    if (!combo) return;
    e.preventDefault();
    e.stopPropagation();
    onBugClick();
  }, true);

  // ---------- Screenshot + modal flow ----------

  // Modal stack — reporting a bug ABOUT the bug reporter (or any other
  // popup) requires opening a new report modal on TOP of the one that's
  // already open, with a screenshot that includes the underlying modal.
  // Track the whole chain and close from the top.
  const modalStack = [];
  const rectsPerModal = new WeakMap();   // overlay → rectangles[]

  async function onBugClick() {
    const btn = document.getElementById("dev-bug-btn");
    if (btn) btn.disabled = true;

    // Corpus's layout keeps body/html at overflow:hidden and does the
    // real scrolling inside .main-pane / .sidebar. html2canvas can only
    // see currently-visible content in those clipped containers, so the
    // screenshot ends up cropped to the viewport height. Temporarily
    // un-clip the scroll containers, capture at full document size,
    // then restore inline styles.
    // The sidebar is deliberately NOT un-clipped. At ~600 papers its full
    // height is tens of thousands of pixels, which pushed the capture past
    // WebKit's maximum canvas size; the canvas came back empty and the
    // report saved a 0-byte screenshot (2026-09-21, "i cant see the image
    // of the error lol. just a question mark"). A bug is never about row
    // 412 of the paper list — the visible part of the sidebar is enough.
    const scrollables = [
      document.documentElement,
      document.body,
      document.querySelector(".main-pane"),
    ].filter(Boolean);
    const savedStyles = scrollables.map(el => ({
      el,
      overflow:      el.style.getPropertyValue("overflow"),
      overflowPrio:  el.style.getPropertyPriority("overflow"),
      height:        el.style.getPropertyValue("height"),
      heightPrio:    el.style.getPropertyPriority("height"),
    }));
    for (const el of scrollables) {
      el.style.setProperty("overflow", "visible", "important");
      el.style.setProperty("height",   "auto",    "important");
    }

    // Iframes (currently the PDF viewer) render into their own document
    // that html2canvas can't rasterize directly. Two strategies:
    //   1. Same-origin: reach into iframe.contentDocument, find the
    //      PDF.js #viewerContainer, iterate every .page canvas, and
    //      composite the visible pages onto our own <canvas>. Wrap in
    //      an <img> so the outer html2canvas has a plain element to
    //      inline. Loses the toolbar/UI chrome — html2canvas can't
    //      reliably render PDF.js's CSS-background-image icons, and
    //      running html2canvas on the inner document either fails
    //      silently or produces broken raw HTML (form controls with
    //      their text labels visible instead of icons).
    //   2. Cross-origin or capture failure: labeled placeholder so
    //      the layout doesn't shift.
    const iframeReplacements = [];
    for (const iframe of document.querySelectorAll("iframe")) {
      if (iframe.offsetParent === null) continue;   // hidden — skip
      const rect = iframe.getBoundingClientRect();
      if (rect.width < 20 || rect.height < 20) continue;

      let replacement = null;

      // Same-origin PDF page composite. Draws:
      //   1. PDF page canvases (the actual pages PDF.js rendered)
      //   2. Any Corpus highlight rects on top, at their stored color
      //      with the same 40% opacity the viewer uses.
      // Then annotates the bottom of the image with the toolbar STATE
      // as text (page X / Y, zoom level, sidebar) so bug reports carry
      // that context even though the toolbar chrome itself can't be
      // rasterized (CSS-background-image icons don't survive html2canvas).
      try {
        const iframeDoc = iframe.contentDocument;
        const viewerContainer = iframeDoc && iframeDoc.querySelector("#viewerContainer");
        if (viewerContainer) {
          const snap = document.createElement("canvas");
          snap.width  = Math.round(rect.width);
          snap.height = Math.round(rect.height);
          const ctx = snap.getContext("2d");
          ctx.fillStyle = "#fafafa";
          ctx.fillRect(0, 0, snap.width, snap.height);
          const containerRect = viewerContainer.getBoundingClientRect();
          // Draw PDF page canvases.
          for (const pc of iframeDoc.querySelectorAll(".page canvas")) {
            const pr = pc.getBoundingClientRect();
            const relLeft = pr.left - containerRect.left;
            const relTop  = pr.top  - containerRect.top;
            if (relTop + pr.height < 0) continue;
            if (relTop > rect.height)   continue;
            ctx.drawImage(pc, relLeft, relTop, pr.width, pr.height);
          }
          // Draw Corpus highlight rects on top of the pages. Uses the
          // same 0.4 opacity + multiply blend as the viewer, so
          // screenshot matches what the user was looking at.
          ctx.globalCompositeOperation = "multiply";
          ctx.globalAlpha = 0.4;
          for (const hi of iframeDoc.querySelectorAll(".corpus-highlight")) {
            const hr = hi.getBoundingClientRect();
            const relLeft = hr.left - containerRect.left;
            const relTop  = hr.top  - containerRect.top;
            if (relTop + hr.height < 0) continue;
            if (relTop > rect.height)   continue;
            ctx.fillStyle = hi.style.backgroundColor || "#ffeb3b";
            ctx.fillRect(relLeft, relTop, hr.width, hr.height);
          }
          ctx.globalCompositeOperation = "source-over";
          ctx.globalAlpha = 1.0;
          // Toolbar state footer — text overlay on a grey bar at the
          // bottom of the composite. Includes what Jack most likely
          // cares about seeing: page + zoom + sidebar. Uses the
          // iframe's PDF.js state; falls back to '(unknown)' fields.
          try {
            const pn = iframeDoc.querySelector("#pageNumber");
            const totalPages = iframeDoc.querySelector("#numPages");
            const scale = iframeDoc.querySelector("#scaleSelect");
            const scaleValue = scale && scale.selectedOptions && scale.selectedOptions[0]
                                ? scale.selectedOptions[0].textContent : "(unknown)";
            const sidebar = iframeDoc.querySelector("#outerContainer");
            const sidebarOpen = sidebar && sidebar.classList.contains("sidebarOpen");
            const highlightBtn = iframeDoc.querySelector("#corpusHighlightBtn");
            const highlightOn  = highlightBtn && highlightBtn.classList.contains("toggled");
            const showBox = iframeDoc.querySelector("#corpusShowHighlights");
            const showOn = showBox && showBox.checked;
            const parts = [
              `page ${pn ? pn.value : "?"}/${totalPages ? totalPages.textContent : "?"}`,
              `zoom: ${scaleValue.trim()}`,
              `sidebar: ${sidebarOpen ? "open" : "closed"}`,
              `highlight mode: ${highlightOn ? "on" : "off"}`,
              `show highlights: ${showOn ? "on" : "off"}`,
            ];
            const footerH = 26;
            ctx.fillStyle = "#4c1d95";
            ctx.fillRect(0, snap.height - footerH, snap.width, footerH);
            ctx.fillStyle = "#ffffff";
            ctx.font = "12px ui-monospace, Menlo, monospace";
            ctx.textBaseline = "middle";
            ctx.fillText(`PDF viewer state — ${parts.join(" · ")}`,
                          10, snap.height - footerH / 2);
          } catch (_) { /* footer is nice-to-have */ }
          replacement = document.createElement("img");
          replacement.src = snap.toDataURL("image/png");
          replacement.style.cssText =
            `width:${rect.width}px;height:${rect.height}px;border:1px solid #b0b1b6;border-radius:6px;`;
        }
      } catch (_) { /* fall through */ }

      // Labeled placeholder fallback.
      if (!replacement) {
        replacement = document.createElement("div");
        replacement.className = "bug-iframe-placeholder";
        replacement.style.cssText = `
          width:${rect.width}px;height:${rect.height}px;
          display:flex;flex-direction:column;
          align-items:center;justify-content:center;
          background:#f5f5f5;border:2px dashed #b0b1b6;
          color:#4c1d95;font-family:ui-monospace,Menlo,monospace;
          font-size:14px;text-align:center;padding:20px;border-radius:6px;
        `;
        replacement.textContent = `[iframe — ${iframe.getAttribute("src") || "no src"}]`;
      }
      iframe.parentNode.insertBefore(replacement, iframe);
      iframe.style.display = "none";
      iframeReplacements.push({ iframe, replacement });
    }
    const restoreIframes = () => {
      for (const { iframe, replacement } of iframeReplacements) {
        iframe.style.display = "";
        replacement.remove();
      }
    };

    // Let the browser reflow before html2canvas measures.
    await new Promise(r => requestAnimationFrame(r));

    let canvas;
    // WebKit refuses a canvas larger than ~16384px on either side and hands
    // back an unusable one instead of throwing. Scale the capture down to
    // fit rather than let a tall page produce an empty screenshot.
    const MAX_CANVAS_DIM = 16000;
    const capW = document.documentElement.scrollWidth;
    const capH = document.documentElement.scrollHeight;
    const scale = Math.min(window.devicePixelRatio || 1,
                           MAX_CANVAS_DIM / Math.max(1, capW),
                           MAX_CANVAS_DIM / Math.max(1, capH));
    try {
      canvas = await window.html2canvas(document.body, {
        scale,
        useCORS: true,
        allowTaint: false,
        logging: false,
        // Force the capture at the FULL scrollable size so nothing is
        // clipped by viewport. Without windowHeight override html2canvas
        // uses window.innerHeight and cuts off below-the-fold content.
        windowWidth:  document.documentElement.scrollWidth,
        windowHeight: document.documentElement.scrollHeight,
        // Only exclude the floating button itself. Existing bug modals
        // are INCLUDED so meta-bug reports (a bug about the bug reporter,
        // a bug about anything popup-shaped) can screenshot the popup.
        ignoreElements: (el) => el.id === "dev-bug-btn",
      });
    } catch (e) {
      alert("screenshot failed: " + e.message);
      if (btn) btn.disabled = false;
      restoreIframes();
      // Restore before bailing out
      for (const s of savedStyles) {
        if (s.overflow) s.el.style.setProperty("overflow", s.overflow, s.overflowPrio);
        else            s.el.style.removeProperty("overflow");
        if (s.height)   s.el.style.setProperty("height",   s.height,   s.heightPrio);
        else            s.el.style.removeProperty("height");
      }
      return;
    }

    // An oversized canvas does not throw — it comes back unusable and
    // `toDataURL` returns the bare "data:," prefix, which saved as a
    // 0-byte screenshot. Say so instead of filing an empty image.
    if (!canvas || !canvas.width || !canvas.height ||
        canvas.toDataURL("image/png").length < 100) {
      console.warn("bug reporter: screenshot came back empty", capW, capH, scale);
      canvas = null;
    }

    // Restore inline styles so the app looks like it did before.
    restoreIframes();
    for (const s of savedStyles) {
      if (s.overflow) s.el.style.setProperty("overflow", s.overflow, s.overflowPrio);
      else            s.el.style.removeProperty("overflow");
      if (s.height)   s.el.style.setProperty("height",   s.height,   s.heightPrio);
      else            s.el.style.removeProperty("height");
    }
    if (btn) btn.disabled = false;
    if (!canvas) {
      alert("The screenshot came back empty, so no report was opened. " +
            "Scroll the page shorter and try again.");
      return;
    }
    openModal(canvas);
  }

  function openModal(screenshotCanvas) {
    const overlay = document.createElement("div");
    overlay.className = "dev-bug-modal-overlay";
    // Later modals stack visually above earlier ones. Base z-index for
    // this modal type is set in bug-reporter.css; nudge each nested
    // one 10 higher so the newest is always on top.
    overlay.style.zIndex = String(300 + modalStack.length * 10);
    overlay.innerHTML = `
      <div class="dev-bug-modal">
        <header>
          <h2>Bug report</h2>
          <span class="dev-tag">DEV ONLY</span>
          <button class="btn ghost" data-act="close">✕</button>
        </header>
        <div class="body">
          <div class="toolbar">
            <span>Drag on the screenshot to draw highlight boxes.</span>
            <div style="flex:1"></div>
            <button class="btn" data-act="undo">Undo</button>
            <button class="btn" data-act="clear">Clear boxes</button>
          </div>
          <div class="canvas-wrap">
            <img class="screenshot-img" />
            <canvas class="draw-overlay"></canvas>
          </div>
          <textarea placeholder="What's wrong? What did you expect vs. what happened?"></textarea>
        </div>
        <footer>
          <button class="btn" data-act="close">Cancel</button>
          <button class="btn primary" data-act="submit">Submit</button>
        </footer>
      </div>
    `;
    document.body.appendChild(overlay);
    modalStack.push(overlay);
    rectsPerModal.set(overlay, []);

    // Wire the screenshot into the img + set up the draw overlay at the
    // SAME pixel dimensions.
    const img = overlay.querySelector(".screenshot-img");
    const draw = overlay.querySelector(".draw-overlay");
    const dataUrl = screenshotCanvas.toDataURL("image/png");
    img.src = dataUrl;
    img.onload = () => {
      // The img may be scaled to fit; the canvas needs to match the
      // rendered size for pointer coords to line up, but we composite
      // at NATURAL size on submit.
      const rect = img.getBoundingClientRect();
      draw.width  = img.naturalWidth;
      draw.height = img.naturalHeight;
      // CSS scale to match rendered image size.
      draw.style.width  = rect.width  + "px";
      draw.style.height = rect.height + "px";
    };
    // Also refresh sizing if the modal is resized.
    window.addEventListener("resize", () => {
      const rect = img.getBoundingClientRect();
      draw.style.width  = rect.width  + "px";
      draw.style.height = rect.height + "px";
    });

    setupDrawing(draw, img, overlay);

    overlay.addEventListener("click", (e) => {
      const act = e.target.dataset && e.target.dataset.act;
      if (!act) return;
      // Only respond to actions on THIS overlay — clicks bubble up
      // from nested overlays if they're stacked, but each modal owns
      // its own action bar.
      if (!overlay.contains(e.target)) return;
      if (act === "close")  closeModal(overlay);
      if (act === "undo")   undoLast(draw, overlay);
      if (act === "clear")  clearBoxes(draw, overlay);
      if (act === "submit") submit(overlay, screenshotCanvas, draw);
    });

    // First modal registers the Esc listener; subsequent ones piggy-
    // back on it (closeModal always closes the topmost).
    if (modalStack.length === 1) document.addEventListener("keydown", escToClose);
  }

  function escToClose(e) {
    if (e.key === "Escape") closeModal();
  }

  function closeModal(which) {
    // No arg → close topmost. Explicit overlay arg → close that one.
    const target = which || modalStack[modalStack.length - 1];
    if (!target) return;
    const idx = modalStack.indexOf(target);
    if (idx === -1) return;
    modalStack.splice(idx, 1);
    target.remove();
    rectsPerModal.delete(target);
    if (modalStack.length === 0) document.removeEventListener("keydown", escToClose);
  }

  // ---------- Drawing rectangles ----------
  //
  // Rectangles are per-modal now (nested reports each get their own
  // set), keyed off the modal overlay via rectsPerModal WeakMap.

  function setupDrawing(drawCanvas, img, modalOverlay) {
    const rects = rectsPerModal.get(modalOverlay);
    const ctx = drawCanvas.getContext("2d");
    let drawing = false, startX = 0, startY = 0;

    // Cached for the duration of one drag. `getBoundingClientRect()` is
    // a forced synchronous layout, and calling it on every pointermove
    // was the second cost here after the full-canvas clear.
    let canvasRect = null;
    // The region the preview box painted last frame, so the next frame
    // knows what to erase.
    let lastPainted = null;
    // Latest pointer position awaiting a frame, and the pending rAF.
    // Pointer events fire far faster than the display refreshes; without
    // coalescing, several repaints happen between two frames and every
    // one but the last is thrown away.
    let pendingRect = null, rafId = 0;

    // Convert pointer coords (CSS pixels) to canvas coords (natural pixels).
    function toCanvas(clientX, clientY) {
      const rect = canvasRect || drawCanvas.getBoundingClientRect();
      const scaleX = drawCanvas.width  / rect.width;
      const scaleY = drawCanvas.height / rect.height;
      return {
        x: (clientX - rect.left) * scaleX,
        y: (clientY - rect.top)  * scaleY,
      };
    }

    // Repaint ONLY the region the preview can have touched.
    //
    // Committed boxes intersecting that region are re-stroked, because
    // the clear cannot tell the preview's pixels from theirs. Everything
    // is clipped to the dirty region, so a huge committed box costs only
    // the sliver that overlaps.
    function paint(preview) {
      const G = window.BugDrawGeom;
      const dirty = G.clampToCanvas(G.dirtyRegion(lastPainted, preview),
                                    drawCanvas.width, drawCanvas.height);
      lastPainted = preview;
      if (!dirty) return;
      ctx.save();
      ctx.beginPath();
      ctx.rect(dirty.x, dirty.y, dirty.w, dirty.h);
      ctx.clip();
      ctx.clearRect(dirty.x, dirty.y, dirty.w, dirty.h);
      for (const r of rects) {
        if (G.intersects(G.strokeBounds(r), dirty)) drawRect(ctx, r.x, r.y, r.w, r.h);
      }
      if (preview) drawRect(ctx, preview.x, preview.y, preview.w, preview.h);
      ctx.restore();
    }

    function cancelFrame() {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    }

    function endDrag(commit) {
      drawing = false;
      cancelFrame();
      // Paint the committed box (or erase the discarded preview) through
      // the same dirty path — a full redraw here would be one
      // 57-megapixel clear per box drawn.
      paint(commit);
      lastPainted = null;
      canvasRect = null;
      pendingRect = null;
    }

    drawCanvas.addEventListener("pointerdown", (e) => {
      drawing = true;
      canvasRect = drawCanvas.getBoundingClientRect();
      lastPainted = null;
      const p = toCanvas(e.clientX, e.clientY);
      startX = p.x; startY = p.y;
      drawCanvas.setPointerCapture(e.pointerId);
    });
    drawCanvas.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      const p = toCanvas(e.clientX, e.clientY);
      pendingRect = { x: startX, y: startY, w: p.x - startX, h: p.y - startY };
      if (rafId) return;                       // a frame is already queued
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        paint(pendingRect);
      });
    });
    drawCanvas.addEventListener("pointerup", (e) => {
      if (!drawing) return;
      const p = toCanvas(e.clientX, e.clientY);
      const w = p.x - startX, h = p.y - startY;
      const keep = Math.abs(w) > 5 && Math.abs(h) > 5;
      if (keep) rects.push({ x: startX, y: startY, w, h });
      endDrag(keep ? { x: startX, y: startY, w, h } : null);
    });
    // A capture lost mid-drag (window blur, a tablet pen leaving range)
    // otherwise leaves `drawing` true and a stale preview on screen.
    drawCanvas.addEventListener("pointercancel", () => {
      if (drawing) endDrag(null);
    });
  }

  function drawRect(ctx, x, y, w, h) {
    ctx.strokeStyle = "#e53e3e";
    // One definition of the stroke width, shared with the geometry that
    // sizes the repaint region. Two copies drifting apart shows up as
    // red smears where an old box was not fully erased.
    ctx.lineWidth = window.BugDrawGeom.LINE_WIDTH;
    ctx.strokeRect(x, y, w, h);
  }

  function redraw(canvas, ctx, rects) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const r of rects) drawRect(ctx, r.x, r.y, r.w, r.h);
  }

  function undoLast(drawCanvas, modalOverlay) {
    const rects = rectsPerModal.get(modalOverlay);
    rects.pop();
    redraw(drawCanvas, drawCanvas.getContext("2d"), rects);
  }

  function clearBoxes(drawCanvas, modalOverlay) {
    const rects = rectsPerModal.get(modalOverlay);
    rects.length = 0;
    redraw(drawCanvas, drawCanvas.getContext("2d"), rects);
  }

  // ---------- Composite + submit ----------

  async function submit(modal, screenshotCanvas, drawOverlay) {
    const textarea = modal.querySelector("textarea");
    const description = textarea.value.trim();

    // Composite: draw screenshot + all boxes onto a fresh canvas.
    const out = document.createElement("canvas");
    out.width  = screenshotCanvas.width;
    out.height = screenshotCanvas.height;
    const ctx = out.getContext("2d");
    ctx.drawImage(screenshotCanvas, 0, 0);
    const rects = rectsPerModal.get(modal) || [];
    for (const r of rects) drawRect(ctx, r.x, r.y, r.w, r.h);
    const dataUrl = out.toDataURL("image/png");

    // POST to server.
    try {
      const r = await fetch("/api/dev/bug-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          description,
          screenshot: dataUrl,
          view_context: {
            url:        window.location.href,
            user_agent: navigator.userAgent,
            viewport:   `${window.innerWidth}x${window.innerHeight}`,
          },
        }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
      showToast(`saved to ${body.label}`, "ok");
      closeModal(modal);
    } catch (e) {
      alert("submit failed: " + e.message);
    }
  }

  function showToast(msg, kind) {
    // Piggy-back on the main app's toast if it exists.
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast" + (kind ? " " + kind : "");
    el.hidden = false;
    setTimeout(() => { el.hidden = true; }, 3500);
  }

  // ---------- Boot ----------

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addButton);
  } else {
    addButton();
  }
})();
