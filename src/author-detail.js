// Corpus — Author detail. Split from app.js on 2026-08-15.
//
// Depends on globals from app.js (resolved at call-time): `state`,
// `api`, `toast`, `$`, `escHtml`, `escAttr`, `hideEmptyState`,
// `SRC_ABBR`, `fmtTs`, `tsSpan`, `_relativeTime`.
// Depends on globals from provenance.js (loaded before this file):
// `Provenance.badgeFromArr`, `Coverage.inSource`.
// Depends on globals from entity-keys.js: `EntityKeys.institution`
// (used for the deep-link on each affiliated institution).
// Depends on globals from entity-detail.js: `EntityDetail.render` —
// shared render skeleton for author / institution / journal panes.
//
// See CODE_MAP.md for the full picture.

// ---------- Author detail ----------

async function loadAuthorDetail(key) {
  hideEmptyState();
  const pane = $("#author-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.authorDetail = await api(`/api/author/${encodeURIComponent(key)}`);
    renderAuthorDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function renderAuthorDetail() {
  const a = state.authorDetail;
  if (!a) return;
  const pane = $("#author-detail");
  const displayName = a.given ? `${a.family}, ${a.given}` : a.family;

  // ORCID link (accept both raw hex and full URL forms).
  const orcidUrl = a.orcid
    ? (a.orcid.startsWith("http") ? a.orcid : `https://orcid.org/${a.orcid}`)
    : "";

  // Local alias so existing call sites stay short. Actual rendering
  // lives in provenance.js; see the paper / institution / journal
  // detail modules for the parallel usage.
  const provFromArr = Provenance.badgeFromArr;

  // Position histogram summary — "first: 3, middle: 5, last: 1".
  const positions = a.position_counts || {};
  const posLine = Object.keys(positions).length
    ? ["first","middle","last"].filter(k => positions[k])
        .map(k => `${escHtml(k)}: ${positions[k]}`).join(" · ")
    : "unknown";

  // OA per-author enrichment — from ~/.corpus/oa_cache/authors/<orcid>.json.
  const enr = a.oa_enrichment || {};
  const enrFetched = a.oa_enrichment_fetched || "";
  const oaId = enr.id || "";  // opaque URL like https://openalex.org/A123
  // For h-index / total papers / total citations Corpus now has SS's
  // and OA's numbers. Show the higher one as the "winner" and the
  // other as a verifier when both present.
  const oaH   = enr.summary_stats && typeof enr.summary_stats.h_index === "number" ? enr.summary_stats.h_index : null;
  const oaWks = typeof enr.works_count === "number" ? enr.works_count : null;
  const oaCit = typeof enr.cited_by_count === "number" ? enr.cited_by_count : null;
  const hSources   = [oaH   !== null ? "openalex" : null, typeof a.h_index === "number"           ? "semanticscholar" : null].filter(Boolean);
  const wksSources = [oaWks !== null ? "openalex" : null, typeof a.papers_count_ss === "number"   ? "semanticscholar" : null].filter(Boolean);
  const citSources = [oaCit !== null ? "openalex" : null, typeof a.citation_count_ss === "number" ? "semanticscholar" : null].filter(Boolean);
  // Preferred value: whichever source is available; when both, show
  // OA (usually higher — bigger citation graph) with SS as verifier.
  const preferred = (oa, ss) => oa !== null ? oa : (typeof ss === "number" ? ss : null);

  const rows = [
    ["Papers in corpus", `${a.papers.length}${provFromArr(a.sources_seen)}`],
    ...(a.orcid ? [["ORCID",
      `<a href="${escAttr(orcidUrl)}" target="_blank">${escHtml(a.orcid.replace(/^https?:\/\/(www\.)?orcid\.org\//,""))}</a>${provFromArr(a.orcid_from)}`]] : []),
    ...(hSources.length ? [["h-index", `${preferred(oaH, a.h_index)}${provFromArr(hSources)}`]] : []),
    ...(wksSources.length ? [["Total papers", `${preferred(oaWks, a.papers_count_ss).toLocaleString()}${provFromArr(wksSources)}`]] : []),
    ...(citSources.length ? [["Total citations", `${preferred(oaCit, a.citation_count_ss).toLocaleString()}${provFromArr(citSources)}`]] : []),
    ...(enr.summary_stats && typeof enr.summary_stats.i10_index === "number" ? [["i10-index", `${enr.summary_stats.i10_index}${provFromArr(["openalex"])}`]] : []),
    ...(enr.summary_stats && typeof enr.summary_stats["2yr_mean_citedness"] === "number" ? [["2-yr mean citedness",
      `${enr.summary_stats["2yr_mean_citedness"].toFixed(2)}${provFromArr(["openalex"])}`]] : []),
    ...(enr.last_known_institution && enr.last_known_institution.display_name ? [["Last-known institution",
      `${escHtml(enr.last_known_institution.display_name)}${enr.last_known_institution.country_code ? ` <span class="muted">· ${escHtml(Countries.name(enr.last_known_institution.country_code))}</span>` : ""}${provFromArr(["openalex"])}`]] : []),
    ["Position (in-corpus papers)", posLine],
    ...(a.corresponding_on.length ? [["Corresponding on",
      `${a.corresponding_on.length} paper${a.corresponding_on.length === 1 ? "" : "s"}${provFromArr(["openalex"])}`]] : []),
    ...(a.ss_id ? [["Semantic Scholar ID", `<a href="https://www.semanticscholar.org/author/${escAttr(a.ss_id)}" target="_blank">${escHtml(a.ss_id)}</a>`]] : []),
    ...(oaId ? [["OpenAlex ID", `<a href="${escAttr(oaId)}" target="_blank">${escHtml(oaId.replace(/^https?:\/\/openalex\.org\//,""))}</a>${provFromArr(["openalex"])}`]] : []),
  ];

  // Institutions section — every distinct place this author has been
  // affiliated across their corpus papers.
  const institutionsBlock = (a.institutions && a.institutions.length) ? `
    <div class="pd-affils">
      <h3 title="Distinct institutions across this author's corpus papers.">Institutions${provFromArr(a.institutions_from)}</h3>
      <ul class="pd-affils-list">
        ${a.institutions.map(inst => {
          // Wrap the name in a deep-link to the Institutions tab.
          // ROR ↗ next to it stays external (points to ror.org).
          const key = EntityKeys.institution(inst.name || "", inst.ror || "");
          return `
          <li>
            <strong><a href="#" data-open-institution="${escAttr(key)}">${escHtml(inst.name)}</a></strong>
            ${inst.country_code ? ` <span class="muted">· ${escHtml(Countries.name(inst.country_code))}</span>` : ""}
            ${inst.type         ? ` <span class="muted">· ${escHtml(inst.type)}</span>`         : ""}
            ${inst.ror          ? ` <a href="${escAttr(inst.ror)}" target="_blank" class="muted">ROR ↗</a>` : ""}
          </li>`;
        }).join("")}
      </ul>
    </div>` : "";

  // Raw affiliation strings (OA) — publisher's original text.
  const rawAffBlock = (a.raw_affiliations && a.raw_affiliations.length) ? `
    <div class="pd-affils">
      <h3 title="Publisher's original affiliation text before OpenAlex normalized it. Useful for verifying the automatic institution matching.">Raw affiliation strings${provFromArr(["openalex"])}</h3>
      <ul>${a.raw_affiliations.map(r => `<li class="muted">${escHtml(r)}</li>`).join("")}</ul>
    </div>` : "";

  // Topic footprint (OA x_concepts) — what this author publishes about.
  const conceptsBlock = (enr.x_concepts && enr.x_concepts.length) ? `
    <div class="pd-affils">
      <h3 title="Topics OpenAlex associates with this author across their body of work (top 5, ranked by relevance score).">Topic footprint${provFromArr(["openalex"])}</h3>
      <ul>
        ${enr.x_concepts.map(c => `
          <li>${escHtml(c.display_name)}${
            typeof c.score === "number" ? ` <span class="muted">(${(c.score * 100).toFixed(0)}%)</span>` : ""
          }</li>
        `).join("")}
      </ul>
    </div>` : "";

  // Career citations-by-year mini chart (OA counts_by_year). Same
  // visual language as the per-paper CBY chart on the paper detail
  // pane — horizontal bars per year, sized by that year's count.
  const cbyBlock = (enr.counts_by_year && enr.counts_by_year.length) ? (() => {
    const years = enr.counts_by_year.slice().sort((a, b) => a.year - b.year);
    const maxCites = Math.max(1, ...years.map(y => y.cited_by_count || 0));
    const bars = years.map(y => {
      const w = ((y.cited_by_count || 0) / maxCites) * 100;
      return `
        <div class="cby-row" title="${y.year}: ${y.cited_by_count || 0} citations, ${y.works_count || 0} works">
          <span class="cby-year">${y.year}</span>
          <span class="cby-bar" style="width: ${w.toFixed(1)}%">&nbsp;</span>
          <span class="cby-count">${(y.cited_by_count || 0).toLocaleString()}</span>
        </div>`;
    }).join("");
    return `
      <div class="pd-affils">
        <h3 title="How many citations this author's work received each year across their career. Last ~15 years from OpenAlex.">Career citations-by-year${provFromArr(["openalex"])}</h3>
        <div class="cby-chart">${bars}</div>
      </div>`;
  })() : "";

  // Papers-by-author table.
  const papersBlock = `
    <div class="pd-refs">
      <h3 title="Every paper by this author currently in Corpus.">Papers in corpus (${a.papers.length})</h3>
      <ol>
        ${a.papers.map(p => `
          <li>
            <a href="#" data-open-paper="${escAttr(p.slug)}">${escHtml(p.title || p.slug)}</a>
            <span class="muted"> — ${escHtml(String(p.year || "?"))}${
              p.position ? ` · ${escHtml(p.position)}` : ""
            }${p.is_corresponding ? " · corresponding" : ""}</span>
          </li>
        `).join("")}
      </ol>
    </div>`;

  // Coverage matrix — same 4-state contract as the paper coverage
  // table (✓ present / ✗ absent / ⊘ SKIP / — n/a). Every author-level
  // field each source could contribute gets a row, including ones
  // Corpus deliberately doesn't extract, so the table is a complete
  // picture of what's out there, not just what we grabbed.
  const inSrc = Coverage.inSource;
  // Rows: [label, cr, ss, oa, tooltip-key]
  //   true / false / "SKIP" / null — same encoding as the paper table
  const authorCovRows = [
    // -------- Identity ---------------------------------------------
    ["Full name",              true,                                    true,                                    true,                                          "coverage.row.authors_structured"],
    ["Given / family split",   true,                                    Boolean((a.family || "") && (a.given || "")),  true,                             "coverage.row.authors_structured"],
    ["Author position",        Object.keys(positions).length > 0,       null,                                    Object.keys(positions).length > 0,             "coverage.row.author_position"],
    ["ORCID",                  inSrc(a.orcid_from, "C"),                inSrc(a.orcid_from, "SS"),               inSrc(a.orcid_from, "OA"),                     "coverage.row.orcid_per_author"],
    ["ORCID verified flag",    "SKIP",                                  null,                                    null,                                          "author.row.orcid_verified"],
    ["Name prefix / suffix",   "SKIP",                                  null,                                    null,                                          "author.row.name_prefix_suffix"],
    // -------- Affiliation ------------------------------------------
    ["Institutions",           inSrc(a.institutions_from, "C"),         inSrc(a.institutions_from, "SS"),        inSrc(a.institutions_from, "OA"),              "coverage.row.inst_ror"],
    ["Institution ROR ID",     null,                                    null,                                    a.institutions.some(i => i.ror),               "coverage.row.inst_ror"],
    ["Institution country",    null,                                    null,                                    a.institutions.some(i => i.country_code),      "coverage.row.inst_ror"],
    ["Institution type",       null,                                    null,                                    a.institutions.some(i => i.type),              "coverage.row.inst_ror"],
    ["Institution lineage",    null,                                    null,                                    "SKIP",                                        "author.row.inst_lineage"],
    ["Raw affiliation strings",null,                                    null,                                    a.raw_affiliations.length > 0,                 "coverage.row.raw_affiliations"],
    ["Raw author name",        null,                                    null,                                    a.papers.some(p => true) ? "SKIP" : "SKIP",    "author.row.raw_name"],
    ["Corresponding flag",     null,                                    null,                                    a.corresponding_on.length > 0,                 "coverage.row.corresponding"],
    // -------- Profile stats ----------------------------------------
    ["h-index",                null,                                    typeof a.h_index === "number",           oaH !== null,                                  "coverage.row.author_hindex"],
    ["Total papers count",     null,                                    typeof a.papers_count_ss === "number",   oaWks !== null,                                "coverage.row.author_hindex"],
    ["Total citations",        null,                                    typeof a.citation_count_ss === "number", oaCit !== null,                                "coverage.row.author_hindex"],
    ["SS author profile ID",   null,                                    Boolean(a.ss_id),                        null,                                          "author.row.ss_id"],
    ["OpenAlex author ID",     null,                                    null,                                    Boolean(oaId),                                 "author.row.oa_id"],
    // -------- Author-body-of-work ----------------------------------
    ["Full papers list",       null,                                    "SKIP",                                  "SKIP",                                        "author.row.papers_list"],
    ["Career citations-by-year", null,                                  "SKIP",                                  (enr.counts_by_year || []).length > 0,         "author.row.author_cby"],
    ["Topic footprint",        null,                                    null,                                    (enr.x_concepts || []).length > 0,             "author.row.author_topics"],
  ];
  pane.innerHTML = EntityDetail.render({
    h1: displayName,
    subtitle: a.institutions.length
      ? escHtml(a.institutions[0].name) +
        (a.institutions[0].country_code ? " · " + escHtml(Countries.name(a.institutions[0].country_code)) : "")
      : "",
    metaRows: rows,
    // Refresh bar only when we have an ORCID (OA enrichment key). No
    // ORCID = no enrichment possible = no refresh button.
    refresh: a.orcid ? { entity: "author", key: a.key, fetchedAt: enrFetched } : null,
    sideBlocks: [institutionsBlock, rawAffBlock, conceptsBlock, cbyBlock, papersBlock],
    coverage: authorCovRows,
  });
}

