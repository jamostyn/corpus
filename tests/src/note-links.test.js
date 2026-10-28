// A note's highlight link must name what the highlight belongs to.
//
// Documents (2026-09-25) can be opened in a popped-out note's panel and
// their highlights linked from the note. The link used to be hard-wired
// to `data-open-paper`, which for a document would open a paper slug
// that does not exist.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const sandbox = loadInVM(["notes.js"]);

test("a document highlight links to the document", () => {
  // Catches the kind being ignored: a document highlight emitted as
  // data-open-paper opens nothing when clicked.
  const html = sandbox._highlightLinkHtml("document", "chapter-3", "h1", "a quote");
  assert.match(html, /data-open-document="chapter-3"/);
  assert.match(html, /data-open-highlight="h1"/);
  assert.doesNotMatch(html, /data-open-paper/);
});

test("a paper highlight still links to the paper", () => {
  // Catches the new branch swallowing the old case.
  const html = sandbox._highlightLinkHtml("paper", "pan-2025-1", "h9", "q");
  assert.match(html, /data-open-paper="pan-2025-1"/);
  assert.doesNotMatch(html, /data-open-document/);
});
