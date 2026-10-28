// Corpus — Paper detail. Split from app.js on 2026-08-15.
//
// Depends on globals from app.js (resolved at call-time): `state`,
// `api`, `toast`, `$`, `escHtml`, `escAttr`, `hideEmptyState`,
// `SRC_ABBR`, `fmtTs`, `tsSpan`, `_relativeTime`.
// Depends on globals from provenance.js (loaded before this file):
// `Provenance.badgeFromField`, `Coverage.inSource`, `Coverage.cell`,
// `Coverage.renderTable`.
// Depends on globals from entity-keys.js: `EntityKeys.author`,
// `EntityKeys.journal` — used to build cross-pane deep-link anchors
// with the same keys the backend aggregators produce.
//
// See CODE_MAP.md for the full picture.

// ---------- Paper detail ----------

async function loadPaperDetail(slug) {
  hideEmptyState();
  const pane = $("#paper-detail");
  pane.hidden = false;
  pane.innerHTML = `<p>Loading…</p>`;
  try {
    state.detail = await api(`/api/paper/${encodeURIComponent(slug)}`);
    renderDetail();
  } catch (e) {
    pane.innerHTML = `<p class="err">failed to load: ${escHtml(e.message)}</p>`;
  }
}

function renderDetail() {
  renderPaperInto($("#paper-detail"), state.detail, {
    reload: () => loadPaperDetail(state.detail.slug),
  });
}

/** The full paper-info view, rendered into `host`.
 *
 *  One renderer for every place paper info appears. It used to write into
 *  `#paper-detail` directly, so the popped-out note's side panel carried
 *  its own compact copy — title, authors, year, venue, DOI, abstract —
 *  and Jack (bug report, 2026-09-25): "i should be able to see all the
 *  paper info here. not just this limited info".
 *
 *  opts.panel  — render inside another view (the note panel): info only.
 *                No Paper info / PDF subtabs (the panel has its own), no
 *                pop-out, and no Re-extract or Add to project: those
 *                re-select the paper in the MAIN pane, which a note
 *                window does not show.
 *  opts.reload — re-fetch and re-render THIS host after an action that
 *                changes the data (Find bridges). Without it the action
 *                reloaded `#paper-detail` regardless of where it was
 *                clicked.
 *  Every element lookup below is scoped to `host`, never the document. */
