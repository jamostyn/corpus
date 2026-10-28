// Tests for corpus-highlights.js's scroll-to-highlight — the code that
// runs when a highlight link in a note is clicked.
//
// Bug (2026-09-22): highlight links did not scroll to the highlight.
// PDF.js draws a highlight's box
// only when its page renders; the old code looked for the box, found
// none on any page not yet scrolled to, and gave up.
//
// The real functions are cut out of the vendored viewer file by marker
// and run against a fake document, state and PDFViewerApplication.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "vendor",
  "pdfjs", "web", "corpus-highlights.js"), "utf8");
const START = SRC.indexOf("const _PENDING_SCROLL_MS");
const END = SRC.indexOf("function highlightsOverlapping");
const SNIPPET = SRC.slice(START, END);

function setup({ rendered = false, docReady = true, highlights } = {}) {
  let now = 1000;
  const el = {
    dataset: { highlightId: "h1" },
    scrolled: 0,
    classList: { add() {}, remove() {} },
    scrollIntoView() { this.scrolled += 1; },
  };
  const app = { page: 1, pdfDocument: docReady ? {} : null };
  const ctx = {
    state: { highlights: highlights || [{ id: "h1", page: 7 }] },
    document: { querySelector: () => (ctx._rendered ? el : null) },
    CSS: { escape: (s) => s },
    window: { PDFViewerApplication: app },
    Date: { now: () => now },
    setTimeout: () => 0,
    _rendered: rendered,
  };
  vm.createContext(ctx);
  vm.runInContext(SNIPPET, ctx);
  return { ctx, el, app, advance: (ms) => { now += ms; } };
}

test("a highlight on a page not yet rendered jumps to that page", () => {
  // The reported bug: the box does not exist yet, so the old code did
  // nothing and the viewer stayed on page 1.
  const { ctx, app } = setup();
  ctx.scrollToHighlight("h1");
  assert.equal(app.page, 7);
});

test("the scroll finishes when the page renders", () => {
  // Catches jumping to the page top and stopping there — the highlight
  // itself must be centred and flashed once it is drawn.
  const { ctx, el } = setup();
  ctx.scrollToHighlight("h1");
  ctx._rendered = true;
  ctx._tryPendingScroll();            // what the pagerendered hook calls
  assert.equal(el.scrolled, 1);
});

test("the jump happens once, not on every later page render", () => {
  // Catches the viewer yanking back to the highlight's page every time
  // ANY page renders while the user scrolls away.
  const { ctx, app } = setup();
  ctx.scrollToHighlight("h1");
  app.page = 2;                       // user scrolls elsewhere
  ctx._tryPendingScroll();
  ctx._tryPendingScroll();
  assert.equal(app.page, 2);
});

test("a link that arrives before the document loads is kept", () => {
  // Catches dropping the request: the note window posts it the moment
  // the iframe exists, long before the PDF has opened.
  const s = setup({ docReady: false });
  s.ctx.scrollToHighlight("h1");
  assert.equal(s.app.page, 1);
  s.app.pdfDocument = {};             // pagesinit
  s.ctx._tryPendingScroll();
  assert.equal(s.app.page, 7);
});

test("a repeat of a scroll that just completed is ignored", () => {
  // Senders re-post for a few seconds; catches every re-post
  // re-centring the page under someone already reading.
  const { ctx, el } = setup({ rendered: true });
  ctx.scrollToHighlight("h1");
  ctx.scrollToHighlight("h1");
  ctx.scrollToHighlight("h1");
  assert.equal(el.scrolled, 1);
});

test("a stale request expires instead of firing much later", () => {
  // Catches a request that never resolved (highlight erased, page failed
  // to render) jumping the viewer minutes afterwards.
  const s = setup({ docReady: false });
  s.ctx.scrollToHighlight("h1");
  s.advance(11000);
  s.app.pdfDocument = {};
  s.ctx._tryPendingScroll();
  assert.equal(s.app.page, 1);
});

test("an erased highlight does not move the viewer", () => {
  // A link to a highlight that no longer exists must leave the paper
  // where it is rather than jump somewhere arbitrary.
  const { ctx, app } = setup({ highlights: [] });
  ctx.scrollToHighlight("h1");
  assert.equal(app.page, 1);
});
