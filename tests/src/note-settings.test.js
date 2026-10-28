// Tests for the note header's Settings dropdown (notes.js::_wireNoteSettings).
//
// Requirement (2026-09-29): delete sits behind a settings button that
// opens a dropdown with a close control; delete is the only option for now.
//
// The real function is cut out of notes.js by marker and run against a
// small fake DOM; the markup assertions read notes.js's template.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "notes.js"), "utf8");
const START = SRC.indexOf("function _wireNoteSettings");
const END = SRC.indexOf("// ---- end note settings dropdown");
const SNIPPET = SRC.slice(START, END);

function el(id, parent) {
  const e = {
    id, parent, hidden: false, attrs: {}, listeners: {}, focused: false,
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
    contains(x) { for (let n = x; n; n = n.parent) if (n === this) return true; return false; },
    focus() { this.focused = true; },
    click() { (this.listeners.click || []).forEach(f => f({ target: this })); },
  };
  return e;
}

function setup() {
  const root = el("root");
  const btn = el("btn-note-settings", root);
  const menu = el("note-settings-menu", root);
  menu.hidden = true;
  const close = el("btn-note-settings-close", menu);
  const del = el("btn-note-delete", menu);
  const elsewhere = el("elsewhere", root);
  const byId = { "#btn-note-settings": btn, "#note-settings-menu": menu,
                 "#btn-note-settings-close": close, "#btn-note-delete": del };
  root.querySelector = (s) => byId[s] || null;
  const docListeners = {};
  const document = {
    addEventListener(t, f) { (docListeners[t] ||= new Set()).add(f); },
    removeEventListener(t, f) { docListeners[t]?.delete(f); },
  };
  const fire = (t, ev) => [...(docListeners[t] || [])].forEach(f => f(ev));
  const deletes = [];
  const ctx = { document };
  vm.createContext(ctx);
  vm.runInContext(SNIPPET, ctx);
  ctx._wireNoteSettings(root, () => deletes.push(menu.hidden));
  return { btn, menu, close, del, elsewhere, fire, docListeners, deletes };
}

test("Settings opens the menu and toggles it closed again", () => {
  // Catches the button not opening anything, or opening but never closing.
  const t = setup();
  t.btn.click();
  assert.equal(t.menu.hidden, false);
  assert.equal(t.btn.attrs["aria-expanded"], "true");
  t.btn.click();
  assert.equal(t.menu.hidden, true);
});

test("the × closes the menu", () => {
  // Catches the close button doing nothing.
  const t = setup();
  t.btn.click();
  t.close.click();
  assert.equal(t.menu.hidden, true);
  assert.equal(t.btn.attrs["aria-expanded"], "false");
});

test("Delete closes the menu first, then asks to delete", () => {
  // Catches Delete not reaching the delete path, or the confirm dialog
  // appearing over a still-open menu.
  const t = setup();
  t.btn.click();
  t.del.click();
  assert.deepEqual(t.deletes, [true]);
});

test("Escape and a click outside close it; a click inside does not", () => {
  // Catches a menu that can only be dismissed with the × — and an
  // outside-click check so broad it closes when the menu itself is used.
  const t = setup();
  t.btn.click();
  t.fire("mousedown", { target: t.del });
  assert.equal(t.menu.hidden, false);
  t.fire("mousedown", { target: t.elsewhere });
  assert.equal(t.menu.hidden, true);
  t.btn.click();
  t.fire("keydown", { key: "Escape", stopPropagation() {} });
  assert.equal(t.menu.hidden, true);
  assert.equal(t.btn.focused, true);
});

test("document listeners exist only while the menu is open", () => {
  // Catches leaking a document-wide mousedown/keydown handler per note
  // opened — they would pile up and fire for every click in the app.
  const t = setup();
  t.btn.click();
  assert.equal(t.docListeners.mousedown.size, 1);
  t.close.click();
  assert.equal(t.docListeners.mousedown.size, 0);
  assert.equal(t.docListeners.keydown.size, 0);
});

test("Delete lives only inside the closed-by-default settings menu", () => {
  // Catches the old header Delete button coming back, or the menu
  // rendering open.
  const head = SRC.slice(SRC.indexOf('<div class="note-head">'),
                         SRC.indexOf('<div class="note-toolbar"'));
  const menu = head.slice(head.indexOf('id="note-settings-menu"'));
  assert.equal((head.match(/id="btn-note-delete"/g) || []).length, 1);
  assert.ok(menu.includes('id="btn-note-delete"'), "delete must be inside the menu");
  assert.match(head, /id="note-settings-menu" role="menu" hidden>/);
  assert.ok(menu.includes('id="btn-note-settings-close"'));
});