function renderPaperInto(host, d, opts = {}) {
  const panel = Boolean(opts.panel);
  const fm = d.frontmatter || {};
  // Treat literal string "unknown" (what prefill writes when extraction
  // fails) as absent — fall back to the slug so the header is a stable
  // identifier the user can act on. Same for author line.
  const isUnk = (v) => !v || String(v).trim().toLowerCase() === "unknown";
  const displayTitle = isUnk(fm.title) ? d.slug : fm.title;
  const authors_full = Array.isArray(fm.authors_full) ? fm.authors_full : [];
  const authorLine = authors_full.length
    ? authors_full.join(", ")
    : (isUnk(fm.author) ? "" : fm.author);

  // Per-field provenance badges. `<field>_from` is a list emitted by
  // extract_metadata: [winner, ...verifiers]. First badge = the source
  // that produced the value; later badges = sources that verified it.
  // Actual rendering lives in provenance.js so all four detail panes
  // agree on shape / dedupe / winner-vs-verifier styling.
  const provBadge = (field) => Provenance.badgeFromField(fm, field);

  // Lazy show-if: only evaluates the render callback when cond is truthy,
  // so we can dereference fields we're not sure exist without JS blowing
  // up on `undefined.map(...)`.
  const showIf = (cond, fn) => cond ? [fn()] : [];

  // Label → tooltip key lookup for the metadata grid. Labels not in
  // the map get no tooltip (title attr is empty, so no hover effect).
  const META_TT_KEYS = {
    "Title": "meta.title",
    "Year": "meta.year",
    "Kind": "meta.kind",
    "Paper type": "meta.paper_type",
    "Publication types": "meta.publication_types",
    "Publisher": "meta.publisher",
    "Publisher (org)": "meta.host_organization",
    "Venue type": "meta.venue_type",
    "Venue type (SS)": "meta.ss_venue_type",
    "DOI": "meta.doi",
    "Volume": "meta.volume",
    "Issue": "meta.issue",
    "Article #": "meta.article_number",
    "Pages": "meta.pages",
    "Edition": "meta.edition",
    "Chapter": "meta.chapter",
    "Issue published": "meta.journal_issue_date",
    "Language": "meta.language",
    "Cited by": "meta.cited_by",
    "FWCI": "meta.fwci",
    "References count": "meta.references_count",
    "ISSN": "meta.issn",
    "ISBN": "meta.isbn",
    "Alternative IDs": "meta.alternative_ids",
    "Event": "meta.event",
    "Source URL": "meta.source_url",
    "Status": "meta.status",
    "Full text": "meta.has_fulltext",
    "Paratext": "meta.paratext",
    "Deposited (Crossref)": "meta.deposited",
    "Indexed (Crossref)": "meta.indexed",
    "OA record created": "meta.oa_created",
    "OA record updated": "meta.oa_updated",
    "Schema": "meta.schema",
  };
  // citation_count in the MD is `citation_count: 7` — _fm.py returns
  // all scalars as strings, so accept both "7" and 7 as valid ints.
  // Any non-digit / missing value → "unknown".
  // _fm.py returns YAML scalars as strings, so accept both "7" and 7 as
  // valid ints for all count fields.
  const asInt = (v) => (typeof v === "number") ? v
    : (typeof v === "string" && /^-?\d+$/.test(v)) ? parseInt(v, 10)
    : null;
  const citeCr    = asInt(fm.citation_count);
  const citeSs    = asInt(fm.citation_count_ss);
  const citeSsI  = asInt(fm.influential_citation_count_ss);
  const citeOa    = asInt(fm.citation_count_oa);
  const refsNum   = asInt(fm.references_count);
  const citeVal = (citeCr !== null) ? citeCr.toString() : "unknown";
  const fwci = (typeof fm.fwci === "number") ? fm.fwci
              : (typeof fm.fwci === "string" && /^-?[\d.]+$/.test(fm.fwci)) ? parseFloat(fm.fwci)
              : null;
  // Parse the JSON block-scalar fields OA emits.
  const parseJsonField = (raw) => {
    if (!raw || typeof raw !== "string") return null;
    try { return JSON.parse(raw); } catch (_) { return null; }
  };
  const oaAuthors    = parseJsonField(fm.oa_authors);
  const oaTopics     = parseJsonField(fm.topics);
  const oaKeywords   = parseJsonField(fm.keywords);
  const oaLocations  = parseJsonField(fm.oa_locations);
  const oaVersions   = parseJsonField(fm.versions);
  const oaCountsByYear = parseJsonField(fm.counts_by_year);
  const contentAssertions = parseJsonField(fm.content_assertions);
  // Merge SS's per-author profile stats (h-index, papers, citations)
  // + ORCID into whichever author list we're going to display. Match
  // by lowercased family name — imperfect but adequate for the small
  // author lists Corpus deals with.
  const ssAuthorsByFamily = (() => {
    const out = {};
    for (const a of (Array.isArray(fm._ss_authors_raw) ? fm._ss_authors_raw : [])) {
      const nm = String(a && a.name || "").split(" ").pop().toLowerCase();
      if (nm) out[nm] = a;
    }
    return out;
  })();
  const enrichAuthorFromSS = (family) => ssAuthorsByFamily[String(family || "").toLowerCase()] || {};
  // Elsevier's e-journal papers deposit the article number in the `page`
  // field too, so Pages and Article # show the same value. Hide Pages
  // when it's identical.
  const pagesRedundant = fm.article_number && fm.pages &&
    String(fm.pages).trim() === String(fm.article_number).trim();
  const metaRows = [
    ["Title",      escHtml(fm.title || "(no title)") + provBadge("title")],
    ["Year",       (fm.year || "unknown") + provBadge("year")],
    ["Kind",       (fm.kind || "unknown") + provBadge("kind")],
    ...showIf(fm.paper_type && fm.paper_type !== "unknown",
       () => ["Paper type", escHtml(fm.paper_type) + provBadge("paper_type")]),
    ...showIf(Array.isArray(fm.publication_types) && fm.publication_types.length,
       () => ["Publication types",
              escHtml(fm.publication_types.join(", ")) + provBadge("publication_types")]),
    ["Publisher",  (() => {
        // Wrap real publisher names in a deep-link to the Journals tab.
        // "unknown" stays as plain text (no aggregate to jump to).
        // Key comes from the backend (`d.link_keys.journal`) so it
        // always matches what `/api/journal/<key>` accepts; EntityKeys
        // is a fallback for old server versions.
        const raw = fm.publisher || "unknown";
        if (raw === "unknown") return raw + provBadge("publisher");
        const key = (d.link_keys && d.link_keys.journal) || EntityKeys.journal(raw, fm.issn);
        if (!key) return escHtml(raw) + provBadge("publisher");
        return `<a href="#" data-open-journal="${escAttr(key)}">${escHtml(raw)}</a>` + provBadge("publisher");
      })()],
    ...showIf(fm.host_organization && fm.host_organization !== fm.publisher,
       () => ["Publisher (org)",
              escHtml(fm.host_organization)
              + (Array.isArray(fm.host_organization_lineage) && fm.host_organization_lineage.length
                  ? ` <span class="muted">— ${fm.host_organization_lineage.map(escHtml).join(" › ")}</span>`
                  : "")
              + provBadge("host_organization")]),
    ...showIf(fm.venue_type, () => ["Venue type", escHtml(fm.venue_type) + provBadge("venue_type")]),
    ...showIf(fm.ss_venue_type && fm.ss_venue_type !== fm.venue_type,
       () => ["Venue type (SS)", escHtml(fm.ss_venue_type) + provBadge("ss_venue_type")]),
    ["DOI",        (fm.doi && fm.doi !== "unknown"
                     ? `<a href="https://doi.org/${escAttr(fm.doi)}" target="_blank">${escHtml(fm.doi)}</a>`
                     : (fm.needs_doi ? '<span class="warn">no DOI — paste one and re-extract</span>' : "unknown"))
                   + provBadge("doi")],
    ...showIf(fm.volume,         () => ["Volume",        escHtml(fm.volume) + provBadge("volume")]),
    ...showIf(fm.issue,          () => ["Issue",         escHtml(fm.issue)  + provBadge("issue")]),
    ...showIf(fm.article_number, () => ["Article #",     escHtml(fm.article_number) + provBadge("article_number")]),
    ...(pagesRedundant ? [] : [["Pages", (fm.pages || "—") + provBadge("pages")]]),
    ...showIf(fm.language,       () => ["Language",      escHtml(fm.language) + provBadge("language")]),
    // Cited by — one row, all three sources side-by-side, provenance
    // badges inline. FWCI appended when OA gave one.
    ["Cited by",
      [
        citeCr !== null ? `${citeCr}${provBadge("citation_count")}` : null,
        citeSs !== null ? `${citeSs}${provBadge("citation_count_ss")}` : null,
        citeOa !== null ? `${citeOa}${provBadge("citation_count_oa")}` : null,
        citeSsI !== null ? `<span class="muted">${citeSsI} influential${provBadge("influential_citation_count_ss")}</span>` : null,
      ].filter(Boolean).join(' <span class="muted">·</span> ')
      || "unknown"],
    ...showIf(fwci !== null, () => ["FWCI",
      fwci.toFixed(2) + provBadge("fwci") +
      ' <span class="muted" style="font-size:11px">(field-weighted citation impact)</span>']),
    ...showIf(refsNum !== null, () => ["References count", refsNum + provBadge("references_count")]),
    ...showIf(Array.isArray(fm.issn) && fm.issn.length,             () => ["ISSN",         fm.issn.map(escHtml).join(", ") + provBadge("issn")]),
    ...showIf(Array.isArray(fm.isbn) && fm.isbn.length,             () => ["ISBN",         fm.isbn.map(escHtml).join(", ") + provBadge("isbn")]),
    ...showIf(Array.isArray(fm.alternative_ids) && fm.alternative_ids.length,
      () => ["Alternative IDs", fm.alternative_ids.map(escHtml).join(", ") + provBadge("alternative_ids")]),
    ...showIf(fm.event_name, () => ["Event", escHtml(fm.event_name) + (fm.event_acronym ? ` (${escHtml(fm.event_acronym)})` : "") + (fm.event_location ? `, ${escHtml(fm.event_location)}` : "")]),
    ...showIf(fm.edition_number, () => ["Edition", escHtml(fm.edition_number) + provBadge("edition_number")]),
    ...showIf(fm.chapter_number, () => ["Chapter", escHtml(fm.chapter_number) + provBadge("chapter_number")]),
    ...showIf(fm.journal_issue_date, () => ["Issue published", tsSpan(fm.journal_issue_date, {dateOnly: true}) + provBadge("journal_issue_date")]),
    ...showIf(fm.has_fulltext !== undefined, () =>
      ["Full text",
        (fm.has_fulltext === true || fm.has_fulltext === "true" ? "yes" : "no")
        + (fm.fulltext_origin ? ` <span class="muted">(${escHtml(fm.fulltext_origin)})</span>` : "")
        + provBadge("has_fulltext")]),
    ...showIf(fm.is_paratext === true || fm.is_paratext === "true",
       () => ["Paratext", "yes (editorial / front-matter)" + provBadge("is_paratext")]),
    ["Source URL", (fm.source_url && fm.source_url !== "unknown"
                     ? `<a href="${escAttr(fm.source_url)}" target="_blank">${escHtml(fm.source_url)}</a>`
                     : "—") + provBadge("source_url")],
    ["Status",     fm.status || "—"],
    ...showIf(fm.deposited_at, () => ["Deposited (Crossref)", tsSpan(fm.deposited_at) + provBadge("deposited_at")]),
    ...showIf(fm.indexed_at,   () => ["Indexed (Crossref)",   tsSpan(fm.indexed_at)   + provBadge("indexed_at")]),
    ...showIf(fm.oa_created_date, () => ["OA record created", tsSpan(fm.oa_created_date) + provBadge("oa_created_date")]),
    ...showIf(fm.oa_updated_date, () => ["OA record updated", tsSpan(fm.oa_updated_date) + provBadge("oa_updated_date")]),
    ["Schema",     fm.schema_version || "—"],
  ];

  // When OA provided per-author structured data, use it — it has
  // corresponding-author flags, positions, ROR + country per institution.
  // Fall back to the Crossref-derived authors_detailed otherwise.
  const affils = Array.isArray(fm.authors_detailed) ? fm.authors_detailed : [];
  const useOaAuthors = Array.isArray(oaAuthors) && oaAuthors.length > 0;
  const affilBlock = (useOaAuthors ? oaAuthors.length : affils.length) ? `
    <div class="pd-affils">
      <h3 title="${escAttr(tt("section.affiliations"))}">Authors + affiliations${provBadge(useOaAuthors ? "oa_authors" : "authors_detailed")}</h3>
      ${(useOaAuthors ? oaAuthors : affils).map((a, ai) => {
        const nameText = `${escHtml(a.given || "")} ${escHtml(a.family || "")}`.trim() || "(no name)";
        // Deep-link author name to the Authors tab. Key comes from the
        // backend (`d.link_keys.oa_authors` or `.authors_detailed`,
        // parallel to fm.oa_authors / fm.authors_detailed by index)
        // so it always matches what `/api/author/<key>` accepts.
        const authorKey = (d.link_keys
              && d.link_keys[useOaAuthors ? "oa_authors" : "authors_detailed"]
              && d.link_keys[useOaAuthors ? "oa_authors" : "authors_detailed"][ai])
          || (a.family ? EntityKeys.author(a.family, a.given || "") : "");
        const name = authorKey
          ? `<a href="#" data-open-author="${escAttr(authorKey)}">${nameText}</a>`
          : nameText;
        const insts = Array.isArray(a.institutions) ? a.institutions : [];
        // Per-author markers as plain text with muted separators — no
        // pills. Pills are reserved for the C/SS/OA source badges.
        // Position + ORCID + corresponding come from whichever source
        // has them (OA has richest data; Crossref has orcid/position
        // for some papers where OA didn't; SS supplements h-index).
        const ssEntry = enrichAuthorFromSS(a.family);
        const orcid = a.orcid || ssEntry.orcid || "";
        const position = a.position || "";
        const isCorr = !!a.is_corresponding;
        const markers = [];
        if (position)  markers.push(escHtml(position));
        if (isCorr)    markers.push("corresponding");
        if (orcid)     markers.push(`<a href="${escAttr(orcid)}" target="_blank">ORCID</a>`);
        // SS author profile stats (h-index / papers / citations)
        if (typeof ssEntry.h_index === "number")     markers.push(`h-index ${ssEntry.h_index}`);
        if (typeof ssEntry.papers_count === "number") markers.push(`${ssEntry.papers_count} papers`);
        if (typeof ssEntry.citation_count === "number") markers.push(`${ssEntry.citation_count.toLocaleString()} citations`);
        const markerLine = markers.length
          ? ` <span class="muted" style="font-size:12px">· ${markers.join(" · ")}</span>`
          : "";
        // Deep-link institution name to the Institutions tab. Key
        // comes from the backend's per-author institution key list
        // (parallel to the author's `institutions` array by index);
        // EntityKeys.institution is a fallback. External ROR link
        // stays external.
        const instKeysForThisAuthor = (d.link_keys
              && d.link_keys[useOaAuthors ? "oa_authors_insts" : "authors_detailed_insts"]
              && d.link_keys[useOaAuthors ? "oa_authors_insts" : "authors_detailed_insts"][ai])
          || [];
        const instAnchor = (name, ror, ij) => {
          if (!name) return "";
          const key = instKeysForThisAuthor[ij] || EntityKeys.institution(name, ror || "");
          if (!key) return escHtml(name);
          return `<a href="#" data-open-institution="${escAttr(key)}">${escHtml(name)}</a>`;
        };
        const affLines = useOaAuthors
          ? insts.map((inst, ij) => {
              // OA institution: {name, ror, country_code, type, lineage}
              const bits = [instAnchor(inst.name || "", inst.ror || "", ij)];
              const meta = [];
              if (inst.country_code) meta.push(escHtml(Countries.name(inst.country_code)));
              if (inst.type)         meta.push(escHtml(inst.type));
              if (inst.ror) meta.push(`<a href="${escAttr(inst.ror)}" target="_blank">ROR</a>`);
              if (meta.length) bits.push(`<span class="muted">${meta.join(" · ")}</span>`);
              return `<li>${bits.join(" ")}</li>`;
            })
          : insts.map((s, ij) => `<li>${instAnchor(s, "", ij)}</li>`);
        return `<div class="author-block">
          <div class="author-name">${name}${markerLine}</div>
          ${insts.length
            ? `<ul class="affil-list">${affLines.join("")}</ul>`
            : `<div class="no-info">no affiliation reported</div>`}
        </div>`;
      }).join("")}
    </div>
  ` : `
    <div class="pd-affils">
      <h3 title="${escAttr(tt("section.affiliations"))}">Authors + affiliations${provBadge("authors_detailed")}</h3>
      <p class="muted">No structured author records in this paper's metadata.</p>
    </div>
  `;

  // Body is Markdown-ish. For v0.1 render the References section as a
  // bulleted list — bold-delimited `**[...]**` gets stripped, DOI links
  // linkified. Handles all 6 render shapes emit by extract_references.py.
  // References arrive parsed from the server (`citations.resolve_references`).
  // The client used to re-parse the markdown itself; that meant two
  // implementations of the reference-line format with nothing keeping
  // them in step. Server is now the only parser.
  const refs = Array.isArray(d.references) ? d.references : [];
  // Ref-list cross-source summary. Source badges live next to the
  // References heading (same pattern as License / Fields of Study /
  // Authors + affiliations) instead of in the metadata grid.
  const refsConfirmed = asInt(fm.refs_confirmed_by_ss);
  const refsSsOnly    = asInt(fm.refs_ss_only);
  const refsSsCount   = asInt(fm.refs_ss_count);
  const refsCrCount   = asInt(fm.refs_crossref_count);
  // Derived: refs Crossref returned but SS didn't confirm by DOI. This
  // includes both (a) refs where SS legitimately doesn't have the paper
  // and (b) refs that have no DOI to compare on. UI splits those below.
  const refsCrOnly = (refsCrCount !== null && refsConfirmed !== null)
    ? refsCrCount - refsConfirmed : null;
  // Count of Crossref refs that have no DOI — those aren't comparable to
  // SS's DOI-keyed list. We say "not compared" rather than "crossref only"
  // so it doesn't read as "SS said no".
  const refsNoDoi = refs.filter(r => !r.doi || r.doi === "unknown").length;
  const refsSrcBadges = (fm.refs_source && fm.refs_source !== "none")
    ? ` <span class="prov">${fm.refs_source.split("+").map(s =>
        `<span class="prov-tag win">${escHtml(SRC_ABBR[s.trim()] || s.trim())}</span>`
      ).join("")}</span>`
    : "";
  // When SS returned zero references we don't show any cross-check
  // stats in the header — the Coverage table below already indicates
  // that SS provided no reference list, and every count would just be
  // "0 both / N Crossref only / 0 SS only" which reads as if SS
  // actively disagreed. Silence is the honest state here.
  const ssComparedRefs = refsSsCount !== null && refsSsCount > 0;
  const refsHeaderSuffix = ssComparedRefs
    ? ` <span class="muted" style="font-size:12px; font-weight:normal">${
        [
          refsConfirmed !== null ? `${refsConfirmed} both` : null,
          (refsCrOnly !== null && refsCrOnly - refsNoDoi > 0)
            ? `${refsCrOnly - refsNoDoi} Crossref only` : null,
          refsSsOnly !== null && refsSsOnly > 0 ? `${refsSsOnly} SS only` : null,
          refsNoDoi > 0 ? `${refsNoDoi} not compared (no DOI)` : null,
        ].filter(Boolean).join(" · ")
      }</span>`
    : "";
  // Per-ref source tagging — we know which Crossref refs are ALSO in
  // SS (from ss_confirmed_dois) and can render SS-only refs at the
  // bottom from ss_only_refs.
  const ssOnlyList = Array.isArray(fm.ss_only_refs) ? fm.ss_only_refs : [];
  // Per-reference source abbreviations. The server decides which
  // sources vouch for a reference and sends `sources`; the client used
  // to re-derive the Semantic Scholar half from frontmatter, which put
  // provenance logic in two places.
  const REF_SRC_ABBR = { crossref: "C", semanticscholar: "SS", pdf: "PDF", corpus: "IN" };
  // Per-ref source markers — use the same C/SS/OA abbreviation pills as
  // the field-provenance badges. Meaning: whichever letters appear
  // beside a ref, those sources confirmed it. Two letters = both agree.
  const refBadgeSS  = '<span class="prov-tag win">SS</span>';
  const wrapBadges  = (b) => b ? ` <span class="prov">${b}</span>` : "";

  const totalRefs = refs.length + ssOnlyList.length;
  const refsBlock = totalRefs ? `
    <div class="pd-refs">
      <h3 title="${escAttr(tt("section.references"))}">References (${totalRefs})${refsSrcBadges}${refsHeaderSuffix}</h3>
      <ol>${refs.map(r => {
        const hasDoi  = r.doi && r.doi !== "unknown";
        const doiLink = hasDoi
          ? `<a href="https://doi.org/${escAttr(r.doi)}" target="_blank">${escHtml(r.doi)}</a>`
          : "";
        // Trailing tag mirrors the MD format:
        //   ` — DOI: <link> [extracted-badge?]`   when we have a DOI
        //   ` — <kind>`                            when no DOI but detected kind
        //   ` — no DOI`                            when neither
        const extractedBadge = r.extracted
          ? ' <span class="muted" style="font-size:11px">(extracted)</span>'
          : "";
        let trail;
        if (hasDoi)       trail = ` — ${doiLink}${extractedBadge}`;
        else if (r.kind)  trail = ` <span class="muted">— ${escHtml(r.kind)}</span>`;
        else              trail = ' <span class="muted">— no DOI</span>';
        // Source badges, straight from the server's `sources` list.
        // Whichever letters appear beside a reference, those sources
        // vouch for it: C = Crossref, SS = Semantic Scholar,
        // PDF = read off this paper's own reference list,
        // IN = labelled from the cited paper's summary (the deposit
        // carried a DOI and nothing else).
        const srcs = Array.isArray(r.sources) ? r.sources : [];
        const srcTag = srcs.length
          ? wrapBadges(srcs.map(s =>
              `<span class="prov-tag win">${escHtml(REF_SRC_ABBR[s] || s)}</span>`).join(""))
          : "";
        // In-corpus link: this reference resolves (by DOI) to another
        // paper you already have. Uses the same data-open-paper
        // delegation as the author / journal / institution panes.
        const inCorpus = r.linked_slug
          ? ` <a href="#" class="ref-incorpus" data-open-paper="${escAttr(r.linked_slug)}"
                >In corpus: ${escHtml(r.linked_slug)}</a>`
          : "";
        if (!r.text) return `<li>${(doiLink || '<span class="muted">(no metadata)</span>')}${inCorpus}${srcTag}</li>`;
        return `<li>${escHtml(r.text)}${trail}${inCorpus}${srcTag}</li>`;
      }).join("")}${ssOnlyList.map(r => {
        const doi   = (r.doi || "").toString();
        const title = (r.title || "").toString();
        const year  = r.year || "";
        const doiLink = doi
          ? `<a href="https://doi.org/${escAttr(doi)}" target="_blank">${escHtml(doi)}</a>`
          : "";
        const label = title
          ? `<strong>[${year ? escHtml(String(year)) + " " : ""}${escHtml(title)}]</strong>`
          : "";
        const trailer = doiLink ? ` — ${doiLink}` : "";
        return `<li>${label}${trailer}${wrapBadges(refBadgeSS)}</li>`;
      }).join("")}
      </ol>
    </div>
  ` : `
    <div class="pd-refs">
      <h3 title="${escAttr(tt("section.references"))}">References${refsSrcBadges}</h3>
      <p class="muted">No references available.</p>
    </div>
  `;

  const pdfLink = d.pdf_url
    ? `<a href="${escAttr(d.pdf_url)}" target="_blank" class="btn ghost" title="${escAttr(tt("btn.open_pdf"))}">Open PDF ↗</a>`
    : "";
  const oaLink = fm.open_access_pdf_url
    ? `<a href="${escAttr(fm.open_access_pdf_url)}" target="_blank" class="btn" title="${escAttr(tt("btn.open_free_pdf"))}">Open free PDF ↗${fm.open_access_pdf_status ? ` <span class="muted">(${escHtml(fm.open_access_pdf_status)})</span>` : ""}</a>`
    : "";
  const bibtexBtn = fm.bibtex
    ? `<button class="btn" id="btn-copy-bibtex" data-slug="${escAttr(d.slug)}" title="${escAttr(tt("btn.copy_bibtex"))}">Copy BibTeX</button>`
    : "";

  // Retraction banner — prominent at the top. Composes Crossref's
  // update_to entries (retraction notice DOI + label) with OA's
  // retraction_notice text when present.
  let retractionBanner = "";
  if (fm.retracted || fm.retraction_notice) {
    const updates = Array.isArray(fm.update_to) ? fm.update_to : [];
    const retraction = updates.find(u => (u.type || "").toLowerCase() === "retraction");
    const label = retraction ? (retraction.label || "See retraction notice") : "See retraction notice";
    const link = retraction && retraction.doi
      ? ` <a href="https://doi.org/${escAttr(retraction.doi)}" target="_blank">${escHtml(label)}</a>`
      : (retraction ? " " + escHtml(label) : "");
    const notice = fm.retraction_notice
      ? `<div class="retraction-notice">${escHtml(String(fm.retraction_notice))}</div>`
      : "";
    retractionBanner = `<div class="retracted-banner"><strong>Retracted.</strong>${link}${notice}</div>`;
  }

  // TLDR block — auto-generated 2-sentence summary from Semantic Scholar.
  // Shown ABOVE the abstract when present, since it's genuinely
  // scanning-useful and shorter.
  const tldrBlock = fm.tldr
    ? `<div class="pd-tldr"><h3 title="${escAttr(tt("section.tldr"))}">TLDR${provBadge("tldr")}</h3><p>${escHtml(fm.tldr)}</p></div>`
    : "";

  // Abstract block — always shown so absence is explicit.
  const abstractBlock = fm.abstract
    ? `<div class="pd-abstract"><h3 title="${escAttr(tt("section.abstract"))}">Abstract${provBadge("abstract")}</h3><p>${escHtml(fm.abstract)}</p></div>`
    : `<div class="pd-abstract"><h3 title="${escAttr(tt("section.abstract"))}">Abstract</h3><p class="muted">No abstract available.</p></div>`;

  // Fields of Study — SS's ML-classified topic hierarchy. Chips styled
  // to distinguish external-tag sources (MAG/DBLP-derived) from SS's
  // own ML model. Kept separate from Subjects (Crossref) — different
  // provenance, different semantics.
  const fosBlock = (Array.isArray(fm.s2_fields_of_study) && fm.s2_fields_of_study.length)
    ? `<div class="pd-fos"><h3>Fields of Study${provBadge("s2_fields_of_study")}</h3><p>${
        fm.s2_fields_of_study.map(f => escHtml(f.category || "")).filter(Boolean).join(", ")
      }</p></div>`
    : "";

  // Subjects (Crossref publisher-declared) — plain comma-separated text.
  const subjectsBlock = (Array.isArray(fm.subjects) && fm.subjects.length)
    ? `<div class="pd-subjects"><h3 title="${escAttr(tt("section.subjects"))}">Subjects${provBadge("subjects")}</h3><p>${
        fm.subjects.map(escHtml).join(", ")
      }</p></div>`
    : "";

  // Topics — OA's ML-classified hierarchy (domain → field → subfield → topic).
  const topicsBlock = (Array.isArray(oaTopics) && oaTopics.length)
    ? `<div class="pd-fos"><h3 title="${escAttr(tt("section.topics"))}">Topics${provBadge("topics")}</h3><ul class="topics-list">${
        oaTopics.map(t => {
          const parts = [t.domain, t.field, t.subfield, t.topic].filter(Boolean).map(escHtml);
          const chain = parts.length
            ? `<span class="muted">${parts.slice(0, -1).join(" › ")}${parts.length > 1 ? " › " : ""}</span><strong>${parts[parts.length - 1]}</strong>`
            : "(unknown)";
          const score = t.score ? ` <span class="muted" style="font-size:11px">(${Number(t.score).toFixed(2)})</span>` : "";
          return `<li>${chain}${score}</li>`;
        }).join("")
      }</ul></div>`
    : "";

  // Keywords — OA-derived, plain comma-separated text.
  const keywordsBlock = (Array.isArray(oaKeywords) && oaKeywords.length)
    ? `<div class="pd-fos"><h3 title="${escAttr(tt("section.keywords"))}">Keywords${provBadge("keywords")}</h3><p>${
        oaKeywords.map(k => escHtml(k.name || "")).filter(Boolean).join(", ")
      }</p></div>`
    : "";

  // OA locations (all known copies across sources — publisher paywall
  // included, so this list is not exclusively "OA"). Renamed the
  // section to "Locations" to match reality, plus per-row indication of
  // whether each URL is actually open-access or paywalled.
  //
  // OA status ("closed" / "gold" / "green" etc.) was rendered raw in
  // the header — meaningless to anyone who hasn't read the OpenAlex
  // taxonomy. Now expanded to a human-readable phrase and tooltipped
  // via oa.status.<key> keys in tooltips.default.js.
  const OA_STATUS_LABEL = {
    gold:    "open (gold)",
    green:   "open (green)",
    hybrid:  "open (hybrid)",
    bronze:  "free to read (bronze)",
    diamond: "open (diamond)",
    closed:  "paywalled",
  };
  const statusRaw = (fm.oa_status || "").toLowerCase();
  const statusText = OA_STATUS_LABEL[statusRaw] || statusRaw;
  const statusTt = tt(`oa.status.${statusRaw}`) || tt("oa.status.unknown");
  const oaLocationsBlock = (Array.isArray(oaLocations) && oaLocations.length)
    ? `<div class="pd-license"><h3 title="${escAttr(tt("section.oa_locations"))}">Locations${provBadge("oa_locations")}${
        statusText ? ` <span class="muted" style="font-weight:normal; text-transform:none" title="${escAttr(statusTt)}">— ${escHtml(statusText)}</span>` : ""
      }</h3><ul>${
        oaLocations.map(loc => {
          const label = loc.source_name || loc.host_org || loc.url;
          const meta = [];
          // Access marker first so it's immediately visible.
          meta.push(loc.is_oa ? "open" : "paywall");
          if (loc.version)     meta.push(escHtml(loc.version));
          if (loc.source_type) meta.push(escHtml(loc.source_type));
          if (loc.pdf)         meta.push("PDF");
          const trail = ` <span class="muted">— ${meta.join(" · ")}</span>`;
          return `<li><a href="${escAttr(loc.url)}" target="_blank">${escHtml(label)}</a>${trail}</li>`;
        }).join("")
      }</ul></div>`
    : "";

  // Versions across sources (preprint → accepted → published chain)
  const versionsBlock = (Array.isArray(oaVersions) && oaVersions.length)
    ? `<div class="pd-license"><h3 title="${escAttr(tt("section.versions"))}">Versions${provBadge("versions")}</h3><ul>${
        oaVersions.map(v => `<li><a href="${escAttr(v.url)}" target="_blank">${escHtml(v.source_name || v.url)}</a> <span class="muted">— ${escHtml(v.version)}</span></li>`).join("")
      }</ul></div>`
    : "";

  // Content assertions block (Crossref) — publisher-declared claims
  // like "peer-reviewed" or "open-access". Rendered as a small list.
  const assertionsBlock = (Array.isArray(contentAssertions) && contentAssertions.length)
    ? `<div class="pd-license"><h3 title="${escAttr(tt("section.assertions"))}">Content assertions${provBadge("content_assertions")}</h3><ul>${
        contentAssertions.map(a => {
          const label = escHtml((a && (a.name || "")).trim() || "(unlabeled)");
          const val   = a && a.value ? ` <span class="muted">— ${escHtml(a.value)}</span>` : "";
          const link  = a && a.url ? ` <a href="${escAttr(a.url)}" target="_blank">↗</a>` : "";
          const grp   = a && a.group ? ` <span class="muted">[${escHtml(a.group)}]</span>` : "";
          return `<li>${label}${val}${grp}${link}</li>`;
        }).join("")
      }</ul></div>`
    : "";

  // Citation counts by year — simple horizontal bar chart via CSS.
  const cbyBlock = (Array.isArray(oaCountsByYear) && oaCountsByYear.length)
    ? (() => {
        const maxC = Math.max(1, ...oaCountsByYear.map(e => e.count || 0));
        const bars = oaCountsByYear.map(e => {
          const pct = ((e.count || 0) / maxC * 100).toFixed(1);
          return `<div class="cby-row"><span class="cby-year">${escHtml(String(e.year))}</span><span class="cby-bar" style="width:${pct}%"></span><span class="cby-count">${escHtml(String(e.count || 0))}</span></div>`;
        }).join("");
        return `<div class="pd-fos"><h3 title="${escAttr(tt("section.cby"))}">Citations by year${provBadge("counts_by_year")}</h3><div class="cby-chart">${bars}</div></div>`;
      })()
    : "";

  // In-corpus connections — papers THIS paper cites, and papers that
  // cite it, restricted to papers you actually have. Both directions
  // come from the server's citation index (DOI-matched); neither is
  // stored on disk, so they stay correct as the corpus grows.
  //
  // Titles are resolved from `state.papers` (already loaded for the
  // sidebar) rather than fetched again — the server sends slugs, which
  // are the identity; the title is presentation.
  // Markup lives in src/corpus-links.js so its empty states are
  // testable. Titles are resolved from `state.papers` (already loaded
  // for the sidebar) — the server sends slugs, which are the identity;
  // the title is presentation.
  const corpusLinksBlock = CorpusLinks.render({
    cites:     d.cites,
    citedBy:   d.cited_by,
    refCounts: d.ref_counts,
    bridges:   d.bridges,
    hasDoi:    !isUnk(fm.doi),
    titleFor:  (slug) => {
      const p = (state.papers || []).find(x => x.slug === slug);
      const t = p && p.title && p.title !== "unknown" ? p.title : "";
      return t || slug;
    },
  });

  // Funding block
  const funderBlock = (Array.isArray(fm.funder) && fm.funder.length)
    ? `<div class="pd-funder"><h3 title="${escAttr(tt("section.funder"))}">Funding${provBadge("funder")}</h3><ul>${
        fm.funder.map(f => {
          const awards = Array.isArray(f.awards) && f.awards.length
            ? ` <span class="muted">— awards: ${f.awards.map(escHtml).join(", ")}</span>`
            : "";
          const doiLink = f.doi && f.doi !== "unknown"
            ? ` <span class="muted">(<a href="https://doi.org/${escAttr(f.doi)}" target="_blank">${escHtml(f.doi)}</a>)</span>`
            : "";
          return `<li><strong>${escHtml(f.name || "unknown")}</strong>${doiLink}${awards}</li>`;
        }).join("")
      }</ul></div>`
    : "";

  // License block — dedupe on URL first (Elsevier deposits a lot of
  // near-duplicate STM policy URLs). URL is the primary link text
  // (opaque `tdm` / `stm-asf` type strings are unhelpful as link labels);
  // the type gets a small trailing tag. Adjacent update_policy (Crossmark)
  // URL surfaces at the end when present.
  const licenseDedup = [];
  const seenLicUrls = new Set();
  for (const l of (Array.isArray(fm.license) ? fm.license : [])) {
    const url = (l && l.url || "").trim();
    if (!url || seenLicUrls.has(url)) continue;
    seenLicUrls.add(url);
    licenseDedup.push(l);
  }
  const licenseBlock = (licenseDedup.length || fm.update_policy)
    ? `<div class="pd-license"><h3>License${provBadge("license")}</h3>${
        licenseDedup.length ? `<ul>${
          licenseDedup.map(l => {
            const type = (l.type || "unspecified");
            const delay = Number(l.delay_days || 0);
            const embargo = delay > 0 ? ` <span class="muted">(embargo: ${delay} day${delay === 1 ? "" : "s"})</span>` : "";
            return `<li><a href="${escAttr(l.url)}" target="_blank">${escHtml(l.url)}</a> <span class="muted">— ${escHtml(type)}</span>${embargo}</li>`;
          }).join("")
        }</ul>` : ""
      }${fm.update_policy
        ? `<p class="muted" style="margin-top:8px">Update policy (Crossmark): <a href="${escAttr(fm.update_policy)}" target="_blank">${escHtml(fm.update_policy)}</a></p>`
        : ""
      }</div>`
    : "";

  // Header timestamp — all fields refresh together on extract, so one
  // "Last updated" line at the top covers everything below (citation
  // counts, references, etc.). Uses last_extracted rather than
  // citation_count_as_of because they're always the same instant
  // (both are stamped in render_frontmatter's `now`).
  const updatedLine = fm.last_extracted
    ? `<div class="pd-updated"><span class="muted">Last updated: ${tsSpan(fm.last_extracted)}</span></div>`
    : "";

  // Coverage matrix — for every field Corpus tracks, which sources
  // COULD provide it (per their API schema) vs which sources actually
  // did for THIS paper. Answers "SS could have deposited this — did
  // it?" without the user having to guess from missing badges.
  //
  // "presence check" for each cell = the frontmatter field the source
  // would populate. null in the cell means the source doesn't track
  // this field at all (n/a).
  // Rows: [label, crossref key, ss key, openalex key, tooltip-key].
  //   null  = source doesn't track this field at all (—)
  //  "SKIP:<key>" = source has this but Corpus deliberately doesn't
  //                 extract it (⊘); <key> is the field it WOULD be
  //  "STORE:<name>" = kept in a per-paper store, not frontmatter;
  //                   ✓/✗ from d.stores[<name>] (papers_api.PAPER_STORES)
  //   other = fm key to check (✓ if present, ✗ if empty)
  // tests/test_coverage_rows.py holds this table to what
  // prefill_summary.render_frontmatter actually writes.
  const coverageRows = [
    // -------- Core bibliographic ------------------------------------
    ["Title",                        "title",            "title",              "title",              "coverage.row.title"],
    ["Year",                         "year",             "year",               "year",               "coverage.row.year"],
    ["Publisher / venue",            "publisher",        "publisher",          "publisher",          "coverage.row.publisher"],
    ["Publisher organization",       null,               null,                 "host_organization",  "coverage.row.host_organization"],
    ["Venue type",                   null,               "ss_venue_type",      "venue_type",         "coverage.row.venue_type"],
    ["Venue alternate names",        null,               "ss_venue_alternate_names", null,           "coverage.row.venue_alt"],
    ["Venue URL",                    null,               "ss_venue_url",       null,                 "coverage.row.venue_url"],
    ["Short journal name",           "SKIP:short_container_title",             null,                 null,                 "coverage.row.short_journal"],
    ["DOI",                          "doi",              "doi",                "doi",                "coverage.row.doi"],
    ["Volume",                       "volume",           "volume",             "volume",             "coverage.row.volume"],
    ["Issue",                        "issue",            null,                 "issue",              "coverage.row.issue"],
    ["Article #",                    "article_number",   null,                 null,                 "coverage.row.article_number"],
    ["Pages",                        "pages",            "pages",              "pages",              "coverage.row.pages"],
    ["Edition #",                    "edition_number",   null,                 null,                 "coverage.row.edition"],
    ["Chapter #",                    "chapter_number",   null,                 null,                 "coverage.row.chapter"],
    ["Journal issue date",           "journal_issue_date", null,               null,                 "coverage.row.journal_issue_date"],
    ["Language",                     "language",         null,                 "language",           "coverage.row.language"],
    ["ISSN",                         "issn",             "issn",               "issn",               "coverage.row.issn"],
    ["ISBN",                         "isbn",             null,                 null,                 "coverage.row.isbn"],
    ["Alternative IDs",              "alternative_ids",  "alternative_ids",    "alternative_ids",    "coverage.row.alternative_ids"],
    // -------- Authors -----------------------------------------------
    ["Authors (structured)",         "authors_full",     null,                 "oa_authors",         "coverage.row.authors_structured"],
    ["Author sequence / position",   "authors_detailed", null,                 "oa_authors",         "coverage.row.author_position"],
    ["ORCID per author",             "authors_detailed", "_ss_authors_raw",    "oa_authors",         "coverage.row.orcid_per_author"],
    ["Corresponding author flag",    null,               null,                 "oa_authors",         "coverage.row.corresponding"],
    ["Institution ROR / country",    null,               null,                 "oa_authors",         "coverage.row.inst_ror"],
    ["Raw affiliation strings",      null,               "_ss_authors_raw",    "oa_authors",         "coverage.row.raw_affiliations"],
    ["Author h-index / papers",      null,               "_ss_authors_raw",    null,                 "coverage.row.author_hindex"],
    // -------- Content -----------------------------------------------
    ["Abstract",                     "abstract",         "abstract",           "abstract",           "coverage.row.abstract"],
    ["Subjects (publisher-declared)","subjects",         null,                 null,                 "coverage.row.subjects"],
    ["Fields of study (ML tags)",    null,               "s2_fields_of_study", null,                 "coverage.row.fos"],
    ["Topics (hierarchical)",        null,               null,                 "topics",             "coverage.row.topics"],
    ["Keywords",                     null,               null,                 "keywords",           "coverage.row.keywords"],
    ["Content assertions",           "content_assertions", null,               null,                 "coverage.row.assertions"],
    // -------- Classification ----------------------------------------
    ["Kind (article/book/…)",        "kind",             "kind",               "kind",               "coverage.row.kind"],
    ["Paper type (empirical/review)",null,               "paper_type",         null,                 "coverage.row.paper_type"],
    ["Publication types",            null,               "publication_types",  null,                 "coverage.row.publication_types"],
    // -------- Metrics -----------------------------------------------
    ["Citation count",               "citation_count",   "citation_count_ss",  "citation_count_oa",  "coverage.row.citation_count"],
    ["Citations by year",            null,               null,                 "counts_by_year",     "coverage.row.counts_by_year"],
    ["FWCI (field-weighted impact)", null,               null,                 "fwci",               "coverage.row.fwci"],
    ["References count",             "references_count", "references_count",   "references_count",   "coverage.row.references_count"],
    ["Reference list (per-ref data)","refs_crossref_count", "refs_ss_count",   "SKIP:refs_oa_count",               "coverage.row.reference_list"],
    ["List of citing papers",        null,               "SKIP:citers_ss",     "STORE:citers",               "coverage.row.list_of_citing"],
    ["Semantically related papers",  null,               "SKIP:related_ss",    "SKIP:related_oa",               "coverage.row.related_papers"],
    // -------- SS-unique content -------------------------------------
    ["TLDR (auto-summary)",          null,               "tldr",               null,                 "coverage.row.tldr"],
    ["Embedding (SPECTER2)",         null,               "embedding_model",    null,                 "coverage.row.embedding"],
    ["BibTeX",                       null,               "bibtex",             null,                 "coverage.row.bibtex"],
    // -------- Access / OA -------------------------------------------
    ["Open Access PDF link",         null,               "open_access_pdf_url","oa_locations",       "coverage.row.oa_pdf"],
    ["OA status (gold/green/…)",     null,               null,                 "oa_status",          "coverage.row.oa_status"],
    ["Full-text availability",       null,               null,                 "has_fulltext",       "coverage.row.fulltext"],
    ["Paratext flag",                null,               null,                 "is_paratext",        "coverage.row.paratext"],
    ["APC paid / listed",            null,               null,                 "SKIP:apc",               "coverage.row.apc"],
    // -------- Funding / License -------------------------------------
    ["Funder",                       "funder",           null,                 "funder",             "coverage.row.funder"],
    ["License",                      "license",          null,                 null,                 "coverage.row.license"],
    // -------- Retraction --------------------------------------------
    ["Retraction flag",              "update_to",        null,                 "retracted",          "coverage.row.retraction_flag"],
    ["Retraction notice text",       null,               null,                 "retraction_notice",  "coverage.row.retraction_notice"],
    ["Update policy (Crossmark)",    "update_policy",    null,                 null,                 "coverage.row.update_policy"],
    // -------- Timestamps --------------------------------------------
    ["Deposited timestamp",          "deposited_at",     null,                 null,                 "coverage.row.deposited"],
    ["Indexed timestamp",            "indexed_at",       null,                 null,                 "coverage.row.indexed"],
    ["OA record created",            null,               null,                 "oa_created_date",    "coverage.row.oa_created"],
    ["OA record updated",            null,               null,                 "oa_updated_date",    "coverage.row.oa_updated"],
    // -------- Other -------------------------------------------------
    ["Publisher direct link[]",      "SKIP:publisher_links",             null,                 null,                 "coverage.row.publisher_link"],
    ["Crossmark content-domain",     "SKIP:crossmark_domain",             null,                 null,                 "coverage.row.crossmark_content"],
    ["Crossref member ID",           "SKIP:crossref_member",             null,                 null,                 "coverage.row.crossref_member"],
    ["SS OA PDF disclaimer",         null,               "SKIP:ss_oa_disclaimer",               null,                 "coverage.row.ss_disclaimer"],
    ["SDG classification",           null,               null,                 "SKIP:sdgs",               "coverage.row.sdg"],
    ["MeSH terms",                   null,               null,                 "SKIP:mesh",               "coverage.row.mesh"],
    ["Datasets",                     null,               null,                 "SKIP:datasets",               "coverage.row.datasets"],
    ["Indexed-in databases",         null,               null,                 "SKIP:indexed_in",               "coverage.row.indexed_in"],
    ["Versions across sources",      null,               null,                 "versions",               "coverage.row.versions"],
  ];
  // Four-state cell: true (✓) / false (✗) / "skip" (⊘) / null (—).
  //  ✓ present     — source returned + we captured
  //  ✗ absent      — source could return this + we extract that field
  //                  + this paper didn't have it
  //  ⊘ skipped     — source has this field, Corpus deliberately doesn't
  //                  extract it (per Jack's audit)
  //  — n/a         — source doesn't track this field at all
  //
  // For MERGED fields (same key checked across all three columns), a
  // single truthy value would mark all three ✓ even when only one
  // source actually contributed. Consult <field>_from to see which
  // sources really supplied a value; only mark ✓ for those.
  // `present` resolves a frontmatter key to one of the values
  // `Coverage.cell` renders: true (✓), false (✗), "skip" (⊘), null (—).
  // Rules are paper-specific — books/preprints have different truthy
  // shapes than authors/institutions do — so this stays local; only
  // the rendering primitives are shared.
  const present = (key, srcAbbr) => {
    if (!key) return null;
    if (key.startsWith("SKIP:")) return "skip";
    if (key.startsWith("STORE:")) return !!(d.stores || {})[key.slice(6)];
    const v = fm[key];
    const hasValue = (val) => {
      if (val == null || val === "") return false;
      if (Array.isArray(val))       return val.length > 0;
      if (typeof val === "number")  return val > 0;
      if (typeof val === "boolean") return val === true;
      if (typeof val === "string")  return val.trim() !== "" && val !== "unknown" && val !== "false";
      return true;
    };
    if (!hasValue(v)) return false;
    // If this field has provenance, restrict the ✓ to columns whose
    // source actually contributed.
    const prov = fm[`${key}_from`];
    if (srcAbbr && Array.isArray(prov) && prov.length) {
      return Coverage.inSource(prov, srcAbbr);
    }
    return true;
  };
  const coverageBlock = Coverage.renderTable(
    coverageRows.map(([label, cr, ss, oa, ttKey]) => [
      label, present(cr, "C"), present(ss, "SS"), present(oa, "OA"), ttKey,
    ])
  );

  // Source-file line — always visible under the title so it's obvious
  // which PDF this record points at, especially when extraction failed
  // and the header shows just the slug. pdf_link comes straight from
  // the frontmatter (e.g., "papers/stachenfeld-2017.pdf"). Both links
  // reveal-in-Finder via the same handler; `data-reveal-kind` routes
  // to the right target (default pdf, or the summary MD).
  const pdfPathLine = fm.pdf_link
    ? `<div class="pd-source-file"><span class="muted">Source file: <a href="#" class="pd-source-file-link" data-reveal-slug="${escAttr(d.slug)}" data-reveal-kind="pdf" title="${escAttr(tt("btn.reveal_in_finder"))}"><code>${escHtml(fm.pdf_link)}</code></a></span></div>`
    : "";
  const summaryPathLine = `<div class="pd-source-file"><span class="muted">Summary: <a href="#" class="pd-source-file-link" data-reveal-slug="${escAttr(d.slug)}" data-reveal-kind="summary" title="${escAttr(tt("btn.reveal_in_finder"))}"><code>summaries/${escHtml(d.slug)}.md</code></a></span></div>`;
  // When extraction failed (title still "unknown"), surface a
  // prominent hint above the meta grid so it's obvious what's wrong
  // and what the user should do next.
  const extractionFailedBanner = isUnk(fm.title) ? `
    <div class="pd-extract-fail">
      <strong>Metadata extraction didn't find a DOI for this PDF.</strong>
      Corpus stored it under the filename-derived slug <code>${escHtml(d.slug)}</code>.
      Try clicking Re-extract, or open the PDF and paste its DOI into the DOI row below.
    </div>` : "";

  // Subtabs (Paper info | PDF). PDF pane is only offered when the PDF
  // is on disk — pdf_url is set in /api/paper/<slug> only if
  // papers/<slug>.pdf exists.
  const hasPdf = Boolean(d.pdf_url) && !panel;
  const activeInfo = (state.paperSubtab === "pdf" && hasPdf) ? "" : "active";
  const activePdf  = (state.paperSubtab === "pdf" && hasPdf) ? "active" : "";

  const infoPaneHtml = `
    <div class="pd-subpane pd-subpane-info" ${activePdf ? "hidden" : ""}>
      ${tldrBlock}
      ${abstractBlock}
      <dl class="pd-meta">
        ${metaRows.map(([k, v]) => `<dt title="${escAttr(tt(META_TT_KEYS[k] || ""))}">${escHtml(k)}</dt><dd>${v}</dd>`).join("")}
      </dl>
      ${corpusLinksBlock}
      ${subjectsBlock}
      ${fosBlock}
      ${topicsBlock}
      ${keywordsBlock}
      ${affilBlock}
      ${funderBlock}
      ${licenseBlock}
      ${assertionsBlock}
      ${oaLocationsBlock}
      ${versionsBlock}
      ${cbyBlock}
      ${refsBlock}
      <div id="pd-citers-host"></div>
      ${coverageBlock}
    </div>`;

  host.innerHTML = `
    ${retractionBanner}
    ${extractionFailedBanner}
    <div class="pd-head">
      <div class="pd-head-titles">
        <h1>${escHtml(displayTitle)}</h1>
        <div class="pd-authors">${escHtml(authorLine)}</div>
        ${pdfPathLine}
        ${summaryPathLine}
        ${updatedLine}
      </div>
      <div class="pd-head-actions">
        ${panel ? "" : pdfLink}
        ${hasPdf ? `<button class="btn" id="btn-pop-out" data-slug="${escAttr(d.slug)}" title="Open PDF in a separate window. Highlights and notes still save.">Pop out ⧉</button>` : ""}
        ${oaLink}
        ${bibtexBtn}
        ${panel ? "" : `<button class="btn" id="btn-add-to-project" data-slug="${escAttr(d.slug)}">Add to project</button>
        <button class="btn" id="btn-reextract" data-slug="${escAttr(d.slug)}" title="${escAttr(tt("btn.reextract"))}">Re-extract</button>`}
      </div>
    </div>
    ${(() => {
      // In a panel the host view owns tabs and PDF — info only.
      if (panel) return infoPaneHtml;
      // Is THIS window's copy of this paper currently popped out to a
      // separate window? If so, replace the whole subtabs+subpanes area
      // with one unified placeholder: subtabs disabled, both info and
      // PDF locked behind the same "open elsewhere" panel.
      if (isDetachedElsewhere("paper", d.slug)) return detachedPlaceholderHtml("paper", d.slug);
      return `
    <nav class="pd-subtabs">
      <button class="pd-subtab ${activeInfo}" data-subtab="info">Paper info</button>
      ${hasPdf ? `<button class="pd-subtab ${activePdf}" data-subtab="pdf">PDF</button>` : ""}
    </nav>
    ${infoPaneHtml}
    ${hasPdf ? pdfPaneHtml(d.pdf_url, displayTitle, { hidden: Boolean(activeInfo) }) : ""}`;
    })()}
  `;

  // Wire buttons that were just rendered — found inside `host` only, so
  // two hosts on one page cannot grab each other's buttons.
  const q = (sel) => host.querySelector(sel);
  const btn = q("#btn-reextract");
  if (btn) btn.addEventListener("click", () => reExtract(btn.dataset.slug));
  const bridgeBtn = q(".pd-bridge-btn");
  if (bridgeBtn) bridgeBtn.addEventListener("click", () => findBridges(bridgeBtn, d.slug, opts.reload));
  const bib = q("#btn-copy-bibtex");
  if (bib) bib.addEventListener("click", () => copyBibtex(fm.bibtex || ""));
  const popOut = q("#btn-pop-out");
  if (popOut) popOut.addEventListener("click", () => openDetached("paper", popOut.dataset.slug));
  // Citers load separately from /api/paper/<slug>: the store can be
  // megabytes for a famous paper, and this pane renders on every click.
  const citersHost = q("#pd-citers-host");
  if (citersHost) Citers.load(d.slug, !isUnk(fm.doi), citersHost);
  // Project membership belongs to projects.js — this pane only opens it.
  // Resolved at click time, like every other cross-module global here,
  // so script load order cannot break it.
  const addProj = q("#btn-add-to-project");
  if (addProj) addProj.addEventListener("click", () =>
    window.ProjectMembership.openFor("paper", addProj.dataset.slug));
  // "Bring to front" / "Close that window" are wired once, in app.js, for
  // papers and notes alike (see detachedPlaceholderHtml).
  // Subtab toggle — swap visibility of the two panes without reloading.
  host.querySelectorAll(".pd-subtab").forEach(t => {
    t.addEventListener("click", () => {
      const target = t.dataset.subtab;
      if (target === state.paperSubtab) return;
      state.paperSubtab = target;
      host.querySelectorAll(".pd-subtab").forEach(tt =>
        tt.classList.toggle("active", tt.dataset.subtab === target));
      const infoPane = host.querySelector(".pd-subpane-info");
      const pdfPane  = host.querySelector(".pd-subpane-pdf");
      if (infoPane) infoPane.hidden = (target !== "info");
      if (pdfPane)  pdfPane.hidden  = (target !== "pdf");
    });
  });

}

