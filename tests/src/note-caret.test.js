// Handing focus back to the note editor must not scroll it.
//
// Bug (2026-09-25): adding a paper via a link scrolled the note to the
// top. The link picker takes focus; the editor used
// `body.focus()` to get it back, which scrolls to where a fresh caret
// would go — the top — before the saved range is restored.
//
// Two tests: the helper's behaviour (real function, fake DOM), and a
// source check that no bare `body.focus()` survives in notes.js — every
// path that restores the caret now goes through the one helper, and a
// new copy of the old pattern would bring the jump back silently.

const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

test("restoring the caret focuses without scrolling, then puts the range back", () => {
  // Catches dropping `preventScroll` (the reported bug) and restoring
  // the range before focusing, which a focus call can then reset.
  const calls = [];
  const sel = {
    removeAllRanges: () => calls.push("clear"),
    addRange: (r) => calls.push(["add", r]),
  };
  const sandbox = loadInVM(["notes.js"], {
    document: { addEventListener() {}, getSelection: () => sel },
  });
  const body = { focus: (opts) => calls.push(["focus", opts]) };
  const range = { marker: "saved" };
  sandbox._restoreCaret(body, range);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)),
                   [["focus", { preventScroll: true }], "clear", ["add", { marker: "saved" }]]);
});

test("no path in notes.js refocuses the editor the scrolling way", () => {
  // Catches a new insert path (or an old one reverted) calling
  // `body.focus()` bare. The link picker, the highlight link and the
  // font-size input all had their own copy of that call.
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "src", "notes.js"), "utf8");
  const bare = src.split("\n").filter(l => /\bbody\.focus\(\s*\)/.test(l));
  assert.deepEqual(bare, [], "bare body.focus() — use _restoreCaret or focus({preventScroll: true})");
});
