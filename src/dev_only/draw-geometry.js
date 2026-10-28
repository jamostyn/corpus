// Dirty-region maths for the bug reporter's annotation boxes.
//
// Jack, 2026-09-21: "dragging the red box is super laggy."
//
// WHY THIS IS SLOW WITHOUT IT
// ---------------------------
// The draw canvas is sized to the screenshot's NATURAL pixels
// (`draw.width = img.naturalWidth` in bug-reporter.js), and a Corpus
// screenshot is the whole scrolled page. The report that prompted this
// was 3422 x 16760 — 57 MEGAPIXELS. The original `pointermove` handler
// called `ctx.clearRect(0, 0, width, height)` and re-stroked every
// committed box, on every single move event. That is ~230 MB of pixel
// writes per mouse movement.
//
// The fix is to repaint only the region that can have changed: the
// union of where the preview box was last frame and where it is now.
// Dragging a 200x100 box then costs ~20k pixels instead of 57M.
//
// This module is pure — no canvas, no DOM — so the maths that decides
// WHAT to repaint is testable, which the drawing code itself is not.
// A wrong region here does not crash; it leaves red smears on the
// screenshot where an old box was not erased, so it needs real
// coverage rather than a squint.

window.BugDrawGeom = (function () {
  "use strict";

  // The stroke straddles the path: half the width falls outside the
  // rectangle. Padding by the FULL width rather than half is deliberate
  // slack — a half-pixel of under-clearing leaves a permanent red line
  // on the screenshot, and over-clearing by three pixels costs nothing.
  const LINE_WIDTH = 4;

  /** Positive-width form of a rect that may have been dragged up or left. */
  function normalize(r) {
    if (!r) return null;
    const w = r.w || 0, h = r.h || 0;
    return {
      x: Math.min(r.x, r.x + w),
      y: Math.min(r.y, r.y + h),
      w: Math.abs(w),
      h: Math.abs(h),
    };
  }

  /** The pixels a stroked rect actually touches. */
  function strokeBounds(r) {
    const n = normalize(r);
    if (!n) return null;
    return {
      x: n.x - LINE_WIDTH,
      y: n.y - LINE_WIDTH,
      w: n.w + LINE_WIDTH * 2,
      h: n.h + LINE_WIDTH * 2,
    };
  }

  function union(a, b) {
    if (!a) return b || null;
    if (!b) return a;
    const x = Math.min(a.x, b.x);
    const y = Math.min(a.y, b.y);
    const x1 = Math.max(a.x + a.w, b.x + b.w);
    const y1 = Math.max(a.y + a.h, b.y + b.h);
    return { x, y, w: x1 - x, h: y1 - y };
  }

  /** Do these two rects share any pixel? Touching edges count.
   *
   *  Inclusive on purpose: a committed box whose stroke merely grazes
   *  the cleared region still has to be re-drawn, or the clear eats a
   *  sliver of it. */
  function intersects(a, b) {
    if (!a || !b) return false;
    return !(a.x + a.w < b.x || b.x + b.w < a.x ||
             a.y + a.h < b.y || b.y + b.h < a.y);
  }

  /** Region to repaint when the preview box moves from `prev` to `next`.
   *
   *  Either may be null — `prev` on the first frame of a drag, `next`
   *  on the last, when the preview is committed and disappears. */
  function dirtyRegion(prev, next) {
    return union(strokeBounds(prev), strokeBounds(next));
  }

  /** Trim a region to the canvas.
   *
   *  A drag that leaves the window produces coordinates outside the
   *  canvas; clearing there is wasted work, and a negative origin makes
   *  `clearRect` sizes meaningless. Returns null when nothing is left. */
  function clampToCanvas(r, canvasW, canvasH) {
    if (!r) return null;
    const x = Math.max(0, r.x);
    const y = Math.max(0, r.y);
    const x1 = Math.min(canvasW, r.x + r.w);
    const y1 = Math.min(canvasH, r.y + r.h);
    if (x1 <= x || y1 <= y) return null;
    return { x, y, w: x1 - x, h: y1 - y };
  }

  return { LINE_WIDTH, normalize, strokeBounds, union, intersects,
           dirtyRegion, clampToCanvas };
})();
