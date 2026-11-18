// Tests for src/shared-citers.js — the note's Shared citers dialog
// (experimental). Requirement (2026-10-30): list works citing two or
// more of a note's papers, in-corpus and not, from any note linking
// more than one paper.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const W = loadInVM(["citers.js", "shared-citers.js"]).window;
const S = W.SharedCiters;

function body(slugs) {
  return { querySelectorAll: () => slugs.map(s => ({ getAttribute: () => s })) };
}

test("a paper linked twice counts once toward enabling the button", () => {
  // Catches counting links rather than papers: one paper linked twice
  // (or once plus a highlight) would enable a search that cannot work.
  assert.equal(S.linkedCount(body(["a", "a"])), 1);
  assert.equal(S.linkedCount(body(["a", "b", "a"])), 2);
});

const papers = [{ slug: "a", status: "stored" }, { slug: "b", status: "stored" }];

test("both groups are listed, each row naming the note papers it cites", () => {
  // Catches dropping the not-in-corpus group, marking outsiders as in
  // the corpus, or losing which note papers a citer connects.
  const h = S.render({
    papers,
    in_corpus: [{ slug: "mine-2021", title: "Mine", year: 2021, doi: "10.1/m", cites: ["a", "b"] }],
    elsewhere: [{ slug: null, title: "Stranger", year: 2020, doi: "", cites: ["a", "b"] }],
    elsewhere_total: 1,
  });
  assert.match(h, /In your corpus <span class="sc-count">1</);
  assert.match(h, /Not in your corpus <span class="sc-count">1</);
  assert.equal((h.match(/data-open-paper=/g) || []).length, 1);
  assert.match(h, /Stranger/);
  assert.match(h, /Cites 2 of your papers: a, b/);
});

test("papers without a citer list are named, with a way to fetch them", () => {
  // Catches an empty result that reads as "nothing shared" when the
  // lists were simply never fetched.
  const h = S.render({ papers: [papers[0], { slug: "c", status: "not_fetched" }],
                       in_corpus: [], elsewhere: [], elsewhere_total: 0 });
  assert.match(h, /No citer list yet: c/);
  assert.match(h, /data-sc-fetch/);
  assert.match(h, /at least 2 papers/);
  assert.doesNotMatch(h, /In your corpus/);
});

test("more shared citers outside the corpus can be paged in", () => {
  // Catches silently truncating the outside list at the first page.
  const h = S.render({ papers, in_corpus: [], elsewhere: [{ title: "X", cites: ["a", "b"] }],
                       elsewhere_total: 250 });
  assert.match(h, /data-sc-more/);
  assert.match(h, /249 left/);
});

test("each work shows its citation count, and nothing when it is unknown", () => {
  // Catches the count being dropped, or an unknown count shown as
  // "0 citations" (which reads as never cited).
  assert.match(S.rowHtml({ title: "T", cites: ["a", "b"], cited_by_count: 1234 }), /1,234 citations/);
  assert.match(S.rowHtml({ title: "T", cites: ["a", "b"], cited_by_count: 1 }), /1 citation\b/);
  assert.doesNotMatch(S.rowHtml({ title: "T", cites: ["a", "b"], cited_by_count: null }), /citation/);
});

test("a failed count lookup is said, not hidden", () => {
  const h = S.render({ papers, in_corpus: [], elsewhere: [], elsewhere_total: 0, counts_failed: 3 });
  assert.match(h, /Citation counts unavailable for 3 works/);
});

