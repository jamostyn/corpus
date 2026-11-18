// Shared citers of a note's papers — window.SharedCiters. EXPERIMENTAL.
//
// A note's "Shared citers" button lists the works that cite two or more
// of the papers the note links, and are not themselves linked: those in
// the corpus first (with the References list's in-corpus link), then the
// rest, each with its citation count. The server builds the list from
// stored citer lists (GET /api/note/<id>/shared-citers) and looks up only
// the counts; a linked paper without a list is named, with a button that
// fetches the missing lists.
//
// `render()` is pure so its states are testable. Relies at call time on
// app.js globals: api, escHtml, escAttr, toast, Progress.

window.SharedCiters = (function () {
  "use strict";

  // Fewer linked papers than this cannot share a citer. Mirrors
  // shared_citers.MIN_PAPERS; tests/test_shared_citers.py keeps them equal.
  const MIN_PAPERS = 2;
  const PAGE = 100;

  /** Distinct papers linked in a note body element (highlight links
   *  carry data-open-paper too, so they count as their paper). */
  function linkedCount(bodyEl) {
    if (!bodyEl) return 0;
    const slugs = new Set();
    bodyEl.querySelectorAll("a[data-open-paper]").forEach(a => slugs.add(a.getAttribute("data-open-paper")));
    return slugs.size;
  }

  function _plural(n, word) {
    return `${Number(n).toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
  }

  /** One work: title; then year · citations · DOI · in-corpus link;
   *  then which of the note's papers it cites. */
  function rowHtml(c) {
    const title = c.title ? escHtml(c.title) : '<span class="muted">(untitled)</span>';
    const meta = [];
    if (c.year) meta.push(escHtml(String(c.year)));
    if (c.cited_by_count != null) meta.push(_plural(c.cited_by_count, "citation"));
    meta.push(c.doi ? `<a href="https://doi.org/${escAttr(c.doi)}" target="_blank">${escHtml(c.doi)}</a>`
                    : '<span class="muted">no DOI</span>');
    const mark = c.slug
      ? ` <a href="#" class="ref-incorpus" data-open-paper="${escAttr(c.slug)}">In corpus: ${escHtml(c.slug)}</a>`
      : "";
    return `<li class="sc-item">
      <div class="sc-title">${title}</div>
      <div class="sc-meta">${meta.join(' <span class="sc-dot">·</span> ')}${mark}</div>
      <div class="sc-cites">Cites ${c.cites.length} of your papers: ${c.cites.map(escHtml).join(", ")}</div>
    </li>`;
  }

  /** Markup for the dialog body. `d` is the GET response, or null while
   *  loading; `opts.busy` is true while missing lists are fetched. */
  function render(d, opts) {
    const o = opts || {};
    if (!d) return `<p class="muted">Loading…</p>`;
    const papers = d.papers || [];
    const usable = papers.filter(p => p.status === "stored" || p.status === "partial");
    const missing = papers.filter(p => p.status === "not_fetched");
    const noDoi = papers.filter(p => p.status === "no_doi");
    const partial = papers.filter(p => p.status === "partial");

    const notes = [];
    if (missing.length) {
      notes.push(`<div class="sc-note"><span>No citer list yet: ${missing.map(p => escHtml(p.slug)).join(", ")}</span>
        <button class="btn" data-sc-fetch ${o.busy ? "disabled" : ""}>${o.busy ? "Finding citers…" : "Find citers"}</button></div>`);
    }
    if (noDoi.length) notes.push(`<div class="sc-note"><span>No DOI, so no citer list: ${noDoi.map(p => escHtml(p.slug)).join(", ")}</span></div>`);
    if (partial.length) notes.push(`<div class="sc-note"><span>Partial citer list: ${partial.map(p => escHtml(p.slug)).join(", ")}</span></div>`);
    if (d.counts_failed) notes.push(`<div class="sc-note"><span>Citation counts unavailable for ${_plural(d.counts_failed, "work")}.</span></div>`);
    const lines = [`<p class="sc-summary">Works citing ${MIN_PAPERS} or more of this note's ${_plural(papers.length, "linked paper")}, from ${_plural(usable.length, "stored citer list")}.</p>`];
    if (notes.length) lines.push(`<div class="sc-notes">${notes.join("")}</div>`);
    if (usable.length < MIN_PAPERS) {
      lines.push(`<p class="muted">Needs stored citer lists for at least ${MIN_PAPERS} papers.</p>`);
      return lines.join("");
    }

    const inside = d.in_corpus || [];
    const outside = d.elsewhere || [];
    const more = d.elsewhere_total > outside.length
      ? `<button class="btn ghost" data-sc-more>Show more (${(d.elsewhere_total - outside.length).toLocaleString()} left)</button>`
      : "";
    lines.push(`<h4 class="sc-group">In your corpus <span class="sc-count">${inside.length}</span></h4>`,
      inside.length ? `<ol class="sc-list">${inside.map(rowHtml).join("")}</ol>`
                    : `<p class="muted">None in your corpus.</p>`,
      `<h4 class="sc-group">Not in your corpus <span class="sc-count">${(d.elsewhere_total || 0).toLocaleString()}</span></h4>`,
      d.elsewhere_total ? `<ol class="sc-list">${outside.map(rowHtml).join("")}</ol>${more}`
                        : `<p class="muted">None outside your corpus.</p>`);
    return lines.join("");
  }

  async function open(noteId) {
    const url = `/api/note/${encodeURIComponent(noteId)}/shared-citers`;
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay shared-citers";
    overlay.innerHTML = `
      <div class="modal">
        <header class="modal-header">
          <h2>Shared citers <span class="sc-badge">Experimental</span></h2>
          <button class="btn ghost" data-sc-close aria-label="Close">✕</button>
        </header>
        <div class="modal-body sc-body"></div>
      </div>`;
    document.body.appendChild(overlay);
    const body = overlay.querySelector(".sc-body");
    let data = null;
    let busy = false;
    const paint = () => { body.innerHTML = render(data, { busy }); };
    const load = async () => {
      data = null; paint();
      try { data = await api(`${url}?limit=${PAGE}`); }
      catch (e) { body.innerHTML = `<p class="muted">Could not load shared citers: ${escHtml(e.message)}</p>`; return; }
      paint();
    };

    const onKey = (e) => { if (e.key === "Escape") close(); };
    const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
    document.addEventListener("keydown", onKey);

    overlay.addEventListener("click", async (e) => {
      if (e.target === overlay || e.target.closest("[data-sc-close]")) { close(); return; }
      // A paper link opens through the app's own link handler (it
      // bubbles on to document); the dialog just gets out of the way.
      if (e.target.closest("a[data-open-paper]")) { close(); return; }
      if (e.target.closest("[data-sc-more]") && data) {
        try {
          const d = await api(`${url}?offset=${data.elsewhere.length}&limit=${PAGE}`);
          data.elsewhere = data.elsewhere.concat(d.elsewhere || []);
          paint();
        } catch (err) { toast("could not load more: " + err.message, "err"); }
        return;
      }
      if (e.target.closest("[data-sc-fetch]") && data && !busy) {
        busy = true; paint();
        Progress.watch();
        // One at a time: the progress channel holds one job, and a
        // second fetch while one runs is refused (409).
        for (const p of data.papers.filter(x => x.status === "not_fetched")) {
          try { await api(`/api/paper/${encodeURIComponent(p.slug)}/citers/fetch`, { method: "POST" }); }
          catch (err) { toast(`finding citers of ${p.slug} failed: ${err.message}`, "err"); }
        }
        busy = false;
        if (overlay.isConnected) await load();
      }
    });
    await load();
  }

  return { MIN_PAPERS, linkedCount, render, rowHtml, open };
})();