async function copyBibtex(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast("BibTeX copied", "ok");
  } catch (e) {
    toast("copy failed: " + e.message, "err");
  }
}

// Bridge search. ~40s against a 56-paper corpus, because it resolves
// every paper to OpenAlex and fetches each one's citer list. That is
// far too long to leave a button looking idle, so it is disabled and
// relabelled for the duration — otherwise the first thing a user does
// is press it again.
async function findBridges(btn, slug, reload) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Searching…";
  // Same progress channel the import uses. Before this the button just
  // said "Searching…" for ~40s with no indication of which of the four
  // phases it was in.
  Progress.watch();
  try {
    const res = await api("/api/bridges/compute", { method: "POST" });
    const t = (res && res.totals) || {};
    // Report what was NOT reachable as well as what was. A partial
    // network failure and a genuinely sparse corpus produce the same
    // small number otherwise.
    // An INCOMPLETE result and a sparse corpus produce similar numbers,
    // so say which. A dropped OpenAlex chunk is up to 50 papers missing
    // from the graph, and on 2026-09-21 that happened without anything
    // reporting it.
    const notes = [];
    if (t.papers_unresolved) notes.push(`${t.papers_unresolved} paper(s) not in OpenAlex`);
    if (t.lookup_failures)   notes.push(`${t.lookup_failures} paper(s) LOST to failed lookups`);
    if (t.citers_failed)     notes.push(`${t.citers_failed} citation lookup(s) failed`);
    const incomplete = t.complete === false;
    toast((incomplete ? `Incomplete: ${t.bridges || 0} bridges` : `${t.bridges || 0} bridges found`)
          + (notes.length ? ` (${notes.join("; ")})` : "")
          + (incomplete ? " — search again for a full result" : ""),
          incomplete ? "err" : "ok");
    // Re-render wherever the button was clicked (main pane or a note's
    // panel); the main pane is only the fallback.
    await (reload ? reload() : loadPaperDetail(slug));
  } catch (e) {
    btn.disabled = false;
    btn.textContent = label;
    toast("bridge search failed: " + e.message, "err");
  }
}

async function reExtract(slug) {
  toast("re-extracting…");
  try {
    const res = await api(`/api/paper/${encodeURIComponent(slug)}/re-extract`, { method: "POST" });
    // Server renames PDF + summary to the canonical slug when the newly-
    // resolved metadata differs from the current slug. Update selection
    // to the new slug so the detail pane doesn't 404.
    const nextSlug = (res && res.slug) || slug;
    state.selectedSlug = nextSlug;
    toast(res && res.renamed ? `renamed → ${nextSlug}` : "re-extracted", "ok");
    await loadPapers();
    await loadPaperDetail(nextSlug);
  } catch (e) {
    toast("re-extract failed: " + e.message, "err");
  }
}

