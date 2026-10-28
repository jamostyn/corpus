// Corpus — sorting a list by one of its tab's declared sort options.
//
// Requirement (2026-09-28): the note link picker can sort by any of the
// tab's options, for example most recently added papers first.
//
// Each tab declares its options once, as `sorts` on its MODES entry in
// app.js: [{ key, label, value: (row) => …, numeric?, defaultDir? }].
// The Papers sidebar and the note link picker both sort through here, so
// "Date added" means the same thing in both and a new option appears in
// both. Before this the sidebar had its own `_sortPapers` and the picker
// had no sort at all.
//
// Pure — no DOM, no state — so tests/src/sorting.test.js loads it as is.

window.Sorting = (function () {
  "use strict";

  function spec(sorts, key) {
    return (sorts || []).find(s => s.key === key) || (sorts || [])[0] || null;
  }

  /** New array, `rows` sorted by the option `key` in direction `dir`
   *  ("asc" | "desc"). Never mutates `rows`. Rows with no value sort LAST
   *  in both directions — an undated paper should not lead "newest first". */
  function sortRows(sorts, rows, key, dir) {
    const s = spec(sorts, key);
    if (!s) return [...rows];
    const mult = dir === "desc" ? -1 : 1;
    const val = (r) => {
      const v = s.value(r);
      if (s.numeric) {
        const n = parseFloat(v);
        return Number.isFinite(n) ? n : null;
      }
      const t = String(v == null ? "" : v).trim().toLowerCase();
      return t && t !== "unknown" ? t : null;
    };
    return rows
      .map((r, i) => ({ r, i, v: val(r) }))
      .sort((a, b) => {
        if (a.v === null && b.v === null) return a.i - b.i;
        if (a.v === null) return 1;
        if (b.v === null) return -1;
        if (a.v < b.v) return -1 * mult;
        if (a.v > b.v) return 1 * mult;
        return a.i - b.i;                       // stable: keep incoming order on ties
      })
      .map(x => x.r);
  }

  /** The direction an option naturally reads in — "Date added" and
   *  counts newest / largest first, names A→Z. */
  function defaultDir(sorts, key) {
    const s = spec(sorts, key);
    return (s && s.defaultDir) || "asc";
  }

  return { sortRows, defaultDir, spec };
})();
