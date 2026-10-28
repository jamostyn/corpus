// Tests for src/dev_only/draw-geometry.js — which pixels the bug
// reporter has to repaint while a box is being dragged.
//
// Jack, 2026-09-21: "dragging the red box is super laggy."
//
// The cause was `ctx.clearRect(0, 0, w, h)` on every pointermove over a
// canvas sized to the whole scrolled screenshot — 3422 x 16760 in the
// report that raised it, 57 megapixels. The fix repaints a dirty region
// instead, and these cover the maths that decides what that region is.
//
// A wrong region does not throw. It leaves red smears on the screenshot
// where an old box was not erased, or eats a slice out of a box the
// user already committed — both silent, which is why this is the part
// that got pulled out into a pure module and tested.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const G = loadInVM(["dev_only/draw-geometry.js"]).window.BugDrawGeom;

// Objects built inside the vm sandbox carry THAT realm's
// Object.prototype, and `assert.deepStrictEqual` compares prototypes —
// so a rect that is field-for-field identical still fails. Spreading
// rebuilds it in this realm. Costs one call; saves the next person
// twenty minutes staring at two objects that print the same.
const plain = (o) => (o == null ? o : { ...o });

// ---------- normalize ----------

test("normalizes a box dragged up and to the left", () => {
  // Dragging from bottom-right to top-left gives negative w/h. Every
  // later step (bounds, intersection, clearRect) is meaningless on a
  // negative size, and this is the direction a right-handed user drags
  // about half the time.
  assert.deepEqual(plain(G.normalize({ x: 100, y: 80, w: -40, h: -30 })),
                   { x: 60, y: 50, w: 40, h: 30 });
});

test("leaves an already-positive box alone", () => {
  assert.deepEqual(plain(G.normalize({ x: 5, y: 6, w: 7, h: 8 })),
                   { x: 5, y: 6, w: 7, h: 8 });
});

// ---------- strokeBounds ----------

test("stroke bounds cover the ink outside the path", () => {
  // Canvas strokes straddle the path: half the line width falls outside
  // the rectangle. Clearing only the rectangle leaves a red frame
  // behind on every move — the exact smear this is here to prevent.
  const b = G.strokeBounds({ x: 100, y: 100, w: 50, h: 20 });
  assert.ok(b.x < 100 && b.y < 100);
  assert.ok(b.x + b.w > 150 && b.y + b.h > 120);
});

test("stroke bounds normalize first", () => {
  // Catches padding a negative-size rect, which pushes the origin the
  // wrong way and clears a region that does not contain the box.
  const a = G.strokeBounds({ x: 100, y: 80, w: -40, h: -30 });
  const b = G.strokeBounds({ x: 60, y: 50, w: 40, h: 30 });
  assert.deepEqual(plain(a), plain(b));
});

// ---------- union / dirtyRegion ----------

test("the dirty region covers both where the box was and where it is", () => {
  // The heart of it. Repainting only the NEW position leaves the
  // previous frame's box on screen — a trail of red rectangles down the
  // screenshot, which is worse than the lag it replaced.
  const prev = { x: 10, y: 10, w: 20, h: 20 };
  const next = { x: 200, y: 300, w: 50, h: 50 };
  const d = G.dirtyRegion(prev, next);
  const pb = G.strokeBounds(prev), nb = G.strokeBounds(next);
  assert.ok(d.x <= pb.x && d.y <= pb.y);
  assert.ok(d.x + d.w >= nb.x + nb.w);
  assert.ok(d.y + d.h >= nb.y + nb.h);
});

