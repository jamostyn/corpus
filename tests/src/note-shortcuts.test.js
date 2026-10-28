// Tests for the note editor's formatting chords (⌘B / ⌘U / ⌘I / ⌘S).
//
// Unlike the PDF highlight module, notes.js loads cleanly in the vm
// harness, so these read the REAL _NOTE_TOOLBAR rather than asserting
// on source text. `_NOTE_TOOLBAR` is a top-level `const`, which does
// not become a sandbox property, so it is read back with
// vm.runInContext against the same context.
//
// What is NOT covered: the keydown handler itself. It lives inside
// _wireNoteEditor, which needs the note-detail DOM, a live note, and
// document.execCommand — none of which the harness provides. The
// dispatch path is asserted structurally in
// tests/test_note_shortcuts.py; whether ⌘B actually bolds is manual.

const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const sandbox = loadInVM(["notes.js"]);
const TOOLBAR = vm.runInContext("_NOTE_TOOLBAR", sandbox);

const byCmd = (cmd) => TOOLBAR.find(b => b.cmd === cmd);
const keyed = () => TOOLBAR.filter(b => b.key);

test("all four formatting commands declare a keyboard chord", () => {
  // Catches: adding a formatting button without its chord, or dropping
  // one. `key` is the ONLY declaration of a chord — the keydown handler
  // looks the entry up rather than carrying its own list — so a missing
  // `key` silently means "this button has no shortcut".
  for (const [cmd, key] of [["bold", "b"], ["italic", "i"],
                            ["underline", "u"], ["strikeThrough", "s"]]) {
    const entry = byCmd(cmd);
    assert.ok(entry, `no toolbar entry for ${cmd}`);
    assert.equal(entry.key, key, `${cmd} should be bound to ⌘${key.toUpperCase()}`);
  }
});

test("every keyed entry also has a cmd for the handler to dispatch", () => {
  // Catches: a `key` on a non-command button (table insert, undo, the
  // link picker). The handler resolves a chord to a button via
  // `[data-cmd="…"]`, so a keyed entry without a cmd matches nothing
  // and the chord silently does nothing.
  for (const b of keyed()) {
    assert.ok(b.cmd, `toolbar entry with key ${b.key} has no cmd`);
  }
});

test("no two toolbar entries claim the same chord", () => {
  // Catches: a duplicate `key`. `.find()` takes the first match, so the
  // second entry's chord would silently never fire.
  const keys = keyed().map(b => b.key);
  assert.equal(new Set(keys).size, keys.length,
    `duplicate chord in _NOTE_TOOLBAR: ${keys.join(", ")}`);
});

test("chords are single lowercase letters", () => {
  // Catches: an uppercase or multi-char `key`. The handler lowercases
  // `e.key` before comparing, so "S" or "Cmd+S" would never match and
  // the chord would be dead with no error.
  for (const b of keyed()) {
    assert.match(b.key, /^[a-z]$/, `bad chord ${JSON.stringify(b.key)}`);
  }
});

test("strikethrough's title advertises its chord like the others", () => {
  // Catches: shipping the binding without telling anyone. B/I/U already
  // named their chord in the tooltip; S did not, because it had no
  // chord to name. A shortcut nobody can discover is nearly as bad as
  // no shortcut.
  for (const cmd of ["bold", "italic", "underline", "strikeThrough"]) {
    assert.match(byCmd(cmd).title, /⌘/,
      `${cmd} tooltip should show its chord: ${byCmd(cmd).title}`);
  }
});
