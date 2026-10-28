// Corpus — Journal detail. Split from app.js on 2026-08-15.
//
// Depends on globals from app.js (resolved at call-time): `state`,
// `api`, `toast`, `$`, `escHtml`, `escAttr`, `hideEmptyState`,
// `SRC_ABBR`, `fmtTs`, `tsSpan`, `_relativeTime`.
// Depends on globals from provenance.js (loaded before this file):
// `Provenance.badgeFromArr`, `Coverage.inSource`.
// Depends on globals from entity-detail.js: `EntityDetail.render` —
// shared render skeleton for author / institution / journal panes.

// ---------- Journal detail ----------

async function loadJournalDetail(key) {
  hideEmptyState();
  const pane = $("#journal-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.journalDetail = await api(`/api/journal/${encodeURIComponent(key)}`);
    renderJournalDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function renderJournalDetail() {
  const j = state.journalDetail;
  if (!j) return;
  const pane = $("#journal-detail");

  // Shared helpers — see provenance.js.
  const provFromArr = Provenance.badgeFromArr;
  const inSrc       = Coverage.inSource;

  // OA per-source enrichment (loaded from ~/.corpus/oa_cache/journals/) —
  // absent when the journal has no ISSN or the OA fetch failed.
  const enr = j.oa_enrichment || {};
  const enrFetched = j.oa_enrichment_fetched || "";
  // Prefer OA's homepage URL over SS's venue URL — same field, OA is
  // usually cleaner. Fall back to SS when OA doesn't have one.
  const homepageUrl = enr.homepage_url || j.ss_venue_url || "";

  const rows = [
    ["Papers in corpus", `${j.papers.length}${provFromArr(j.sources_seen)}`],
    ...(j.year_range ? [["Year range", escHtml(j.year_range)]] : []),
    ...(j.issns.length ? [["ISSN(s)",
      `${j.issns.map(escHtml).join(", ")}${provFromArr(j.issns_from)}`]] : []),
    ...(j.host_organization ? [["Publisher",
      `${escHtml(j.host_organization)}${provFromArr(j.host_organization_from)}`]] : []),
    ...(j.host_organization_lineage && j.host_organization_lineage.length ? [["Publisher hierarchy",
      `${j.host_organization_lineage.map(escHtml).join(" › ")}${provFromArr(["openalex"])}`]] : []),
    ...(j.venue_type    ? [["Venue type",       `${escHtml(j.venue_type)}${provFromArr(j.venue_type_from)}`]] : []),
    ...(j.ss_venue_type && j.ss_venue_type !== j.venue_type
                        ? [["Venue type (SS)",  `${escHtml(j.ss_venue_type)}${provFromArr(["semanticscholar"])}`]] : []),
    ...(homepageUrl ? [["Homepage",
      `<a href="${escAttr(homepageUrl)}" target="_blank">${escHtml(homepageUrl)}</a>${provFromArr(enr.homepage_url ? ["openalex"] : ["semanticscholar"])}`]] : []),
    // ---- OA per-source enrichment fields ------------------------------
    ...(enr.country_code ? [["Country of publication",
      `${escHtml(Countries.withCode(enr.country_code))}${provFromArr(["openalex"])}`]] : []),
    ...(typeof enr.works_count === "number" ? [["Journal works count",
      `${enr.works_count.toLocaleString()}${provFromArr(["openalex"])}`]] : []),
    ...(typeof enr.cited_by_count === "number" ? [["Journal citations",
      `${enr.cited_by_count.toLocaleString()}${provFromArr(["openalex"])}`]] : []),
    ...(enr.summary_stats && typeof enr.summary_stats["2yr_mean_citedness"] === "number" ? [["2-yr mean citedness",
      `${enr.summary_stats["2yr_mean_citedness"].toFixed(2)} <span class="muted">(impact-factor equivalent)</span>${provFromArr(["openalex"])}`]] : []),
    ...(enr.summary_stats && typeof enr.summary_stats.h_index === "number" ? [["Journal h-index",
      `${enr.summary_stats.h_index}${provFromArr(["openalex"])}`]] : []),
    ...(enr.is_in_doaj !== undefined || enr.is_oa !== undefined ? [["Open access status",
      `${enr.is_oa ? "OA journal" : "not OA"}${enr.is_in_doaj ? " · listed in DOAJ" : ""}${provFromArr(["openalex"])}`]] : []),
    ...(enr.apc_prices && enr.apc_prices.length ? [["APC (list price)",
      `${enr.apc_prices.map(a => `${a.price} ${a.currency}`).join(" · ")}${provFromArr(["openalex"])}`]] : []),
  ];

  // Alternate names — SS-provided list of other names for the venue.
  const altNamesBlock = (j.ss_venue_alternate_names && j.ss_venue_alternate_names.length) ? `
    <div class="pd-affils">
      <h3 title="Other names by which this venue is known (previous names, abbreviations, translations).">Alternate names${provFromArr(["semanticscholar"])}</h3>
      <ul>${j.ss_venue_alternate_names.map(n => `<li class="muted">${escHtml(n)}</li>`).join("")}</ul>
    </div>` : "";

  // Associated concepts (top-5 topics OA associates with this venue).
  const conceptsBlock = (enr.x_concepts && enr.x_concepts.length) ? `
    <div class="pd-affils">
      <h3 title="Topics OpenAlex associates with this venue's body of work (top 5, ranked by relevance).">Associated concepts${provFromArr(["openalex"])}</h3>
      <ul>
        ${enr.x_concepts.map(c => `
          <li>${escHtml(c.display_name)}${
            typeof c.score === "number" ? ` <span class="muted">(${(c.score * 100).toFixed(0)}%)</span>` : ""
          }</li>
        `).join("")}
      </ul>
    </div>` : "";

  // Papers-in-journal list.
  const papersBlock = `
    <div class="pd-refs">
      <h3 title="Every paper in Corpus that appeared in this venue.">Papers in corpus (${j.papers.length})</h3>
      <ol>
        ${j.papers.map(p => `
          <li>
            <a href="#" data-open-paper="${escAttr(p.slug)}">${escHtml(p.title || p.slug)}</a>
            <span class="muted"> — ${escHtml(String(p.year || "?"))}</span>
          </li>
        `).join("")}
      </ol>
    </div>`;

  // Coverage matrix — same 4-state contract as papers/authors/institutions.
  const covRows = [
    // Identity
    ["Display name",             true,                                  true,                                    true,                                  "journal.row.name"],
    ["Short journal name",       "SKIP",                                null,                                    null,                                  "coverage.row.short_journal"],
    ["ISSN",                     inSrc(j.issns_from, "C"),              inSrc(j.issns_from, "SS"),               inSrc(j.issns_from, "OA"),             "coverage.row.issn"],
    ["Alternate names",          null,                                  j.ss_venue_alternate_names.length > 0,   "SKIP",                                "inst.row.alt_names"],
    // Publisher hierarchy
    ["Publisher organization",   null,                                  null,                                    Boolean(j.host_organization),          "coverage.row.host_organization"],
    ["Publisher hierarchy",      null,                                  null,                                    j.host_organization_lineage.length > 0,"journal.row.hierarchy"],
    // Venue metadata
    ["Venue type",               null,                                  Boolean(j.ss_venue_type),                Boolean(j.venue_type),                 "coverage.row.venue_type"],
    ["Homepage URL",             null,                                  Boolean(j.ss_venue_url),                 Boolean(enr.homepage_url),             "journal.row.url"],
    ["Country of publication",   null,                                  null,                                    Boolean(enr.country_code),             "journal.row.country"],
    // Impact / profile (now fetched via /sources/<id>)
    ["Impact factor equivalent", "SKIP",                                "SKIP",                                  Boolean(enr.summary_stats && enr.summary_stats["2yr_mean_citedness"] != null), "journal.row.impact"],
    ["Journal works count",      null,                                  "SKIP",                                  typeof enr.works_count === "number",   "journal.row.works_count"],
    ["Journal citations",        null,                                  "SKIP",                                  typeof enr.cited_by_count === "number", "journal.row.citations"],
    ["Associated concepts",      null,                                  null,                                    (enr.x_concepts || []).length > 0,     "inst.row.concepts"],
    // Access / OA at journal level
    ["Is in DOAJ / is-OA",       null,                                  null,                                    enr.is_in_doaj !== undefined || enr.is_oa !== undefined, "journal.row.doaj"],
    ["APC price (list)",         null,                                  null,                                    (enr.apc_prices || []).length > 0,     "journal.row.apc"],
    // Skipped elsewhere
    ["Crossref member ID",       "SKIP",                                null,                                    null,                                  "coverage.row.crossref_member"],
  ];
  pane.innerHTML = EntityDetail.render({
    h1: j.name,
    subtitle: [j.host_organization, j.venue_type || j.ss_venue_type, j.year_range]
                .filter(Boolean).map(escHtml).join(" · "),
    metaRows: rows,
    // Refresh bar only when we have at least one ISSN (OA enrichment
    // key). Books / gray literature with no ISSN skip enrichment.
    refresh: j.issns.length ? { entity: "journal", key: j.key, fetchedAt: enrFetched } : null,
    sideBlocks: [altNamesBlock, conceptsBlock, papersBlock],
    coverage: covRows,
  });
}

