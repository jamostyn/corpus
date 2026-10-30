// Appearance setting in the window (app.js::applyTheme) and in the PDF
// viewer (corpus-highlights.js, "Appearance" block).
//
// Requirement (2026-10-28): dark mode can be pinned or follow the system,
// and the PDF viewer's toolbar follows the same choice.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = path.join(__dirname, "..", "..", "src");
const APP = fs.readFileSync(path.join(SRC, "app.js"), "utf8");
const VIEWER = fs.readFileSync(path.join(SRC, "vendor", "pdfjs", "web", "corpus-highlights.js"), "utf8");

function rootEl() {
  const cls = new Set();
  return { dataset: {}, classList: {
    add: c => cls.add(c), remove: (...cs) => cs.forEach(c => cls.delete(c)),
    has: c => cls.has(c) } };
}

function loadApplyTheme() {
  const start = APP.indexOf("function applyTheme");
  const end = APP.indexOf("\n}\n", start) + 3;
  const root = rootEl();
  const sb = { document: { documentElement: root } };
  vm.createContext(sb);
  vm.runInContext(APP.slice(start, end), sb);
  return { applyTheme: sb.applyTheme, root };
}

test("pinned themes set data-theme; system clears it", () => {
  // Catches "system" leaving the last pinned theme in place — the window
  // would stay dark after switching to Match system on a light Mac.
  const { applyTheme, root } = loadApplyTheme();
  applyTheme("dark");
  assert.equal(root.dataset.theme, "dark");
  applyTheme("system");
  assert.ok(!("theme" in root.dataset));
  applyTheme("light");
  assert.equal(root.dataset.theme, "light");
  applyTheme(undefined);
  assert.ok(!("theme" in root.dataset), "no stored theme means follow the system");
});

function loadViewerTheme(parentRoot) {
  const start = VIEWER.indexOf("// ---- Appearance");
  const end = VIEWER.indexOf("// ---- end appearance");
  const snippet = VIEWER.slice(start, VIEWER.indexOf("})();", end) + 5);
  const own = rootEl();
  let observed = null;
  const sb = {
    document: { documentElement: own },
    MutationObserver: class { constructor(cb) { this.cb = cb; } observe() { observed = this.cb; } },
  };
  sb.window = sb;
  sb.window.parent = parentRoot ? { document: { documentElement: parentRoot } } : sb;
  vm.createContext(sb);
  vm.runInContext(snippet, sb);
  return { own, fire: () => observed && observed(), sb };
}

test("the viewer takes the window's pinned theme, and follows changes", () => {
  // Catches the PDF toolbar staying light in a dark window (or the
  // reverse) because pdf.js only knows the system setting.
  const parent = rootEl();
  parent.dataset.theme = "dark";
  const { own, fire } = loadViewerTheme(parent);
  assert.ok(own.classList.has("is-dark"));
  parent.dataset.theme = "light";
  fire();
  assert.ok(own.classList.has("is-light") && !own.classList.has("is-dark"));
  delete parent.dataset.theme;
  fire();
  assert.ok(!own.classList.has("is-light") && !own.classList.has("is-dark"),
            "Match system leaves pdf.js on its own system rule");
});

test("a viewer opened on its own leaves pdf.js alone", () => {
  // Catches a crash or a forced theme when there is no Corpus window
  // around the viewer (window.parent === window).
  const { own, sb } = loadViewerTheme(null);
  assert.ok(!own.classList.has("is-dark") && !own.classList.has("is-light"));
  assert.equal(sb.corpusViewerThemeClass("dark"), "is-dark");
  assert.equal(sb.corpusViewerThemeClass("system"), null);
});
