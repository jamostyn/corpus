// Tests for keeping your place when a note pops out
// (notes.js::noteScrollAnchor / restoreNoteScrollAnchor, and the URL
// hand-off in app.js::openDetached / _readDetachedHash).
//
// Jack, 2026-09-29: "when i pop out a note i lose my place where i was
// scrolling." The pop-out is a new window, a different width, that loaded
// the note at the top.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const NOTES = fs.readFileSync(path.join(__dirname, "..", "..", "src", "notes.js"), "utf8");
const APP = fs.readFileSync(path.join(__dirname, "..", "..", "src", "app.js"), "utf8");
const SNIPPET = NOTES.slice(NOTES.indexOf("function _noteScrollParent"),
                            NOTES.indexOf("// ---- end keep-your-place"));

// A fake layout: a scroller of `viewH` px whose content is `heights`
// stacked blocks. Rects are derived from scrollTop like a browser does.
function layout(heights, { viewH = 400, scrollTop = 0, bodyScrolls = true } = {}) {
  const scroller = {
    scrollTop, clientHeight: viewH, style: { overflowY: "auto" },
    get scrollHeight() { return heights.reduce((a, b) => a + b, 0); },
    getBoundingClientRect() { return { top: 100 }; },
  };
  const kids = [];
  let y = 0;
  for (const h of heights) {
    const start = y;
    kids.push({ getBoundingClientRect: () => {
      const top = 100 + start - scroller.scrollTop;
      return { top, bottom: top + h, height: h };
    } });
    y += h;
  }
  let body;
  if (bodyScrolls) {
    body = Object.assign(scroller, { children: kids, parentElement: null });
  } else {
    // The pop-out case: the body grows and its parent column scrolls.
    body = { children: kids, parentElement: scroller, style: { overflowY: "visible" },
             scrollHeight: 0, clientHeight: 0 };
    scroller.parentElement = null;
  }
  const ctx = {
    document: { documentElement: {}, scrollingElement: scroller },
    getComputedStyle: (n) => n.style,
  };
  vm.createContext(ctx);
  vm.runInContext(SNIPPET, ctx);
  return { ctx, body, scroller };
}

test("the anchor is the first visible block and how far into it", () => {
  // Catches picking the first block of the note (always "top") or the
  // last one: scrolled 250px into 100px blocks = block 2, halfway.
  const { ctx, body } = layout([100, 100, 100, 100, 100, 100], { scrollTop: 250 });
  const a = ctx.noteScrollAnchor(body);
  assert.equal(a.i, 2);
  assert.equal(a.f, 0.5);
});

test("an unscrolled note records nothing", () => {
  // Catches every pop-out forcing a scroll even when the user was at the top.
  const { ctx, body } = layout([100, 100, 100]);
  assert.equal(ctx.noteScrollAnchor(body), null);
});

test("the place survives a different width in a different scroller", () => {
  // Catches restoring a raw pixel offset: the pop-out is narrower, blocks
  // are taller, and its column (not the body) scrolls. Block 2, halfway,
  // must land at 2*180 + 90 = 450px.
  const docked = layout([100, 100, 100, 100, 100, 100], { scrollTop: 250 });
  const a = docked.ctx.noteScrollAnchor(docked.body);
  const pop = layout([180, 180, 180, 180, 180, 180], { bodyScrolls: false });
  pop.ctx.restoreNoteScrollAnchor(pop.body, a);
  assert.equal(pop.scroller.scrollTop, 450);
});

test("an anchor past the end of a shorter note is ignored", () => {
  // Catches a throw (and a blank pop-out) when the note shrank between
  // windows.
  const { ctx, body, scroller } = layout([100, 100]);
  ctx.restoreNoteScrollAnchor(body, { i: 9, f: 0.2 });
  assert.equal(scroller.scrollTop, 0);
});

test("the pop-out URL carries the place and the window reads it back", () => {
  // Catches the anchor being computed but never sent, or sent under one
  // name and read under another.
  const open = APP.slice(APP.indexOf("async function openDetached("));
  assert.match(open.slice(0, open.indexOf("_hasPywebviewBridge")),
               /noteScrollAnchor\(document\.getElementById\("note-body"\)\)[\s\S]*&at=\$\{place\.i\}&atf=\$\{place\.f\}/);
  const read = APP.slice(APP.indexOf("function _readDetachedHash"));
  const fn = read.slice(0, read.indexOf("\n}\n") + 3);
  const ctx = { location: { hash: "#detached=note%3A17-ab&noteMode=0&at=12&atf=0.35" },
                URLSearchParams, DETACH_KINDS: ["paper", "note", "document"] };
  vm.createContext(ctx);
  vm.runInContext(fn + "\nthis.r = _readDetachedHash();", ctx);
  assert.deepEqual({ ...ctx.r.place }, { i: 12, f: 0.35 });
  const detachedNote = APP.slice(APP.indexOf("async function openDetachedNote"));
  assert.match(detachedNote.slice(0, detachedNote.indexOf("\n}\n")),
               /restoreNoteScrollAnchor\(document\.getElementById\("note-body"\), place\)/);
});
