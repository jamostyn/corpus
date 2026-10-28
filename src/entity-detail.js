// Corpus — shared entity-detail render skeleton.
//
// Author / Institution / Journal detail panes all follow the same
// visual shape:
//
//   <div class="pd-header">
//     <h1>{display name}</h1>
//     <p class="pd-authors">{subtitle}</p>
//   </div>
//   <dl class="pd-meta">{ meta rows }</dl>
//   {optional refresh bar}
//   {side blocks in order}
//   {coverage matrix}
//
// This module renders that skeleton. Callers (author-detail.js,
// institution-detail.js, journal-detail.js) compute the entity-
// specific parts and pass them in as a descriptor.
//
// Loaded AFTER provenance.js (uses Coverage.renderTable) and BEFORE
// the three detail modules. Callers use `EntityDetail.render(desc)`.
//
// Refresh-button contract: emits ONE attribute pattern —
// `data-refresh-entity="<entity>" data-refresh-key="<key>"` — that
// the shared click handler in app.js catches. No more three-way
// per-entity branches.

(function () {
  function render(desc) {
    return `
      <div class="pd-header">
        <h1>${escHtml(desc.h1 || "")}</h1>
        ${desc.subtitle ? `<p class="pd-authors">${desc.subtitle}</p>` : ""}
      </div>
      <dl class="pd-meta">
        ${(desc.metaRows || []).map(([k, v]) =>
          `<dt>${escHtml(k)}</dt><dd>${v}</dd>`
        ).join("")}
      </dl>
      ${_renderRefresh(desc.refresh)}
      ${(desc.sideBlocks || []).filter(Boolean).join("")}
      ${Coverage.renderTable(desc.coverage || [])}
    `;
  }

  // Refresh bar. `desc.refresh` is:
  //   null / undefined   → no refresh bar (entity has no enrichable id)
  //   {entity, key, fetchedAt} → "OpenAlex enrichment fetched X ago"
  //     + "Refresh from source" button. entity in
  //     {"author", "institution", "journal"}; the click handler in
  //     app.js dispatches on data-refresh-entity.
  function _renderRefresh(r) {
    if (!r) return "";
    const label = r.fetchedAt
      ? `<span class="muted" title="${escAttr(r.fetchedAt)}">OpenAlex enrichment fetched ${escHtml(_relativeTime(r.fetchedAt))}</span>`
      : `<span class="muted">no OpenAlex enrichment cached yet</span>`;
    return `
      <div class="pd-refresh">
        ${label}
        <button class="btn ghost" data-refresh-entity="${escAttr(r.entity)}" data-refresh-key="${escAttr(r.key)}">Refresh from source</button>
      </div>`;
  }

  window.EntityDetail = { render };
})();
