// Tests for src/citers.js — the Citers section of the paper info panel.
//
// Requirement (2026-09-22): clear distinction, as for references, of
// which citers are in the corpus. The distinction uses the References
// list's own `ref-incorpus` marker, and these hold it to that.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const C = loadInVM(["citers.js"]).window.Citers;

test("a never-fetched paper offers the fetch, not an empty list", () => {
  // Catches rendering "0 citers" before anyone has looked.
  const h = C.render({ status: "not_fetched", citation_count: 12 }, { hasDoi: true });
  assert.match(h, /data-citers-fetch/);
  assert.doesNotMatch(h, /In your corpus/);
});

test("a big paper warns how many requests the fetch will take", () => {
  // Catches a silent multi-minute fetch: PRISMA is ~530 requests.
  const h = C.render({ status: "not_fetched", citation_count: 105710 }, { hasDoi: true });
  assert.match(h, /OpenAlex requests/);
});

test("a paper with no DOI is told why it cannot be fetched", () => {
  const h = C.render({ status: "not_fetched" }, { hasDoi: false });
  assert.doesNotMatch(h, /data-citers-fetch/);
  assert.match(h, /DOI/);
});

test("in-corpus citers carry the same marker references use", () => {
  // The in-corpus distinction. Catches in-corpus citers rendered
  // like any other, and outsiders mis-marked as in the corpus.
  const h = C.render({
    status: "ok", stored_count: 2, complete: true, fetched_at: "2026-09-22T10:00:00",
    in_corpus: [{ slug: "mine-2023", doi: "10.1/mine", year: 2023, title: "Mine" }],
    elsewhere: [{ doi: "10.9/x", year: 2021, title: "Stranger" }],
    elsewhere_total: 1,
  }, { hasDoi: true });
  const inside = h.slice(h.indexOf("In your corpus"), h.indexOf("Not in your corpus"));
  const outside = h.slice(h.indexOf("Not in your corpus"));
  assert.match(inside, /class="ref-incorpus" data-open-paper="mine-2023"/);
  assert.doesNotMatch(outside, /ref-incorpus/);
  assert.ok(h.indexOf("In your corpus") < h.indexOf("Not in your corpus"),
            "in-corpus citers come first");
});

test("a partial fetch says it is partial", () => {
  // Catches a truncated list presented as complete.
  const h = C.render({ status: "ok", stored_count: 400, reported_count: 1000,
                       complete: false, in_corpus: [], elsewhere: [], elsewhere_total: 400 },
                     { hasDoi: true });
  assert.match(h, /partial/);
});

test("more citers than shown offers Show more", () => {
  const h = C.render({ status: "ok", stored_count: 120, complete: true,
                       in_corpus: [], elsewhere: new Array(50).fill({ title: "x" }),
                       elsewhere_total: 120 }, { hasDoi: true });
  assert.match(h, /data-citers-more/);
  assert.match(h, /70 left/);
});
