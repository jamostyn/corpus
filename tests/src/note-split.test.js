// The divider between a popped-out note and its PDF panel
// (note-workspace.js::splitPercent / _wireSplit, styles.css .nw-split).
//
// Requirement (2026-10-28): in a popped-out note, drag the line between
// the note and the PDF to change how much of the window each takes.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { loadInVM } = require("./harness");

const CSS = fs.readFileSync(path.join(__dirname, "..", "..", "src", "styles.css"), "utf8");

function fakeEl() {
  return {
    listeners: {}, props: {}, captured: null,
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
    fire(t, e) { (this.listeners[t] || []).forEach(f => f({ preventDefault() {}, ...e })); },
    setPointerCapture(id) { this.captured = id; },
    style: {
      props: {},
      setProperty(k, v) { this.props[k] = v; },
      getPropertyValue(k) { return this.props[k] || ""; },
    },
    getBoundingClientRect() { return { left: 100, width: 1000 }; },
  };
}

function load() {
  const store = {};
  const classes = new Set();
  const sb = loadInVM(["note-workspace.js"], {
    localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    document: { addEventListener() {}, body: { classList: {
      add: c => classes.add(c), remove: c => classes.delete(c) } } },
  });
  return { NW: sb.NoteWorkspace, store, classes };
}

test("the note's share follows the pointer across the workspace", () => {
  const { NW } = load();
  assert.equal(NW.splitPercent(100 + 350, 100, 1000), 35);
  assert.equal(NW.splitPercent(100 + 625, 100, 1000), 62.5);
});

test("neither side can be dragged shut", () => {
  // Catches a missing clamp: dragging to the window edge would leave the
  // note or the PDF zero-wide, with the divider hard to grab back.
  const { NW } = load();
  assert.equal(NW.splitPercent(100, 100, 1000), NW.SPLIT_MIN);
  assert.equal(NW.splitPercent(5000, 100, 1000), NW.SPLIT_MAX);
  assert.ok(NW.SPLIT_MIN >= 15 && NW.SPLIT_MAX <= 85);
  assert.equal(NW.splitPercent(500, 0, 0), null, "an unmeasured workspace changes nothing");
});

test("a drag sets the split, keeps it, and blocks the iframe only while dragging", () => {
  // Catches (a) moves applied without a press, (b) the PDF iframe keeping
  // pointer events mid-drag (the drag dies when it crosses the panel), and
  // (c) the split not being remembered for the next note window.
  const { NW, store, classes } = load();
  const ws = fakeEl(), split = fakeEl();
  NW._wireSplit(ws, split);
  assert.equal(ws.style.props["--nw-note-pct"], "50");

  split.fire("pointermove", { clientX: 400 });
  assert.equal(ws.style.props["--nw-note-pct"], "50", "a move without a press is ignored");

  split.fire("pointerdown", { pointerId: 7 });
  assert.ok(classes.has("nw-resizing"));
  assert.equal(split.captured, 7);
  split.fire("pointermove", { clientX: 400 });
  assert.equal(ws.style.props["--nw-note-pct"], "30");
  split.fire("pointerup", {});
  assert.ok(!classes.has("nw-resizing"));
  assert.equal(store["corpus.noteSplitPct"], "30");

  // A new window opens at the remembered split; double-click resets it.
  const ws2 = fakeEl(), split2 = fakeEl();
  NW._wireSplit(ws2, split2);
  assert.equal(ws2.style.props["--nw-note-pct"], "30");
  split2.fire("dblclick", {});
  assert.equal(ws2.style.props["--nw-note-pct"], "50");
});

test("the stylesheet sizes both sides from the divider's value", () => {
  // Catches the JS setting --nw-note-pct while the CSS still uses the
  // fixed 50/50 flex basis (dragging would do nothing visible), and the
  // iframe rule that keeps a drag alive being dropped.
  assert.match(CSS, /\.note-workspace\.nw-open \.nw-note\s*\{[^}]*var\(--nw-note-pct/);
  assert.match(CSS, /body\.nw-resizing iframe\s*\{\s*pointer-events:\s*none/);
  assert.match(CSS, /\.nw-split\[hidden\]\s*\{\s*display:\s*none !important/);
});
