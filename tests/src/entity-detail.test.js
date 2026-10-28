// Tests for src/entity-detail.js — the shared render skeleton for
// author / institution / journal detail panes.
//
// EntityDetail.render depends on `Coverage.renderTable` from
// provenance.js and on `escHtml`, `escAttr`, `_relativeTime` from
// app.js at call-time. The harness stubs those; provenance.js is
// loaded as a real dep so `Coverage.renderTable` is genuine.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const sandbox = loadInVM(["provenance.js", "entity-detail.js"], {
  // _relativeTime is on app.js; stub for tests.
  _relativeTime: (iso) => (iso ? "recent" : "unknown"),
});
const ED = sandbox.window.EntityDetail;

// ---------- basic skeleton ----------

test("render — header h1 + subtitle appear when provided", () => {
  const html = ED.render({
    h1: "Kahneman, Daniel",
    subtitle: "Princeton University · US",
    metaRows: [],
    coverage: [],
  });
  assert.match(html, /<h1>Kahneman, Daniel<\/h1>/);
  assert.match(html, /class="pd-authors">Princeton University · US</);
});

test("render — subtitle omitted when empty", () => {
  const html = ED.render({
    h1: "Just A Name",
    metaRows: [],
    coverage: [],
  });
  assert.match(html, /<h1>Just A Name<\/h1>/);
  assert.doesNotMatch(html, /pd-authors/);
});

test("render — metaRows render as dt/dd pairs", () => {
  const html = ED.render({
    h1: "X",
    metaRows: [
      ["Papers in corpus", "5"],
      ["ORCID",            "<a>0000-0001</a>"],
    ],
    coverage: [],
  });
  assert.match(html, /<dt>Papers in corpus<\/dt><dd>5<\/dd>/);
  assert.match(html, /<dt>ORCID<\/dt><dd><a>0000-0001<\/a><\/dd>/);
});

// ---------- refresh bar ----------

test("refresh — bar omitted when descriptor.refresh is null", () => {
  const html = ED.render({ h1: "X", metaRows: [], coverage: [] });
  assert.doesNotMatch(html, /pd-refresh/);
});

test("refresh — bar rendered when descriptor.refresh present", () => {
  const html = ED.render({
    h1: "X",
    metaRows: [],
    refresh: { entity: "author", key: "kahneman-daniel", fetchedAt: "2026-08-16T12:00:00Z" },
    coverage: [],
  });
  assert.match(html, /pd-refresh/);
  assert.match(html, /data-refresh-entity="author"/);
  assert.match(html, /data-refresh-key="kahneman-daniel"/);
  assert.match(html, /OpenAlex enrichment fetched recent/);   // via stubbed _relativeTime
});

test("refresh — 'no cache yet' state when fetchedAt is empty", () => {
  const html = ED.render({
    h1: "X",
    metaRows: [],
    refresh: { entity: "institution", key: "ror-abc", fetchedAt: "" },
    coverage: [],
  });
  assert.match(html, /no OpenAlex enrichment cached yet/);
});

// ---------- side blocks ----------

test("sideBlocks — rendered in order, empties filtered", () => {
  const html = ED.render({
    h1: "X",
    metaRows: [],
    sideBlocks: [
      `<div class="a">block A</div>`,
      "",                              // empty — should be filtered
      `<div class="b">block B</div>`,
      null,                            // null — should be filtered
      `<div class="c">block C</div>`,
    ],
    coverage: [],
  });
  const aIdx = html.indexOf("block A");
  const bIdx = html.indexOf("block B");
  const cIdx = html.indexOf("block C");
  assert.ok(aIdx > 0 && bIdx > aIdx && cIdx > bIdx, "blocks must render in given order");
});

// ---------- coverage ----------

test("coverage — always renders a Coverage.renderTable call, empty array ok", () => {
  const html = ED.render({ h1: "X", metaRows: [], coverage: [] });
  assert.match(html, /cov-table/);       // Coverage.renderTable output present
  assert.match(html, /Crossref/);        // column header rendered
});
