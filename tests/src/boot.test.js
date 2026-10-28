// Boot smoke test: load every frontend script in index.html's order into
// one sandbox with a permissive stub DOM, run boot(), and assert it gets
// as far as loading the papers.
//
// Jack, 2026-09-21: "when i clicked pop out on a note it is completely
// blank." The server log showed both windows fetching /api/config and
// /api/tooltips after a restart and then nothing — not even the main
// window requested /api/papers. Startup was throwing, and no test loaded
// the scripts together, so nothing caught it.
//
// This is deliberately crude: the stub DOM answers every lookup with an
// inert element, so the test is about "does boot RUN" — ordering,
// undefined globals, a throw at top level — not about what renders.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = path.join(__dirname, "..", "..", "src");

function scriptOrder() {
  const html = fs.readFileSync(path.join(SRC, "index.html"), "utf8");
  return [...html.matchAll(/<script src="([^"]+)"/g)].map(m => m[1]);
}

// An element that tolerates anything boot might do to it.
function stubEl() {
  const el = {
    hidden: false, disabled: false, textContent: "", innerHTML: "", value: "",
    title: "", placeholder: "", checked: false, className: "", id: "",
    style: { setProperty() {}, removeProperty() {}, getPropertyValue() { return ""; },
             getPropertyPriority() { return ""; } },
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {}, appendChild(c) { return c; },
    insertBefore(c) { return c; }, remove() {}, focus() {}, blur() {}, click() {},
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    hasAttribute() { return false; }, closest() { return null; },
    querySelector() { return stubEl(); }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 0, height: 0 }; },
    scrollIntoView() {}, contentWindow: null, options: [], files: [],
  };
  return el;
}

function run(hash) {
  const requests = [];
  const errors = [];
  const doc = {
    getElementById: () => stubEl(),
    querySelector: () => stubEl(),
    querySelectorAll: () => [],
    createElement: () => stubEl(),
    addEventListener() {}, removeEventListener() {},
    execCommand() {},
    body: stubEl(), head: stubEl(), documentElement: stubEl(),
  };
  const responses = {
    "/api/config": { corpus_dir: "/tmp/corpus", dev_mode: true, keys: {}, mailto: "" },
    "/api/tooltips": {},
    "/api/papers": [],
    "/api/notes": [],
    "/api/projects": [],
  };
  const fetch = async (url) => {
    const u = String(url);
    requests.push(u);
    const key = Object.keys(responses).find(k => u === k || u.startsWith(k + "?"));
    const body = key ? responses[key] : {};
    return { ok: true, status: 200,
             headers: { get: (h) => (/content-type/i.test(h) ? "application/json" : null) },
             json: async () => body, text: async () => JSON.stringify(body) };
  };
  const sandbox = {
    console: { log() {}, warn() {}, error: (...a) => errors.push(a.join(" ")) },
    document: doc,
    location: { hash: hash || "", origin: "http://x", pathname: "/", search: "" },
    history: { replaceState() {}, pushState() {} },
    navigator: { platform: "MacIntel", userAgent: "node", clipboard: {} },
    localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    fetch, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
    requestAnimationFrame: (f) => setTimeout(f, 0),
    addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
    CustomEvent: class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } },
    Intl, URLSearchParams, Map, Set, Promise, JSON, Math, Date, Array, Object,
    RegExp, String, Number, Boolean, Error,
    CSS: { escape: (s) => s },
    getComputedStyle: () => ({ getPropertyValue() { return ""; } }),
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  for (const f of scriptOrder()) {
    vm.runInContext(fs.readFileSync(path.join(SRC, f), "utf8"), sandbox, { filename: f });
  }
  return { sandbox, requests, errors };
}

test("boot reaches the papers list in the main window", async () => {
  const { sandbox, requests } = run("");
  await sandbox.boot();
  assert.ok(requests.includes("/api/papers"),
            `boot never requested /api/papers; requests were ${JSON.stringify(requests)}`);
});

test("boot reaches the note in a popped-out note window", async () => {
  // The reported symptom: a blank pop-out.
  const { sandbox, requests } = run("#detached=note%3An1&noteMode=0");
  await sandbox.boot();
  assert.ok(requests.includes("/api/papers"), JSON.stringify(requests));
  assert.ok(requests.some(u => u.startsWith("/api/note/n1")), JSON.stringify(requests));
});
