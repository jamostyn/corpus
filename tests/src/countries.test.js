// Tests for src/countries.js — ISO country codes → readable names.
//
// Requirement (2026-09-17): show the full country name next to the code.
// Corpus rendered raw OpenAlex
// `country_code` values ("NL", "SG", "AE") in nine places.
//
// This module is self-contained and pure, so unlike most of the
// frontend it gets real behavioural coverage rather than source
// assertions. The names come from `Intl.DisplayNames` — the point of
// these tests is the WRAPPER: the fallbacks, the case handling, and
// the guarantee that a caller can always render the result directly.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const C = loadInVM(["countries.js"]).window.Countries;

// ---------- the reported problem ----------

test("resolves the codes a reader cannot decode on sight", () => {
  // The whole point of the report. "US" is guessable; these are not.
  assert.equal(C.name("NL"), "Netherlands");
  assert.equal(C.name("SG"), "Singapore");
  assert.equal(C.name("AE"), "United Arab Emirates");
  assert.equal(C.name("IL"), "Israel");
});

// ---------- fallbacks: a caller must be able to render the result ----------
//
// Every render site does `escHtml(Countries.name(x))` with no guard of
// its own, so anything that returns undefined/null/"undefined" would
// print that into the UI.

test("an empty or missing code yields an empty string, never 'undefined'", () => {
  // Catches: returning `dn.of(...)` directly. `of("")` THROWS a
  // RangeError, which in a list render would take out the whole row.
  for (const input of ["", "   ", null, undefined]) {
    assert.equal(C.name(input), "", `name(${JSON.stringify(input)})`);
    assert.equal(C.withCode(input), "", `withCode(${JSON.stringify(input)})`);
  }
});

test("a code Intl cannot parse comes back unchanged instead of throwing", () => {
  // Catches: dropping the try/catch. `of("USA")` throws RangeError —
  // alpha-3 is not ISO 3166-1 alpha-2. If a data source ever hands us
  // one, the row must still render.
  assert.equal(C.name("USA"), "USA");
  assert.equal(C.name("X"), "X");
});

test("lower-case codes resolve rather than passing through", () => {
  // Catches: forgetting the .toUpperCase(). `of("nl")` does NOT throw —
  // it returns "nl" unchanged, so the bug would be silent: the UI shows
  // a lowercase code and looks like the feature simply didn't apply.
  assert.equal(C.name("nl"), "Netherlands");
  assert.equal(C.name("gb"), "United Kingdom");
});

test("an unknown-but-well-formed code returns the original string", () => {
  // Catches: returning the upper-cased form on the unresolved path,
  // which silently rewrites the stored value in the UI.
  assert.equal(C.name("qx"), "qx");
});

// ---------- withCode ----------

test("withCode shows the name and keeps the raw code", () => {
  // The institution detail's Country row is explicitly ABOUT the stored
  // field, so the code stays visible there.
  assert.equal(C.withCode("NL"), "Netherlands (NL)");
  assert.equal(C.withCode("nl"), "Netherlands (NL)");
});

test("withCode does not print a code twice when it cannot resolve", () => {
  // Catches: `${name(c)} (${c})` with no equality check, which renders
  // "USA (USA)" for anything unresolvable.
  assert.equal(C.withCode("USA"), "USA");
  assert.equal(C.withCode("qx"), "qx");
});

// ---------- the no-Intl fallback ----------

test("falls back to the raw code when Intl.DisplayNames is missing", () => {
  // Catches: assuming Intl.DisplayNames exists. It is ES2021; if the
  // embedded webview predates it, every country cell must degrade to
  // what it showed before this module existed — not crash the render
  // and not print "undefined".
  const sandbox = loadInVM(["countries.js"], { Intl: {} });
  const Fallback = sandbox.window.Countries;
  assert.equal(Fallback.name("NL"), "NL");
  assert.equal(Fallback.withCode("NL"), "NL");
  assert.equal(Fallback.name(""), "");
});

test("a throwing Intl.DisplayNames constructor is survived", () => {
  // Catches: constructing the formatter outside the try/catch. A
  // runtime with the symbol present but the region type unsupported
  // would otherwise throw at module load and take the whole page down.
  const sandbox = loadInVM(["countries.js"], {
    Intl: { DisplayNames: function () { throw new Error("unsupported"); } },
  });
  assert.equal(sandbox.window.Countries.name("NL"), "NL");
});

test("the formatter is built once, not per call", () => {
  // Catches: moving the `new Intl.DisplayNames(...)` inside `name`.
  // These run inside list renders that fire on every filter keystroke,
  // once per visible row.
  let built = 0;
  const sandbox = loadInVM(["countries.js"], {
    Intl: {
      DisplayNames: function () {
        built++;
        this.of = (c) => (c === "NL" ? "Netherlands" : c);
      },
    },
  });
  const K = sandbox.window.Countries;
  for (let i = 0; i < 25; i++) K.name("NL");
  assert.equal(built, 1, `constructed ${built} times`);
});

test("an empty code never reaches Intl at all", () => {
  // Catches: dropping the `if (!raw) return ""` early return.
  //
  // Removing it is BEHAVIOUR-PRESERVING — `of("")` throws RangeError,
  // the try/catch returns the raw string, and the caller sees "" either
  // way. It survived mutation testing for exactly that reason. What it
  // changes is the mechanism: a blank country_code is common (plenty of
  // OpenAlex institutions have none), and these run once per row inside
  // list renders, so the empty case would be driving a thrown exception
  // per row per keystroke instead of returning immediately.
  //
  // Asserting the observable difference — that Intl is not consulted —
  // is what turns an equivalent mutant into a caught one.
  const calls = [];
  const sandbox = loadInVM(["countries.js"], {
    Intl: {
      DisplayNames: function () {
        this.of = (c) => { calls.push(c); return c; };
      },
    },
  });
  const K = sandbox.window.Countries;
  K.name("");
  K.name(null);
  K.name("   ");
  assert.deepEqual(calls, [], `Intl was consulted for empty input: ${calls}`);
});
