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

// Linking a paper inserts its slug, while the picker row still shows the
// title (2026-11-12): the title is how a paper is found, the slug is
// what a note should carry.
const PAPER = {
  linkId: (r) => r.slug,
  linkLabel: (r) => `${r.title} (${r.year})`,
  linkText: (r) => r.slug,
};
const ROW = { slug: "pan-2025-1", title: "Individual differences in fluid intelligence", year: "2025" };

test("a paper link says the slug, its picker row the title", () => {
  // Catches the inserted text falling back to the row label (the old
  // behaviour), or the row label turning into the slug too.
  const [x] = sandbox._pickerItems(PAPER, [ROW]);
  assert.equal(x.id, "pan-2025-1");
  assert.equal(x.text, "pan-2025-1");
  assert.equal(x.label, "Individual differences in fluid intelligence (2025)");
});

test("a type without linkText inserts its label", () => {
  // Catches authors / journals inserting an empty or undefined link.
  const author = { linkId: (r) => r.key, linkLabel: (r) => r.name };
  const [x] = sandbox._pickerItems(author, [{ key: "a1", name: "Unsworth, Nash" }]);
  assert.equal(x.text, "Unsworth, Nash");
});

// A highlight link says the slug and the highlight's page, not the
// quote (2026-11-12).
test("a highlight link says slug and page", () => {
  // Catches the label going back to the quote, or dropping the page.
  assert.equal(sandbox._highlightLinkLabel("pan-2025-1", 4), "pan-2025-1, p. 4");
});

test("a highlight with no page says the slug alone", () => {
  // Catches "p. undefined" / "p. 0" when the viewer sends no page.
  assert.equal(sandbox._highlightLinkLabel("pan-2025-1", undefined), "pan-2025-1");
  assert.equal(sandbox._highlightLinkLabel("pan-2025-1", 0), "pan-2025-1");
});
