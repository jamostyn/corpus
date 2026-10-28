// Tests for src/corpus-links.js — the in-corpus connections block.
//
// This module exists because of a real bug: the first version of the
// block omitted a direction when its list was empty, and omitted the
// whole block when both were. On a paper that cites two others but is
// cited by none, the user saw a "Cites" heading and no "Cited by" at
// all — indistinguishable from the reverse direction never having been
// built. Jack reported it as a missing feature. Every empty-state test
// below is pinning that.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const sandbox = loadInVM(["corpus-links.js"]);
const CL = sandbox.window.CorpusLinks;

const titleFor = (slug) => ({
  "collins-2016": "Cognitive Control Over Learning",
  "blanco-2023":  "Exploration in Category Learning",
}[slug] || slug);

// ---------- both directions are ALWAYS present ----------

test("renders both headings when the paper has no links at all", () => {
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true,
                           refCounts: { total: 0, with_doi: 0, linked: 0 } });
  assert.match(html, /Cites \(0\)/);
  assert.match(html, /Cited by \(0\)/);
});

test("returns markup rather than an empty string when there are no links", () => {
  // The original bug: `if (!cites.length && !citedBy.length) return ""`.
  // An absent section reads as a missing feature, not as "no connections".
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true, refCounts: {} });
  assert.notEqual(html.trim(), "");
  assert.match(html, /In-corpus connections/);
});

test("shows Cited by even when only Cites is populated", () => {
  // The exact shape Jack hit: turner-2024 cites 2, cited by 0.
  const html = CL.render({
    cites: ["blanco-2023"], citedBy: [], hasDoi: true,
    refCounts: { total: 29, with_doi: 28, linked: 1 },
  });
  assert.match(html, /Cites \(1\)/);
  assert.match(html, /Cited by \(0\)/);
  assert.match(html, /No papers in this corpus cite it\./);
});

test("shows Cites even when only Cited by is populated", () => {
  const html = CL.render({
    cites: [], citedBy: ["collins-2016"], hasDoi: true,
    refCounts: { total: 40, with_doi: 30, linked: 0 },
  });
  assert.match(html, /Cites \(0\)/);
  assert.match(html, /Cited by \(1\)/);
});

// ---------- empty-state wording ----------

test("empty states scope themselves to THIS corpus", () => {
  // "No papers cite it" would be a claim about the literature. The only
  // thing Corpus knows is what is in the user's own corpus.
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true, refCounts: {} });
  assert.match(html, /No papers in this corpus/);
  assert.doesNotMatch(html, /has never been cited/i);
});

// ---------- link markup ----------

test("each linked paper is a data-open-paper anchor", () => {
  // Catches: losing the delegation attribute app.js listens for, which
  // would render the links as dead text.
  const html = CL.render({ cites: ["collins-2016"], citedBy: [], hasDoi: true,
                           refCounts: { total: 1, with_doi: 1, linked: 1 } });
  assert.match(html, /data-open-paper="collins-2016"/);
});

test("resolved titles are shown with the slug alongside", () => {
  const html = CL.render({ cites: ["collins-2016"], citedBy: [], hasDoi: true,
                           refCounts: {}, titleFor });
  assert.match(html, /Cognitive Control Over Learning/);
  assert.match(html, /collins-2016/);
});

test("falls back to the slug when no title is known", () => {
  // Catches: rendering "undefined" when state.papers hasn't loaded or
  // the paper's title is missing.
  const html = CL.render({ cites: ["mystery-2020"], citedBy: [], hasDoi: true,
                           refCounts: {}, titleFor });
  assert.match(html, /mystery-2020/);
  assert.doesNotMatch(html, /undefined/);
});

test("counts match the number of rendered entries", () => {
  const html = CL.render({ cites: ["a", "b", "c"], citedBy: ["d"], hasDoi: true,
                           refCounts: {} });
  assert.match(html, /Cites \(3\)/);
  assert.match(html, /Cited by \(1\)/);
  assert.equal((html.match(/data-open-paper=/g) || []).length, 4);
});

// ---------- explaining WHY a section is empty ----------

test("a paper with no DOI is told why nothing can cite it", () => {
  // Matching is DOI-only, so a paper without one can never be a link
  // target. Without this line its permanently empty "Cited by" looks
  // like a bug. 2 of 57 papers in Jack's corpus are in this state.
  const html = CL.render({ cites: [], citedBy: [], hasDoi: false, refCounts: {} });
  assert.match(html, /no DOI, so references to it cannot be matched/);
});

test("the no-DOI note is suppressed once something does cite it", () => {
  // Defensive: if cited_by is somehow non-empty the explanation is
  // false and must not appear.
  const html = CL.render({ cites: [], citedBy: ["x-2020"], hasDoi: false,
                           refCounts: {} });
  assert.doesNotMatch(html, /cannot be matched/);
});

test("a paper with a DOI gets no no-DOI note", () => {
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true, refCounts: {} });
  assert.doesNotMatch(html, /cannot be matched/);
});

// ---------- reference-count note ----------

test("no reference list is stated outright", () => {
  // 8 of 57 papers in Jack's corpus have refs_source: none. Silence
  // there looks like a rendering failure.
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true,
                           refCounts: { total: 0, with_doi: 0, linked: 0 } });
  assert.match(html, /No reference list for this paper\./);
});

test("references without a DOI are reported separately from unmatched ones", () => {
  // Catches: collapsing "no DOI" into "not in corpus". They are
  // different problems — one is a metadata gap, the other means the
  // user doesn't own the paper.
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true,
                           refCounts: { total: 67, with_doi: 61, linked: 0 } });
  assert.match(html, /0 of 61 references with a DOI match/);
  assert.match(html, /6 of 67 have no DOI/);
});

test("the no-DOI clause is omitted when every reference has one", () => {
  const html = CL.render({ cites: [], citedBy: [], hasDoi: true,
                           refCounts: { total: 20, with_doi: 20, linked: 3 } });
  assert.match(html, /3 of 20 references with a DOI match/);
  assert.doesNotMatch(html, /have no DOI/);
});

// ---------- defensive input handling ----------

test("missing or malformed inputs still render the block", () => {
  // renderDetail calls this unconditionally now, so a paper served by
  // an older server (no cites/cited_by keys) must not throw and take
  // the whole paper-info pane down with it.
  for (const opts of [undefined, {}, { cites: null, citedBy: undefined }]) {
    const html = CL.render(opts);
    assert.match(html, /In-corpus connections/);
    assert.match(html, /Cites \(0\)/);
  }
});
