// Corpus — in-corpus citation connections block.
//
// Renders the two directions of intra-corpus citation links for one
// paper: papers it cites, and papers that cite it. Data comes from
// `/api/paper/<slug>` (`cites` / `cited_by` / `ref_counts`), computed
// by python/citations.py.
//
// Split out of paper-detail.js on 2026-08-25 so the empty states are
// directly testable — the bug that prompted it was invisible precisely
// because it only showed up when a list was empty.
//
// Depends at call-time on `escHtml` / `escAttr` from app.js.

window.CorpusLinks = (function () {

  // Every empty state says WHICH corpus it means. "None" alone reads as
  // "this paper has never been cited", which is a much bigger claim than
  // "no paper in your corpus cites it".
  const EMPTY_CITES    = "No papers in this corpus.";
  const EMPTY_CITED_BY = "No papers in this corpus cite it.";

  function _list(slugs, titleFor) {
    return `<ul class="pd-links-list">${slugs.map(s =>
      `<li><a href="#" data-open-paper="${escAttr(s)}">${escHtml(titleFor(s))}</a>` +
      `<span class="muted pd-links-slug">${escHtml(s)}</span></li>`
    ).join("")}</ul>`;
  }

  function _side(label, slugs, emptyText, titleFor) {
    const n = slugs.length;
    const heading = `<h4>${escHtml(label)} (${n})</h4>`;
    const body = n
      ? _list(slugs, titleFor)
      : `<p class="muted pd-links-empty">${escHtml(emptyText)}</p>`;
    return heading + body;
  }

  // Why a reference count can look wrong to the user, explained inline
  // rather than left to be inferred. Three different situations produce
  // "few links", and they mean different things:
  //   * references with no DOI    -> a metadata gap
  //   * DOIs not matching anything -> papers not owned
  //   * no reference list at all   -> publisher deposited none
  function _refsNote(rc) {
    if (!rc || !rc.total) {
      return `<p class="muted pd-links-note">No reference list for this paper.</p>`;
    }
    const total = rc.total || 0;
    const withDoi = rc.with_doi || 0;
    const linked = rc.linked || 0;
    const noDoi = total - withDoi;
    const bits = [`${linked} of ${withDoi} references with a DOI match a paper in this corpus`];
    if (noDoi > 0) {
      bits.push(`${noDoi} of ${total} have no DOI and cannot be matched`);
    }
    return `<p class="muted pd-links-note">${escHtml(bits.join(" · "))}.</p>`;
  }

  /**
   * Build the connections block.
   *
   * opts:
   *   cites      [slug]  papers this one cites (inside the corpus)
   *   citedBy    [slug]  papers citing this one (inside the corpus)
   *   refCounts  {total, with_doi, linked}
   *   hasDoi     bool    whether THIS paper has a resolvable DOI
   *   titleFor   fn(slug) -> display title
   *
   * Always returns markup. The block is never conditionally omitted:
   * an absent section is indistinguishable from a missing feature, and
   * "nothing cites this yet" is a real answer the user asked for.
   */
  // ---- Bridges: indirect connections via a paper NOT in the corpus ----
  //
  // Three states that must never be confused, because they look the
  // same and mean completely different things:
  //   not computed yet -> the user has not pressed the button
  //   computed, none   -> we looked and there is no known path
  //   stale            -> computed before the corpus changed
  const BRIDGE_UNCOMPUTED =
    "Not searched yet. Bridges are found through papers outside this " +
    "corpus, which needs a lookup.";
  const BRIDGE_NONE =
    "No indirect connections found to other papers in this corpus.";

  function _middle(m) {
    const bits = [];
    if (m.year) bits.push(String(m.year));
    if (typeof m.cited_by === "number") bits.push(`${m.cited_by} citations`);
    return `<li><span class="pd-bridge-mid">${escHtml(m.title || "Untitled")}</span>` +
           (bits.length ? `<span class="muted pd-bridge-meta">${escHtml(bits.join(" · "))}</span>` : "") +
           `</li>`;
  }

  function _bridgeRow(row, middles, titleFor) {
    const ms = (row.middles || []).map(id => middles[id]).filter(Boolean);
    const n = (row.middles || []).length;
    // The hop count is the headline: "2 hops" is the length of the
    // bridge, shown alongside the papers.
    const head =
      `<div class="pd-bridge-head">` +
      `<a href="#" data-open-paper="${escAttr(row.other)}">${escHtml(titleFor(row.other))}</a>` +
      `<span class="pd-bridge-hops">${escHtml(String(row.hops))} hops</span>` +
      `<span class="muted">via ${escHtml(String(n))} paper${n === 1 ? "" : "s"}</span>` +
      `</div>`;
    return `<li class="pd-bridge">${head}<ul class="pd-bridge-mids">${ms.map(_middle).join("")}</ul></li>`;
  }

  function _bridges(b, titleFor) {
    const o = b || {};
    const rows = Array.isArray(o.rows) ? o.rows : [];
    const middles = o.middles || {};
    const btn = `<button class="btn pd-bridge-btn" data-find-bridges="1">` +
                `${o.computed ? "Search again" : "Find bridges"}</button>`;
    let body;
    if (!o.computed)       body = `<p class="muted pd-links-empty">${escHtml(BRIDGE_UNCOMPUTED)}</p>`;
    else if (!rows.length) body = `<p class="muted pd-links-empty">${escHtml(BRIDGE_NONE)}</p>`;
    else                   body = `<ul class="pd-bridge-list">${rows.map(r => _bridgeRow(r, middles, titleFor)).join("")}</ul>`;
    const stamp = (o.computed && o.computed_at)
      ? `<p class="muted pd-links-note">Searched ${escHtml(String(o.computed_at).replace("T", " "))}.</p>`
      : "";
    return `<div class="pd-bridges"><h4>Bridges (${rows.length})${btn}</h4>${body}${stamp}</div>`;
  }

  function render(opts) {
    const o         = opts || {};
    const cites     = Array.isArray(o.cites) ? o.cites : [];
    const citedBy   = Array.isArray(o.citedBy) ? o.citedBy : [];
    const titleFor  = typeof o.titleFor === "function" ? o.titleFor : (s) => s;

    // A paper with no resolvable DOI can never be the target of a link,
    // because matching is DOI-only. Without this line its permanently
    // empty "Cited by" reads as a bug rather than a data gap.
    const noDoiNote = (!o.hasDoi && !citedBy.length)
      ? `<p class="muted pd-links-note">This paper has no DOI, so references to it cannot be matched.</p>`
      : "";

    return `
      <div class="pd-links">
        <h3>In-corpus connections</h3>
        ${_side("Cites", cites, EMPTY_CITES, titleFor)}
        ${_side("Cited by", citedBy, EMPTY_CITED_BY, titleFor)}
        ${noDoiNote}
        ${_bridges(o.bridges, titleFor)}
        ${_refsNote(o.refCounts)}
      </div>`;
  }

  return { render };
})();