test("dirty region handles the first and last frame of a drag", () => {
  // `prev` is null on the first move, `next` is null when the preview is
  // committed or discarded. Returning null for the live one would skip
  // the repaint and strand a box on the canvas.
  assert.deepEqual(plain(G.dirtyRegion(null, { x: 0, y: 0, w: 10, h: 10 })),
                   plain(G.strokeBounds({ x: 0, y: 0, w: 10, h: 10 })));
  assert.deepEqual(plain(G.dirtyRegion({ x: 0, y: 0, w: 10, h: 10 }, null)),
                   plain(G.strokeBounds({ x: 0, y: 0, w: 10, h: 10 })));
  assert.equal(G.dirtyRegion(null, null), null);
});

// ---------- intersects ----------

test("a committed box grazing the dirty region counts as intersecting", () => {
  // Inclusive on purpose. An exclusive test drops a box whose stroke
  // touches the cleared edge, and the clear then eats a sliver of it.
  const a = { x: 0, y: 0, w: 10, h: 10 };
  const b = { x: 10, y: 0, w: 10, h: 10 };   // edges exactly touching
  assert.equal(G.intersects(a, b), true);
});

test("boxes that share no pixel do not intersect", () => {
  // Catches an over-inclusive test, which would re-stroke every
  // committed box on every frame — the O(n) cost the dirty region
  // exists to avoid.
  assert.equal(G.intersects({ x: 0, y: 0, w: 10, h: 10 },
                            { x: 40, y: 0, w: 10, h: 10 }), false);
  assert.equal(G.intersects({ x: 0, y: 0, w: 10, h: 10 },
                            { x: 0, y: 40, w: 10, h: 10 }), false);
});

// ---------- clampToCanvas ----------

test("clamps a region that runs off the canvas", () => {
  // Dragging past the window edge produces negative coordinates. A
  // negative origin makes the clearRect size wrong, so the visible part
  // is not fully cleared.
  const c = G.clampToCanvas({ x: -50, y: -50, w: 100, h: 100 }, 1000, 1000);
  assert.deepEqual(plain(c), { x: 0, y: 0, w: 50, h: 50 });
});

test("clamps against the far edge too", () => {
  const c = G.clampToCanvas({ x: 900, y: 900, w: 500, h: 500 }, 1000, 1000);
  assert.deepEqual(plain(c), { x: 900, y: 900, w: 100, h: 100 });
});

test("a region entirely off-canvas clamps to nothing", () => {
  // The caller skips painting on null. Returning a zero- or
  // negative-sized rect instead would have canvas silently no-op, which
  // works by luck rather than by contract.
  assert.equal(G.clampToCanvas({ x: -500, y: 0, w: 100, h: 100 }, 1000, 1000), null);
  assert.equal(G.clampToCanvas({ x: 2000, y: 0, w: 100, h: 100 }, 1000, 1000), null);
});

// ---------- the cost claim ----------

test("a dragged box repaints a small region, not the whole canvas", () => {
  // The regression that matters. If someone reverts to clearing the
  // full canvas, this is the number that moves: dragging a 200x100 box
  // near the top of a 3422x16760 screenshot must not dirty anything
  // close to 57 megapixels.
  const CANVAS_W = 3422, CANVAS_H = 16760;     // the real report's size
  const prev = { x: 100, y: 100, w: 200, h: 100 };
  const next = { x: 100, y: 100, w: 208, h: 104 };
  const d = G.clampToCanvas(G.dirtyRegion(prev, next), CANVAS_W, CANVAS_H);
  const dirtyPixels = d.w * d.h;
  assert.ok(dirtyPixels < 30000,
            `dirty region is ${dirtyPixels}px, expected well under 30k`);
  assert.ok(dirtyPixels < CANVAS_W * CANVAS_H / 1000);
});

// ---------- the shared constant ----------

test("the stroke width is exported for the drawing code to use", () => {
  // bug-reporter.js sets `ctx.lineWidth` from this. A second literal
  // there would drift from the padding here, and under-padding shows up
  // as a permanent red line on the saved screenshot.
  assert.equal(typeof G.LINE_WIDTH, "number");
  assert.ok(G.LINE_WIDTH > 0);
});
