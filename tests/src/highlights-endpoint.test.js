// Which endpoint the PDF viewer saves highlights to.
//
// Documents (2026-09-25) are read in the same viewer as papers. The only
// thing that differs is where their highlights and anchored notes live,
// and the viewer works that out from the PDF's URL. Getting it wrong is
// silent: a document's highlights would save under a paper's slug, or
// not at all. The real function is cut out of the vendored file.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "vendor",
  "pdfjs", "web", "corpus-highlights.js"), "utf8");
const start = SRC.indexOf("function highlightsApiFor(");
const body = SRC.slice(start, SRC.indexOf("\n  }\n", start) + 4);
const ctx = {};
vm.createContext(ctx);
vm.runInContext(body, ctx);
const apiFor = (u) => vm.runInContext(`highlightsApiFor(${JSON.stringify(u)})`, ctx);

test("a paper's PDF saves to the paper endpoint", () => {
  // Catches the document branch shadowing the paper one.
  assert.equal(apiFor("/pdf/smith-2020"), "/api/paper/smith-2020/highlights");
});

test("a document's PDF saves to the document endpoint", () => {
  // Catches documents getting no persistence (the old /pdf/-only match)
  // or being saved under a paper slug.
  assert.equal(apiFor("/document/chapter-3-memory/pdf"),
               "/api/document/chapter-3-memory/highlights");
});

test("anything else saves nowhere", () => {
  // Catches a loose match: a paper slug that merely CONTAINS "/pdf/", or
  // an arbitrary URL, must not start writing highlights somewhere.
  assert.equal(apiFor("/vendor/test.pdf"), null);
  assert.equal(apiFor("https://example.com/pdf/x"), null);
  assert.equal(apiFor(""), null);
});
