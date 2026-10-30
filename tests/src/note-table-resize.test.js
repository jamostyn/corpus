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
  const sb = { document: { addEventListener: (t, f) => { listeners[t] = f; }, removeEventListener() {} } };
  vm.createContext(sb);
  vm.runInContext(SRC.slice(start, end) + "\nthis.hit = _noteTableHitTest; this.drag = _startNoteTableResize;", sb);
  return { sb, listeners };
}

// A 3-column table: columns 100 / 80 / 120 px, from x=0, rows of 20 px.
function fakeTable() {
  const widths = [100, 80, 120];
  let x = 0;
  const cells = widths.map(w => { const r = { left: x, right: x + w, top: 0, bottom: 20 }; x += w; return { getBoundingClientRect: () => r }; });
  const row = { children: cells, firstElementChild: cells[0], getBoundingClientRect: () => ({ top: 0, bottom: 20 }), style: { height: "20px" } };
  const cols = widths.map(w => ({ style: { width: `${w}px` }, getBoundingClientRect: () => ({ width: w }) }));
  return {
    cols, style: { width: "300px" },
    getBoundingClientRect: () => ({ left: 0, right: 300, top: 0, bottom: 40 }),
    querySelector: (q) => (q === "tr" ? row : null),
    querySelectorAll: (q) => (q === "colgroup > col" ? cols : q === "tr" ? [row] : []),
  };
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
