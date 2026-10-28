// Corpus — canonical entity keys.
//
// JavaScript mirrors of the Python helpers in `python/server.py`:
//   _author_key(family, given)         → EntityKeys.author(family, given)
//   _journal_key(name, issns)          → EntityKeys.journal(name, issns)
//   _institution_key(name, ror)        → EntityKeys.institution(name, ror)
//
// Used by paper-detail and author-detail (and any future cross-pane
// deep-link source) so `<a data-open-author="…">`,
// `<a data-open-journal="…">`, and `<a data-open-institution="…">`
// land on the same aggregation keys the backend produces.
//
// KEEP IN SYNC WITH server.py. Behavior drift = broken links. See
// `tests/src/entity-keys.test.js` for parity fixtures.

(function () {
  // Normalize a string the same way the Python side does:
  //   1. NFKD decompose (splits "é" → "e" + combining acute).
  //   2. Strip combining marks (mirrors Python's `.encode("ascii", "ignore")`).
  //   3. Runs of non-alphanumerics → single hyphen.
  //   4. Trim leading/trailing hyphens.
  //   5. Lowercase.
  function _norm(s) {
    if (s == null) return "";
    return String(s)
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")   // combining diacriticals
      .replace(/[^a-zA-Z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase();
  }

  function author(family, given) {
    const fam = _norm(family);
    // Python uses the first whitespace-token of `given` — mirror it.
    const firstGiven = (given || "").trim().split(/\s+/)[0] || "";
    const giv = _norm(firstGiven);
    return giv ? `${fam}-${giv}` : fam;
  }

  function institution(name, ror) {
    // ROR wins when present — canonical + stable across name variants.
    // ROR canonical URLs look like "https://ror.org/01tgyzw49"; the
    // Python side takes the last run of ASCII alphanumerics. Bare IDs
    // ("01tgyzw49") match too.
    if (ror) {
      const m = /[a-z0-9]+$/.exec(String(ror).trim());
      if (m) return `ror-${m[0]}`;
    }
    const s = _norm(name);
    return s || "unknown";
  }

  function journal(name, issns) {
    // ISSN wins when present — canonical + dedup-friendly across name
    // variants. Matches the Python backend exactly:
    //   * `issn: 0028-0836` (bare string in YAML) → treated as [str]
    //   * `issn: [0028-0836, 1476-4687]` (list) → first entry used
    //   * surrounding quotes stripped (YAML quirk, mirrors _strip_quotes)
    //   * uppercase, whitespace stripped
    let list = issns;
    if (typeof list === "string" && list.trim()) list = [list];
    if (!Array.isArray(list)) list = [];
    if (list.length) {
      let raw = String(list[0] == null ? "" : list[0]).trim();
      const quoted = /^(?:"([^"]*)"|'([^']*)')$/.exec(raw);
      if (quoted) raw = quoted[1] != null ? quoted[1] : quoted[2];
      const v = raw.toUpperCase().replace(/\s+/g, "");
      if (v) return `issn-${v}`;
    }
    const s = _norm(name);
    return s || "unknown";
  }

  window.EntityKeys = { author, institution, journal };
})();
