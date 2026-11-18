// Resizing a table inside a note (notes.js _noteTableHitTest /
// _startNoteTableResize).
//
// Requirement (2026-10-29): dragging the table's right edge resizes only
// the right-most column — as every other column border resizes only its
// own column — instead of stretching every column.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "notes.js"), "utf8");
const start = SRC.indexOf("const _NOTE_TABLE_EDGE_PX");
const end = SRC.indexOf("// --- Table right-click context menu ---");

function load() {
  const listeners = {};
  // Animation frames are queued, not run: a test steps them with frames.run().
  const frames = { queue: [], cancelled: 0, run() { const q = this.queue; this.queue = []; q.forEach(f => f()); } };
  const sb = {
    document: { addEventListener: (t, f) => { listeners[t] = f; }, removeEventListener() {} },
    requestAnimationFrame: (f) => { frames.queue.push(f); return frames.queue.length; },
    cancelAnimationFrame: () => { frames.cancelled++; frames.queue = []; },
  };
  vm.createContext(sb);
  vm.runInContext(SRC.slice(start, end) + "\nthis.hit = _noteTableHitTest; this.drag = _startNoteTableResize; this.edgeScroll = _noteTableEdgeScroll;", sb);
  return { sb, listeners, frames };
}

// A 3-column table: columns 100 / 80 / 120 px, from x=0, rows of 20 px.
// The note the table sits in: visible right edge at x=320. Like a real
// scroll box it cannot scroll past its content (the table, from x=0).
function fakeNote() {
  let left = 0;
  const note = {
    table: null,
    get scrollLeft() { return left; },
    set scrollLeft(v) { left = Math.max(0, Math.min(v, parseFloat(note.table.style.width) - 320)); },
    getBoundingClientRect: () => ({ left: 0, right: 320 }),
  };
  return note;
}

function fakeTable(note = null) {
  const widths = [100, 80, 120];
  let x = 0;
  const cells = widths.map(w => { const r = { left: x, right: x + w, top: 0, bottom: 20 }; x += w; return { getBoundingClientRect: () => r }; });
  const row = { children: cells, firstElementChild: cells[0], getBoundingClientRect: () => ({ top: 0, bottom: 20 }), style: { height: "20px" } };
  const cols = widths.map(w => ({ style: { width: `${w}px` }, getBoundingClientRect: () => ({ width: w }) }));
  const table = {
    cols, style: { width: "300px" },
    closest: (q) => (q === ".note-body" ? note : null),
    getBoundingClientRect: () => ({ left: 0, right: 300, top: 0, bottom: 40 }),
    querySelector: (q) => (q === "tr" ? row : null),
    querySelectorAll: (q) => (q === "colgroup > col" ? cols : q === "tr" ? [row] : []),
  };
  if (note) note.table = table;
  return table;
}

test("the right edge grabs the last column, not the whole table", () => {
  // Catches the old "table-h" mode coming back: a right-edge drag would
  // scale every column.
  const { sb } = load();
  const t = fakeTable();
  assert.deepEqual({ ...sb.hit({ clientX: 299, clientY: 10 }, t) }, { mode: "col", idx: 2 });
});

test("dragging the right edge widens only the last column", () => {
  // Catches the drag rescaling the other columns (they would shift),
  // and the table width falling out of step with its columns.
  const { sb, listeners } = load();
  const t = fakeTable();
  sb.drag({ clientX: 300, clientY: 10 }, t, { mode: "col", idx: 2 }, () => {});
  listeners.mousemove({ clientX: 350, clientY: 10 });
  assert.deepEqual(t.cols.map(c => c.style.width), ["100px", "80px", "170px"]);
  assert.equal(t.style.width, "350px");
});

test("a column cannot push the table past the size the server keeps", () => {
  // Catches column drags ignoring the 4000 px cap the sanitiser applies
  // (the save would silently come back narrower).
  const { sb, listeners } = load();
  const t = fakeTable();
  sb.drag({ clientX: 300, clientY: 10 }, t, { mode: "col", idx: 2 }, () => {});
  listeners.mousemove({ clientX: 9000, clientY: 10 });
  assert.equal(t.style.width, "4000px");
});

// Requirement (2026-11-12): dragging a table's right edge past the edge
// of the note scrolls the note sideways, so the table can be dragged out
// as far as wanted (up to the 4000 px the server keeps).

test("edge scrolling starts near the note's edge and is fastest past it", () => {
  // Catches scrolling that never starts, starts anywhere in the note, or
  // stops when the pointer leaves the note (the usual way to drag "far").
  const { sb } = load();
  assert.equal(sb.edgeScroll(200, 320), 0);
  assert.ok(sb.edgeScroll(300, 320) > 0);
  assert.equal(sb.edgeScroll(320, 320), sb.edgeScroll(900, 320));
  assert.ok(sb.edgeScroll(320, 320) > sb.edgeScroll(300, 320));
});

test("holding the pointer at the edge keeps scrolling and widening", () => {
  // Catches a scroll that does not widen the table (the note cannot
  // scroll past its content, so it would stop after one step), and a
  // width that ignores the scrolled distance (the table would stop
  // growing as soon as the note scrolls under a still pointer).
  const { sb, listeners, frames } = load();
  const note = fakeNote();
  const t = fakeTable(note);
  sb.drag({ clientX: 300, clientY: 10 }, t, { mode: "col", idx: 2 }, () => {});
  listeners.mousemove({ clientX: 330, clientY: 10 });
  assert.equal(t.style.width, "330px");
  const step = sb.edgeScroll(330, 320);
  frames.run();
  frames.run();
  assert.equal(note.scrollLeft, 2 * step);
  assert.equal(t.style.width, `${330 + 2 * step}px`);
});

test("letting go stops the scrolling", () => {
  // Catches the frame loop outliving the drag: the note would keep
  // scrolling (and the table widening) after the button is released.
  const { sb, listeners, frames } = load();
  const t = fakeTable(fakeNote());
  sb.drag({ clientX: 300, clientY: 10 }, t, { mode: "col", idx: 2 }, () => {});
  listeners.mouseup();
  assert.equal(frames.cancelled, 1);
  assert.equal(frames.queue.length, 0);
});

test("a height drag does not scroll sideways", () => {
  // Catches the edge scroll running for row / bottom-edge drags, where
  // a pointer near the right edge would push the note sideways.
  const { sb, listeners, frames } = load();
  const note = fakeNote();
  const t = fakeTable(note);
  t.style.width = "400px";   // wider than the note, so it COULD scroll
  sb.drag({ clientX: 100, clientY: 40 }, t, { mode: "table-v" }, () => {});
  listeners.mousemove({ clientX: 330, clientY: 60 });
  frames.run();
  assert.equal(note.scrollLeft, 0);
});

test("a note table may be wider than the note", () => {
  // Catches `max-width: 100%` coming back on note tables: the table would
  // be squeezed to the note's width and the drag would appear to stop at
  // the edge however far the note scrolled.
  const css = fs.readFileSync(path.join(__dirname, "..", "..", "src", "styles.css"), "utf8");
  const i = css.indexOf(".note-body table.note-table {");
  const rule = css.slice(i, css.indexOf("}", i));
  assert.ok(i !== -1);
  assert.doesNotMatch(rule.replace(/\/\*[\s\S]*?\*\//g, ""), /max-width/);
});
