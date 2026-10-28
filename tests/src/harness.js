// Frontend test harness. Loads a browser JS file into a Node vm sandbox
// with fakes for the globals it expects at call-time (window, escHtml,
// escAttr, tt, SRC_ABBR, …). Returns the sandbox so tests can pull
// `sandbox.window.Provenance` etc.
//
// Zero deps beyond node's built-in `vm` + `node:test` + `node:assert`.
// Ships in-repo — run with `node --test tests/src/*.test.js` or via
// the Python glue at `tests/test_frontend.py` so `pytest tests/ -q`
// runs the whole suite in one shot.

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC_DIR = path.join(__dirname, "..", "..", "src");

// Corpus's SRC_ABBR (mirrors app.js:61). Kept here so provenance.js
// tests don't have to load app.js (which drags in the whole DOM).
// If app.js's SRC_ABBR ever changes, this must too.
const SRC_ABBR = {
  "crossref":        "C",
  "crossref-search": "C",
  "openalex":        "OA",
  "semanticscholar": "SS",
  "pdf-metadata":    "PDF",
  "slug":            "F",
};

// Identity-shaped fakes for the escape helpers app.js exports. Not
// real HTML-escaping — tests assert against the surrounding markup
// shape, not the escape rules. If a test needs real escaping later,
// import the real ones (a tiny copy — 5 replace rules).
function identity(s) { return String(s == null ? "" : s); }

function defaultGlobals() {
  return {
    window:   {},
    // `window` becomes the sandbox itself (see loadInVM), so window
    // methods live at top level, as in a browser. notes.js registers a
    // `pagehide` flush at load (2026-09-28); without this it would not
    // load at all.
    addEventListener() {},
    document: { addEventListener() {} },
    SRC_ABBR,
    escHtml: identity,
    escAttr: identity,
    tt: (key) => key,
  };
}

// Load one or more files (in order) into a shared sandbox.
//
// Browser semantics: `window` IS the global scope. When a script does
// `window.Foo = {...}`, `Foo` becomes accessible as a bare identifier
// in every subsequently-loaded script. Node's `vm` module does NOT
// wire this up by default — `sandbox.window` is just a property on
// `sandbox`, so a later `Coverage.foo()` reference resolves in
// sandbox scope (undefined) not on `window.Coverage`. Making
// `sandbox.window === sandbox` gives us real browser behavior.
function loadInVM(files, extraGlobals) {
  const sandbox = Object.assign(defaultGlobals(), extraGlobals || {});
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  for (const filename of files) {
    const src = fs.readFileSync(path.join(SRC_DIR, filename), "utf8");
    vm.runInContext(src, sandbox, { filename });
  }
  return sandbox;
}

module.exports = { loadInVM, SRC_ABBR };
