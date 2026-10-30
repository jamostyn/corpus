// The browser-mode notice (src/window-notice.js).
//
// Requirement (2026-10-30): when Corpus opens in a browser because its
// window could not start, say why, with the fix when one is known.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const WN = () => loadInVM(["window-notice.js"]).window.WindowNotice;

test("no error, no bar", () => {
  // Catches the bar showing on every normal launch.
  assert.equal(WN().html(null), "");
  assert.equal(WN().html({}), "");
});

test("a missing WebView2 gets the install link; other failures do not", () => {
  // Catches the WebView2 advice shown for a different failure (or not
  // shown for the one it fixes), and the error detail being dropped.
  const miss = WN().html({ reason: "webview2_missing", detail: "ModuleNotFoundError: mshtml" });
  assert.match(miss, /WebView2 Runtime/);
  assert.match(miss, /href="https:\/\/developer\.microsoft\.com\/microsoft-edge\/webview2\/"/);
  assert.match(miss, /ModuleNotFoundError: mshtml/);
  const other = WN().html({ reason: "window_failed", detail: "RuntimeError: x" });
  assert.doesNotMatch(other, /WebView2/);
  assert.match(other, /could not start/);
  assert.match(other, /RuntimeError: x/);
});
