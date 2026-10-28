// Citers — every known work citing this paper, in the paper info panel.
//
// Jack, 2026-09-22: "implement a storage for the citers of each paper.
// integrate it into the info panel and have clear distinctions like for
// references about which citers are in the corpus."
//
// Two groups, always in this order:
//   * In your corpus — every one, linked with the SAME `ref-incorpus`
//     "In corpus: <slug>" marker the References list uses, so the
//     distinction reads identically in both places.
//   * Not in your corpus — paged, 50 at a time. The largest paper has
//     ~105k citers; rendering them all would freeze the pane.
//
// Fetching is a button, never automatic: see python/citers.py for the
// request cost. `render()` is pure so its states are testable.
//
// Relies at call time on app.js globals: api, escHtml, escAttr, toast,
// Progress.

window.Citers = (function () {
  "use strict";

  const PAGE = 50;

  function _fmtCount(n) {
    return (n == null || n === "" || n === "unknown") ? null : Number(n).toLocaleString();
  }

  function _rowHtml(c, inCorpus) {
    const year = c.year ? `${escHtml(String(c.year))} ` : "";
    const title = c.title ? escHtml(c.title) : '<span class="muted">(untitled)</span>';
    const doi = c.doi
      ? ` — <a href="https://doi.org/${escAttr(c.doi)}" target="_blank">${escHtml(c.doi)}</a>`
      : ' <span class="muted">— no DOI</span>';
    const mark = inCorpus
      ? ` <a href="#" class="ref-incorpus" data-open-paper="${escAttr(c.slug)}">In corpus: ${escHtml(c.slug)}</a>`
      : "";
    return `<li><strong>[${year}${title}]</strong>${doi}${mark}</li>`;
  }

  /** Markup for every state. `d` is the GET /citers response (or null
   *  while loading); `opts.hasDoi` / `opts.busy` drive the button. */
  function render(d, opts) {
    const o = opts || {};
    const head = (suffix) =>
      `<h3>Citers${suffix || ""}</h3>`;

    if (!d) return `<div class="pd-citers">${head()}<p class="muted">Loading…</p></div>`;

    if (d.status === "not_fetched") {
      if (!o.hasDoi) {
        return `<div class="pd-citers">${head()}
          <p class="muted">Needs a DOI to look up who cites this paper.</p></div>`;
      }
      const n = _fmtCount(d.citation_count);
      // Warn before a big fetch: 200 citers per request.
      const reqs = d.citation_count > 0 ? Math.ceil(d.citation_count / 200) : 0;
      const note = n
        ? `<p class="muted">About ${n} citations on record${reqs > 25
            ? ` — roughly ${reqs.toLocaleString()} OpenAlex requests to fetch`
            : ""}.</p>`
        : "";
      return `<div class="pd-citers">${head()}${note}
        <button class="btn" data-citers-fetch ${o.busy ? "disabled" : ""}>
          ${o.busy ? "Finding citers…" : "Find citers"}</button></div>`;
    }

    const stored = _fmtCount(d.stored_count) || "0";
    const partial = d.complete ? "" :
      ` <span class="muted">— partial: ${escHtml(stored)} of ${escHtml(_fmtCount(d.reported_count) || "?")} fetched before OpenAlex stopped answering</span>`;
    const when = d.fetched_at ? d.fetched_at.slice(0, 10) : "";
    const meta = `<p class="muted pd-citers-meta">OpenAlex · fetched ${escHtml(when)}${partial}
      <button class="btn ghost" data-citers-fetch ${o.busy ? "disabled" : ""}>
        ${o.busy ? "Refreshing…" : "Refresh"}</button></p>`;

    const inside = d.in_corpus || [];
    const outside = d.elsewhere || [];
    const insideHtml = inside.length
      ? `<ol class="pd-citers-in">${inside.map(c => _rowHtml(c, true)).join("")}</ol>`
      : `<p class="muted">None of this paper's citers are in your corpus.</p>`;
    const more = d.elsewhere_total > outside.length
      ? `<button class="btn ghost" data-citers-more>Show more (${(d.elsewhere_total - outside.length).toLocaleString()} left)</button>`
      : "";
    const outsideHtml = d.elsewhere_total
      ? `<ol class="pd-citers-out">${outside.map(c => _rowHtml(c, false)).join("")}</ol>${more}`
      : `<p class="muted">None outside your corpus.</p>`;

    return `<div class="pd-citers">${head(` (${escHtml(stored)})`)}${meta}
      <h4>In your corpus (${inside.length})</h4>${insideHtml}
      <h4>Not in your corpus (${(d.elsewhere_total || 0).toLocaleString()})</h4>${outsideHtml}
    </div>`;
  }

  // ---------- wiring ------------------------------------------------

  // One load at a time per pane; a stale response for a paper the user
  // has since left must not overwrite the one now showing.
  let _slug = null;
  let _data = null;
  let _busy = false;

  // The box to paint into. Passed by the renderer so it can be the note
  // panel's copy of the paper view as well as the main pane's; the id
  // lookup is only the fallback for a caller that passes none.
  let _hostEl = null;
  function _host() {
    return (_hostEl && _hostEl.isConnected) ? _hostEl : document.getElementById("pd-citers-host");
  }

  function _paint(hasDoi) {
    const h = _host();
    if (h) h.innerHTML = render(_data, { hasDoi, busy: _busy });
  }

  async function load(slug, hasDoi, host) {
    _hostEl = host || null;
    _slug = slug;
    _data = null;
    _paint(hasDoi);
    try {
      const d = await api(`/api/paper/${encodeURIComponent(slug)}/citers?limit=${PAGE}`);
      if (_slug !== slug) return;
      _data = d;
    } catch (e) {
      if (_slug !== slug) return;
      const h = _host();
      if (h) h.innerHTML = `<div class="pd-citers"><h3>Citers</h3>
        <p class="muted">Could not load citers: ${escHtml(e.message)}</p></div>`;
      return;
    }
    _paint(hasDoi);
    _wire(slug, hasDoi);
  }

  function _wire(slug, hasDoi) {
    const h = _host();
    if (!h) return;
    h.onclick = async (e) => {
      if (e.target.closest("[data-citers-fetch]")) {
        _busy = true; _paint(hasDoi);
        Progress.watch();
        try {
          await api(`/api/paper/${encodeURIComponent(slug)}/citers/fetch`, { method: "POST" });
        } catch (err) {
          toast("finding citers failed: " + err.message, "err");
        }
        _busy = false;
        if (_slug === slug) await load(slug, hasDoi, _hostEl);
        return;
      }
      if (e.target.closest("[data-citers-more]") && _data) {
        const off = (_data.elsewhere || []).length;
        try {
          const d = await api(`/api/paper/${encodeURIComponent(slug)}/citers?offset=${off}&limit=${PAGE}`);
          if (_slug !== slug) return;
          _data.elsewhere = (_data.elsewhere || []).concat(d.elsewhere || []);
          _paint(hasDoi);
        } catch (err) {
          toast("could not load more citers: " + err.message, "err");
        }
      }
    };
  }

  return { render, load };
})();
