// Tests for src/nav.js — pure arrow-key navigation arithmetic.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const { window } = loadInVM(["nav.js"]);
const N = window.Nav;

const DOWN = { direction: 1  };
const UP   = { direction: -1 };

// ---------- Empty / degenerate ----------

test("empty list — no move in either direction", () => {
  assert.equal(N.nextIndex({ itemCount: 0, currentIndex: -1, ...DOWN }), null);
  assert.equal(N.nextIndex({ itemCount: 0, currentIndex: -1, ...UP   }), null);
});

// ---------- No current selection ----------

test("no selection + ArrowDown → 0 (first item)", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: -1, ...DOWN }), 0);
});

test("no selection + ArrowUp → last item", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: -1, ...UP }), 4);
});

test("out-of-range currentIndex treated as no selection", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: 99,  ...DOWN }), 0);
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: -99, ...UP   }), 4);
});

// ---------- Normal middle-of-list moves ----------

test("middle + ArrowDown → currentIndex + 1", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: 2, ...DOWN }), 3);
});

test("middle + ArrowUp → currentIndex - 1", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: 2, ...UP }), 1);
});

// ---------- Boundary — clamps, does not wrap ----------

test("last item + ArrowDown → null (no move, no wrap)", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: 4, ...DOWN }), null);
});

test("first item + ArrowUp → null (no move, no wrap)", () => {
  assert.equal(N.nextIndex({ itemCount: 5, currentIndex: 0, ...UP }), null);
});

// ---------- Single-item list ----------

test("single item + any direction from that item → null", () => {
  assert.equal(N.nextIndex({ itemCount: 1, currentIndex: 0, ...DOWN }), null);
  assert.equal(N.nextIndex({ itemCount: 1, currentIndex: 0, ...UP   }), null);
});

test("single item + no selection → 0 regardless of direction", () => {
  assert.equal(N.nextIndex({ itemCount: 1, currentIndex: -1, ...DOWN }), 0);
  assert.equal(N.nextIndex({ itemCount: 1, currentIndex: -1, ...UP   }), 0);
});
