// Tests for src/provenance.js — the shared badge + coverage helpers
// used by all four detail modules. Run with `node --test`.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const { window } = loadInVM(["provenance.js"]);
const P = window.Provenance;
const C = window.Coverage;

// ---------- Provenance.badgeFromArr ----------

test("badgeFromArr — empty / non-array returns empty string", () => {
  assert.equal(P.badgeFromArr(null),        "");
  assert.equal(P.badgeFromArr(undefined),   "");
  assert.equal(P.badgeFromArr([]),          "");
  assert.equal(P.badgeFromArr("crossref"),  "");
  assert.equal(P.badgeFromArr(42),          "");
});

test("badgeFromArr — dedupes crossref + crossref-search into one C badge", () => {
  const html = P.badgeFromArr(["crossref", "crossref-search"]);
  const cBadges = html.match(/>C</g) || [];
  assert.equal(cBadges.length, 1, "should dedupe C variants");
});

test("badgeFromArr — first source is winner, rest are verifiers", () => {
  const html = P.badgeFromArr(["crossref", "openalex", "semanticscholar"]);
  assert.match(html, /prov-tag win"[^>]*>C</,   "crossref should be winner");
  assert.match(html, /prov-tag ver"[^>]*>OA</,  "openalex should be verifier");
  assert.match(html, /prov-tag ver"[^>]*>SS</,  "semanticscholar should be verifier");
});

test("badgeFromArr — preserves order across dedupe", () => {
  // openalex first → should be winner; the two crossref entries collapse
  // to a single verifier badge appearing AFTER OA.
  const html = P.badgeFromArr(["openalex", "crossref", "crossref-search"]);
  const oaIdx = html.indexOf(">OA<");
  const cIdx  = html.indexOf(">C<");
  assert.ok(oaIdx >= 0 && cIdx >= 0);
  assert.ok(oaIdx < cIdx, "OA winner should render before C verifier");
  assert.match(html, /prov-tag win"[^>]*>OA</);
  assert.match(html, /prov-tag ver"[^>]*>C</);
});

test("badgeFromArr — unknown source string falls back to itself", () => {
  const html = P.badgeFromArr(["future-api"]);
  assert.match(html, />future-api</);
});

// ---------- Provenance.badgeFromField ----------

test("badgeFromField — reads <field>_from off a frontmatter dict", () => {
  const fm = { title_from: ["crossref", "openalex"] };
  const html = P.badgeFromField(fm, "title");
  assert.match(html, />C</);
  assert.match(html, />OA</);
});

test("badgeFromField — safe on null fm or missing field", () => {
  assert.equal(P.badgeFromField(null, "title"),      "");
  assert.equal(P.badgeFromField(undefined, "title"), "");
  assert.equal(P.badgeFromField({}, "title"),        "");
});

// ---------- Coverage.inSource ----------

test("inSource — crossref-search counts as C (matches paper-detail's pre-existing behavior)", () => {
  assert.equal(C.inSource(["crossref-search"], "C"),  true);
  assert.equal(C.inSource(["crossref-search"], "SS"), false);
  assert.equal(C.inSource(["crossref-search"], "OA"), false);
});

test("inSource — plain source names route to the right column", () => {
  assert.equal(C.inSource(["crossref"],        "C"),  true);
  assert.equal(C.inSource(["semanticscholar"], "SS"), true);
  assert.equal(C.inSource(["openalex"],        "OA"), true);
});

test("inSource — false on empty / non-array / unknown column", () => {
  assert.equal(C.inSource(null,          "C"),  false);
  assert.equal(C.inSource([],            "C"),  false);
  assert.equal(C.inSource("crossref",    "C"),  false);
  assert.equal(C.inSource(["crossref"], "ZZ"),  false);
});

// ---------- Coverage.cell ----------

test("cell — 4-state matrix", () => {
  assert.match(C.cell(null),       /cov-na/);
  assert.match(C.cell(undefined),  /cov-na/);
  assert.match(C.cell("skip"),     /cov-skip/);
  assert.match(C.cell("SKIP"),     /cov-skip/);
  assert.match(C.cell(true),       /cov-yes/);
  assert.match(C.cell(false),      /cov-no/);
  assert.match(C.cell(0),          /cov-no/);
  assert.match(C.cell("anything"), /cov-no/);
});

// ---------- Coverage.renderTable ----------

test("renderTable — mixes all 4 cell states into one table + legend", () => {
  const html = C.renderTable([
    ["Title", true,    "skip", null,    "meta.title"],
    ["DOI",   true,    true,   true,    "meta.doi"],
    ["Pages", false,   null,   "SKIP",  "meta.pages"],
  ]);
  assert.match(html, /cov-table/);
  assert.match(html, /Title/);
  assert.match(html, /DOI/);
  assert.match(html, /Pages/);
  assert.match(html, /cov-yes/);
  assert.match(html, /cov-no/);
  assert.match(html, /cov-skip/);
  assert.match(html, /cov-na/);
  assert.match(html, /cov-legend/);
  assert.match(html, /Crossref/);
  assert.match(html, /Semantic Scholar/);
  assert.match(html, /OpenAlex/);
});

test("renderTable — empty rows array still renders header + legend", () => {
  const html = C.renderTable([]);
  assert.match(html, /cov-table/);
  assert.match(html, /Crossref/);
  assert.match(html, /cov-legend/);
});
