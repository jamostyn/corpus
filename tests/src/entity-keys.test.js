// Tests for src/entity-keys.js — must produce byte-identical output to
// the Python `_author_key` / `_journal_key` in server.py, otherwise
// deep-link anchors on paper-detail land on 404s.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const { window } = loadInVM(["entity-keys.js"]);
const K = window.EntityKeys;

// ---------- author ----------

test("author — plain ASCII first-name given", () => {
  assert.equal(K.author("Kahneman", "Daniel"), "kahneman-daniel");
  assert.equal(K.author("Tulving",  "Endel"),  "tulving-endel");
});

test("author — single-initial given", () => {
  assert.equal(K.author("Smith", "J."),  "smith-j");
  assert.equal(K.author("Smith", "J"),   "smith-j");
});

test("author — no given → family alone (no trailing hyphen)", () => {
  assert.equal(K.author("Cher", ""),        "cher");
  assert.equal(K.author("Cher", null),      "cher");
  assert.equal(K.author("Cher", undefined), "cher");
});

test("author — first whitespace-token of given only ('John R. Anderson')", () => {
  // Python: `given.split()[0]` → "John" (not "John R.")
  assert.equal(K.author("Anderson", "John R."), "anderson-john");
  assert.equal(K.author("Kahneman", "D. R."),   "kahneman-d");
});

test("author — accented characters strip cleanly (NFKD → ASCII)", () => {
  assert.equal(K.author("Müller", "Hans"),  "muller-hans");
  assert.equal(K.author("Peña",   "María"), "pena-maria");
  assert.equal(K.author("Curie",  "Marie"), "curie-marie");
});

test("author — non-alphanumerics collapse to single hyphen", () => {
  assert.equal(K.author("O'Brien",  "Sean"),   "o-brien-sean");
  assert.equal(K.author("van der Berg", "A."), "van-der-berg-a");
  assert.equal(K.author("Smith-Jones", "K."),  "smith-jones-k");
});

test("author — empty family degenerates to empty (guardrail)", () => {
  assert.equal(K.author("", "Daniel"), "-daniel");
  assert.equal(K.author("", ""),       "");
});

// ---------- institution ----------

test("institution — full ROR URL → ror-<id> key", () => {
  assert.equal(K.institution("MIT", "https://ror.org/042nb2s44"), "ror-042nb2s44");
});

test("institution — bare ROR id → ror-<id> key", () => {
  assert.equal(K.institution("Any", "01tgyzw49"), "ror-01tgyzw49");
});

test("institution — no ROR → name slug", () => {
  assert.equal(K.institution("Massachusetts Institute of Technology", ""),
                             "massachusetts-institute-of-technology");
  assert.equal(K.institution("Princeton University", null),
                             "princeton-university");
});

test("institution — no ROR + accents strip cleanly", () => {
  assert.equal(K.institution("Université de Montréal", ""), "universite-de-montreal");
});

test("institution — no ROR + empty name → 'unknown'", () => {
  assert.equal(K.institution("", ""),   "unknown");
  assert.equal(K.institution(null, ""), "unknown");
});

// ---------- journal ----------

test("journal — ISSN wins over name", () => {
  assert.equal(K.journal("Cognition", ["0010-0277"]),           "issn-0010-0277");
  assert.equal(K.journal("Nature",    ["0028-0836", "1476-4687"]), "issn-0028-0836");
});

test("journal — ISSN upper-cases 'X' check digit + strips whitespace", () => {
  assert.equal(K.journal("Any", [" 1234-567x "]), "issn-1234-567X");
});

test("journal — no ISSN → name slug", () => {
  assert.equal(K.journal("PLOS ONE",                 []), "plos-one");
  assert.equal(K.journal("Journal of Neuroscience",  []), "journal-of-neuroscience");
  assert.equal(K.journal("Cognition",                null), "cognition");
});

test("journal — no ISSN + accents strip cleanly", () => {
  assert.equal(K.journal("Zeitschrift für Psychologie", []), "zeitschrift-fur-psychologie");
});

test("journal — no ISSN + empty name → 'unknown'", () => {
  assert.equal(K.journal("", []),    "unknown");
  assert.equal(K.journal(null, []),  "unknown");
});

test("journal — bare-string ISSN treated as [issn] (YAML `issn: 0028-0836`)", () => {
  // Regression: backend coerces bare-string ISSN to list; frontend
  // must too, otherwise deep-link 404s on any paper whose YAML uses
  // the bare form.
  assert.equal(K.journal("Nature", "0028-0836"),   "issn-0028-0836");
  assert.equal(K.journal("Cognition", "0010-0277"), "issn-0010-0277");
});

test("journal — quoted ISSN strings unwrap (defense against YAML quirks)", () => {
  assert.equal(K.journal("Nature", ['"0028-0836"']), "issn-0028-0836");
  assert.equal(K.journal("Nature", ["'0028-0836'"]), "issn-0028-0836");
});
