// Country codes → readable country names.
//
// OpenAlex stores ISO 3166-1 alpha-2 codes ("NL", "SG", "AE"). Corpus
// rendered those raw in nine places, which is unreadable for anything
// outside the handful everyone knows — Jack, 2026-09-17: "can you also
// have it show the full name of the country? not sure which one this
// is."
//
// The mapping comes from `Intl.DisplayNames`, which is ICU/CLDR data
// built into the runtime. Deliberately NOT a hand-written table: an
// ISO 3166-1 list is ~250 rows of fact that would sit in this repo
// unverified, drift as countries are renamed (CZ became "Czechia",
// MK became "North Macedonia"), and have to be checked by hand. The
// platform already ships the authoritative list.
//
// Availability: `Intl.DisplayNames` is ES2021 — Safari 14+, so present
// in the WKWebView pywebview uses on macOS, and in the Edge WebView2
// runtime used on Windows. Every path below falls back to the raw code
// if it is missing or throws, so the worst case is exactly the
// behaviour this module replaced.

window.Countries = (function () {
  "use strict";

  // One formatter, built lazily and reused. Constructing an
  // Intl.DisplayNames is not free, and these run inside list renders
  // that fire on every keystroke of a filter box.
  let _dn = null;
  let _dnTried = false;

  function _formatter() {
    if (_dnTried) return _dn;
    _dnTried = true;
    try {
      _dn = new Intl.DisplayNames(["en"], { type: "region" });
    } catch (_) {
      _dn = null;   // ancient runtime; every caller falls back to the code
    }
    return _dn;
  }

  /** Readable country name for an ISO 3166-1 alpha-2 code.
   *
   *  Returns the input unchanged when it cannot be resolved, so a
   *  caller can always render the result directly:
   *    name("NL")   -> "Netherlands"
   *    name("nl")   -> "Netherlands"   (codes are case-insensitive)
   *    name("")     -> ""
   *    name("USA")  -> "USA"           (alpha-3 is not ISO 3166-1 a-2)
   *    name(null)   -> ""
   */
  function name(code) {
    const raw = String(code == null ? "" : code).trim();
    if (!raw) return "";
    const dn = _formatter();
    if (!dn) return raw;
    // Must be upper-cased: `of("us")` returns "us" unchanged rather
    // than throwing, which would silently render lowercase codes as
    // though they were country names.
    const upper = raw.toUpperCase();
    let out;
    try {
      out = dn.of(upper);
    } catch (_) {
      return raw;      // not a well-formed region code (e.g. "USA", "X")
    }
    // `of` echoes the input back for codes it has no name for. Return
    // the ORIGINAL string in that case, not the upper-cased one, so
    // nothing is silently rewritten.
    if (!out || out.toUpperCase() === upper) return raw;
    return out;
  }

  /** Name plus the raw code — "Netherlands (NL)".
   *
   *  For the one place that is explicitly ABOUT the stored field (the
   *  institution detail's Country row). Everywhere else shows the name
   *  alone; repeating the code in a sidebar line adds width without
   *  telling the reader anything they asked for.
   *
   *  Collapses to just the code when it cannot be resolved, so it never
   *  renders "US (US)".
   */
  function withCode(code) {
    const raw = String(code == null ? "" : code).trim();
    if (!raw) return "";
    const n = name(raw);
    return n === raw ? raw : `${n} (${raw.toUpperCase()})`;
  }

  return { name, withCode };
})();
