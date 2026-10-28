// Corpus — provenance + coverage helpers shared across every entity
// detail pane (paper / author / institution / journal). Extracted from
// four copy-pasted implementations on 2026-08-16.
//
// Loaded AFTER `tooltips.default.js` and BEFORE the detail modules so
// that `Provenance` / `Coverage` exist on `window` at parse-time when
// the detail modules declare their functions. Function bodies still
// resolve `SRC_ABBR`, `escHtml`, `escAttr`, `tt` at call-time — same
// pattern as the detail modules use for other app.js globals.
//
// See CODE_MAP.md, "Feature → files map / Shared helpers".

(function () {
  // Which raw `sources_seen` / `<field>_from` strings map to which
  // Corpus-facing column abbreviation. Superset of every historical
  // per-page variant — paper detail always counted "crossref-search"
  // as C; author / institution / journal detail did not. Now all four
  // pages behave the same.
  const SRC_TAG = {
    C:  ["crossref", "crossref-search"],
    SS: ["semanticscholar"],
    OA: ["openalex"],
  };

  // "Winner + verifiers" badge strip. `arr` is a `[winner, ...verifiers]`
  // list of raw source names. Dedupes to abbreviations (two crossref
  // variants → one C) while preserving order. Empty when there's no
  // provenance to show.
  function badgeFromArr(arr) {
    if (!Array.isArray(arr) || !arr.length) return "";
    const seen = new Set();
    const items = [];
    arr.forEach((s, i) => {
      const abbr = SRC_ABBR[s] || s;
      if (seen.has(abbr)) return;
      seen.add(abbr);
      items.push({ abbr, isWinner: i === 0 });
    });
    return ` <span class="prov">${items.map(it =>
      `<span class="prov-tag ${it.isWinner ? "win" : "ver"}" title="${escAttr(tt("source." + it.abbr))}">${escHtml(it.abbr)}</span>`
    ).join("")}</span>`;
  }

  // Convenience: read the `<field>_from` array off a frontmatter dict.
  // Callers that already have the array should use `badgeFromArr` directly.
  function badgeFromField(fm, field) {
    return badgeFromArr(fm && fm[`${field}_from`]);
  }

  // Did source `srcAbbr` (one of "C" / "SS" / "OA") contribute to this
  // field? Used by coverage-matrix rows that decide per-column ✓ / ✗.
  function inSource(fromArr, srcAbbr) {
    const wanted = SRC_TAG[srcAbbr] || [];
    return Array.isArray(fromArr) && fromArr.some(s => wanted.includes(s));
  }

  // Render one <td> content for a coverage matrix cell. Values:
  //   null / undefined  — source doesn't track this field  (—)
  //   "skip" / "SKIP"   — source has it, Corpus skips it   (⊘)
  //   true              — present                          (✓)
  //   anything else     — absent                           (✗)
  //
  // Case-insensitive on "skip" because paper detail historically used
  // lowercase and the other three used uppercase. Both accepted.
  function coverageCell(v) {
    if (v === null || v === undefined) {
      return `<span class="cov-na"   title="${escAttr(tt("coverage.state.na"))}">—</span>`;
    }
    if (v === "skip" || v === "SKIP") {
      return `<span class="cov-skip" title="${escAttr(tt("coverage.state.skipped"))}">⊘</span>`;
    }
    if (v === true) {
      return `<span class="cov-yes"  title="${escAttr(tt("coverage.state.present"))}">✓</span>`;
    }
    return   `<span class="cov-no"   title="${escAttr(tt("coverage.state.absent"))}">✗</span>`;
  }

  const COVERAGE_LEGEND_HTML =
    `<p class="cov-legend">` +
    `<span class="cov-yes">✓</span> present · ` +
    `<span class="cov-no">✗</span> source could return this but didn&#39;t · ` +
    `<span class="cov-skip">⊘</span> source has this, Corpus deliberately doesn&#39;t extract · ` +
    `<span class="cov-na">—</span> source doesn&#39;t track this field` +
    `</p>`;

  // Full "Coverage" section renderer. `rows` is a list of
  // `[label, cr, ss, oa, tooltipKey]` tuples where the middle three
  // are values in the format `coverageCell` accepts.
  function renderCoverageTable(rows) {
    return `
    <div class="pd-coverage">
      <h3 title="${escAttr(tt("section.coverage"))}">Coverage</h3>
      <table class="cov-table">
        <thead><tr>
          <th></th>
          <th title="${escAttr(tt("source.C"))}">Crossref</th>
          <th title="${escAttr(tt("source.SS"))}">Semantic Scholar</th>
          <th title="${escAttr(tt("source.OA"))}">OpenAlex</th>
        </tr></thead>
        <tbody>
          ${rows.map(([label, cr, ss, oa, ttKey]) => `
            <tr>
              <td class="cov-label" title="${escAttr(tt(ttKey))}">${escHtml(label)}</td>
              <td>${coverageCell(cr)}</td>
              <td>${coverageCell(ss)}</td>
              <td>${coverageCell(oa)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      ${COVERAGE_LEGEND_HTML}
    </div>`;
  }

  window.Provenance = {
    badgeFromArr,
    badgeFromField,
  };
  window.Coverage = {
    SRC_TAG,
    inSource,
    cell: coverageCell,
    LEGEND_HTML: COVERAGE_LEGEND_HTML,
    renderTable: renderCoverageTable,
  };
})();
