// Corpus — Institution detail. Split from app.js on 2026-08-15.
//
// Depends on globals from app.js (resolved at call-time): `state`,
// `api`, `toast`, `$`, `escHtml`, `escAttr`, `hideEmptyState`,
// `SRC_ABBR`, `fmtTs`, `tsSpan`, `_relativeTime`.
// Depends on globals from provenance.js (loaded before this file):
// `Provenance.badgeFromArr`, `Coverage.inSource`.
// Depends on globals from entity-detail.js: `EntityDetail.render` —
// shared render skeleton for author / institution / journal panes.
//
// See CODE_MAP.md for the full picture.

// ---------- Institution detail ----------

async function loadInstitutionDetail(key) {
  hideEmptyState();
  const pane = $("#institution-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.institutionDetail = await api(`/api/institution/${encodeURIComponent(key)}`);
    renderInstitutionDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function renderInstitutionDetail() {
  const i = state.institutionDetail;
  if (!i) return;
  const pane = $("#institution-detail");

  // Shared helpers — see provenance.js.
  const provFromArr = Provenance.badgeFromArr;
  const inSrc       = Coverage.inSource;

  // OA per-institution enrichment (loaded from ~/.corpus/oa_cache/) —
  // may be absent when institution has no ROR or the OA fetch failed.
  const enr = i.oa_enrichment || {};
  const enrFetched = i.oa_enrichment_fetched || "";

  // Meta rows
  const rows = [
    ["Authors in corpus", `${i.authors.length}${provFromArr(i.sources_seen)}`],
    ["Papers in corpus",  `${i.papers.length}`],
    ...(i.ror ? [["ROR ID",
      `<a href="${escAttr(i.ror)}" target="_blank">${escHtml(i.ror.replace(/^https?:\/\/(www\.)?ror\.org\//, ""))}</a>${provFromArr(["openalex"])}`]] : []),
    ...(i.country_code ? [["Country", `${escHtml(Countries.withCode(i.country_code))}${provFromArr(["openalex"])}`]] : []),
    ...(i.type         ? [["Type",    `${escHtml(i.type)}${provFromArr(["openalex"])}`]]         : []),
    ...(i.lineage && i.lineage.length ? [["Lineage IDs", `${i.lineage.length} parent${i.lineage.length === 1 ? "" : "s"}${provFromArr(["openalex"])}`]] : []),
    // OA enrichment fields — appear only when the /institutions/<id>
    // lookup returned something. Each carries the OA provenance badge.
    ...(enr.homepage_url ? [["Homepage",
      `<a href="${escAttr(enr.homepage_url)}" target="_blank">${escHtml(enr.homepage_url)}</a>${provFromArr(["openalex"])}`]] : []),
    ...(enr.geo && (enr.geo.city || enr.geo.region || enr.geo.latitude != null) ? [["Location",
      `${[enr.geo.city, enr.geo.region, Countries.name(enr.geo.country_code)].filter(Boolean).map(escHtml).join(", ")}${
        enr.geo.latitude != null && enr.geo.longitude != null
          ? ` <span class="muted">(${enr.geo.latitude.toFixed(3)}, ${enr.geo.longitude.toFixed(3)})</span>`
          : ""
      }${provFromArr(["openalex"])}`]] : []),
    ...(typeof enr.works_count === "number" ? [["Works count",
      `${enr.works_count.toLocaleString()}${provFromArr(["openalex"])}`]] : []),
    ...(typeof enr.cited_by_count === "number" ? [["Citations",
      `${enr.cited_by_count.toLocaleString()}${provFromArr(["openalex"])}`]] : []),
    ...(enr.summary_stats && typeof enr.summary_stats.h_index === "number" ? [["Institution h-index",
      `${enr.summary_stats.h_index}${provFromArr(["openalex"])}`]] : []),
  ];

  // Lineage (parent-org OA IDs). Opaque URLs — we'd need to fetch
  // /institutions/<id> to get names, deferred. Show them as links.
  const lineageBlock = (i.lineage && i.lineage.length) ? `
    <div class="pd-affils">
      <h3 title="Parent organizations in OpenAlex's institution hierarchy (opaque IDs — clicking opens the OpenAlex page for that org).">Lineage (OA IDs)${provFromArr(["openalex"])}</h3>
      <ul>
        ${i.lineage.map(id => `
          <li><a href="${escAttr(id)}" target="_blank" class="muted">${escHtml(id)}</a></li>
        `).join("")}
      </ul>
    </div>` : "";

  // Associated concepts (from OA enrichment) — top-5 topics this
  // institution is associated with, with relevance scores.
  const conceptsBlock = (enr.x_concepts && enr.x_concepts.length) ? `
    <div class="pd-affils">
      <h3 title="Topics OpenAlex associates with this institution across their body of work (top 5, ranked by relevance).">Associated concepts${provFromArr(["openalex"])}</h3>
      <ul>
        ${enr.x_concepts.map(c => `
          <li>${escHtml(c.display_name)}${
            typeof c.score === "number" ? ` <span class="muted">(${(c.score * 100).toFixed(0)}%)</span>` : ""
          }</li>
        `).join("")}
      </ul>
    </div>` : "";

  // Authors from this institution.
  const authorsBlock = `
    <div class="pd-affils">
      <h3 title="Authors from this institution currently in Corpus.">Authors (${i.authors.length})</h3>
      <ul>
        ${i.authors.map(a => {
          const displayName = a.given ? `${a.family}, ${a.given}` : a.family;
          return `<li><a href="#" data-open-author="${escAttr(a.key)}">${escHtml(displayName)}</a></li>`;
        }).join("")}
      </ul>
    </div>`;

  // Papers with at least one author from this institution.
  const papersBlock = `
    <div class="pd-refs">
      <h3 title="Papers in Corpus with at least one author affiliated with this institution.">Papers in corpus (${i.papers.length})</h3>
      <ol>
        ${i.papers.map(p => `
          <li>
            <a href="#" data-open-paper="${escAttr(p.slug)}">${escHtml(p.title || p.slug)}</a>
            <span class="muted"> — ${escHtml(String(p.year || "?"))}</span>
          </li>
        `).join("")}
      </ol>
    </div>`;

  // Coverage matrix — same 4-state contract as papers/authors.
  const covRows = [
    // Identity
    ["Display name",         inSrc(i.sources_seen, "C"),  inSrc(i.sources_seen, "SS"),  inSrc(i.sources_seen, "OA"),  "inst.row.display_name"],
    ["ROR ID",               null,                        null,                         Boolean(i.ror),               "inst.row.ror"],
    ["Country code",         null,                        null,                         Boolean(i.country_code),      "inst.row.country_code"],
    ["Type",                 null,                        null,                         Boolean(i.type),              "inst.row.type"],
    // Hierarchy / metadata
    ["Lineage (parent orgs)",null,                        null,                         (i.lineage || []).length > 0, "inst.row.lineage"],
    ["Alternate names",      null,                        null,                         "SKIP",                       "inst.row.alt_names"],
    ["Homepage URL",         null,                        null,                         Boolean(enr.homepage_url),    "inst.row.homepage"],
    ["Geo coordinates",      null,                        null,                         Boolean(enr.geo && enr.geo.latitude != null), "inst.row.geo"],
    // Body-of-work profile — now fetched via /institutions/<id>.
    ["Institution works count", null,                     "SKIP",                       typeof enr.works_count === "number",    "inst.row.works_count"],
    ["Institution citations",   null,                     "SKIP",                       typeof enr.cited_by_count === "number", "inst.row.citations"],
    ["Associated concepts",     null,                     null,                         (enr.x_concepts || []).length > 0, "inst.row.concepts"],
  ];
  pane.innerHTML = EntityDetail.render({
    h1:       i.name,
    subtitle: [Countries.name(i.country_code), i.type].filter(Boolean).map(escHtml).join(" · "),
    metaRows: rows,
    // Refresh bar only when we have a ROR (OA enrichment key). No ROR
    // = no enrichment possible = no refresh button.
    refresh: i.ror ? { entity: "institution", key: i.key, fetchedAt: enrFetched } : null,
    sideBlocks: [lineageBlock, conceptsBlock, authorsBlock, papersBlock],
    coverage: covRows,
  });
}

// Small helper — "3 minutes ago" / "2 days ago" style relative time
// for the "last updated" pill next to Refresh from source.
