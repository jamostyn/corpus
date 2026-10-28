// Tests for corpus-highlights.js's "viewer did not start" readout.
//
// Jack, 2026-09-29, Windows build: "the windows pdf viewer is completely
// black. it shows the controls but no PDF". When pdf.js's modules fail to
// run there is no visible error at all; the readout reports the type each
// module was served with.
//
// The readout functions are cut out of the vendored viewer file by marker
// and run against a fake fetch.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "vendor",
  "pdfjs", "web", "corpus-highlights.js"), "utf8");
const START = SRC.indexOf("const _VIEWER_MODULES");
const END = SRC.indexOf("// ---- end viewer-failure readout");
const SNIPPET = SRC.slice(START, END);

function load() {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(SNIPPET + "\nthis._viewerModuleTypes = _viewerModuleTypes;", ctx);
  return ctx;
}

function fakeFetch(table) {
  return async (url) => {
    const v = table[url];
    if (v instanceof Error) throw v;
    return { ok: v.status === 200, status: v.status,
             headers: { get: () => v.type || null } };
  };
}

test("the readout names each module with the type it was served as", async () => {
  // Catches a readout that says only "failed" — the served type is the
  // one fact that separates the Windows MIME cause from everything else.
  const lines = await load()._viewerModuleTypes(fakeFetch({
    "../build/pdf.mjs": { status: 200, type: "text/plain; charset=utf-8" },
    "viewer.mjs": { status: 200, type: "text/plain; charset=utf-8" },
  }));
  assert.deepEqual([...lines], ["pdf.mjs: text/plain; charset=utf-8",
                                "viewer.mjs: text/plain; charset=utf-8"]);
});

test("a missing or unreachable module is reported, not thrown", async () => {
  // Catches one failed HEAD aborting the readout, which would leave the
  // box saying nothing useful.
  const lines = await load()._viewerModuleTypes(fakeFetch({
    "../build/pdf.mjs": { status: 404 },
    "viewer.mjs": new Error("offline"),
  }));
  assert.deepEqual([...lines], ["pdf.mjs: HTTP 404", "viewer.mjs: not reachable"]);
});

test("init stops at the readout when pdf.js never ran", () => {
  // Catches the check moving below `await loadHighlights()` or being
  // dropped: init would go on to wire listeners onto an app that does
  // not exist and the pane would stay silently black.
  const init = SRC.slice(SRC.indexOf("async function init()"));
  const guard = init.indexOf('typeof window.PDFViewerApplication === "undefined"');
  const firstAwait = init.indexOf("await loadHighlights()");
  assert.ok(guard > 0 && guard < firstAwait, "guard must come first in init()");
  assert.match(init.slice(guard, firstAwait), /reportViewerLoadFailure\(\);\s*return;/);
});
