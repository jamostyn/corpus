// Corpus — Documents tab. Added 2026-09-25.
//
// Jack: "i want to add an another documents tab. for now i will just be
// uploading a pdf of a book chapter. i dont want any fancy integrations
// aside from all the text, highlight, and note features for the paper
// pdfs. but none of the api stuff."
//
// A document is a PDF with a title. The pane is the paper pane's PDF
// view — `pdfPaneHtml` from app.js, the same viewer and anchored-note
// gutter — so text selection, search, highlights, Note Mode and notes
// behave exactly as they do on a paper. Nothing here looks anything up.
//
// Also linkable from notes, addable to projects, renameable and poppable
// (2026-09-25) — each through the machinery papers already use.
//
// Depends at call time on app.js globals: state, api, toast, $, escHtml,
// escAttr, hideEmptyState, pdfPaneHtml, modeRowMatches, MODES_BY_ID,
// openDetached, isDetachedElsewhere, detachedPlaceholderHtml; and
// window.ProjectMembership from projects.js.

async function loadDocuments() {
  try {
    state.documents = await api(MODES_BY_ID.documents.listUrl);
    renderDocuments();
    if (state.selectedDocId && !state.documents.find(d => d.id === state.selectedDocId)) {
      state.selectedDocId = null;
    }
    renderDocumentDetail();
  } catch (e) {
    toast("documents load failed: " + e.message, "err");
  }
}

function renderDocuments() {
  const list = $("#documents-list");
  const q = (state.documentFilter || "").trim().toLowerCase();
  const rows = q
    ? state.documents.filter(r => modeRowMatches(MODES_BY_ID.documents, r, q))
    : state.documents;
  list.innerHTML = rows.map(d => `
    <li data-doc-id="${escAttr(d.id)}" ${d.id === state.selectedDocId ? 'class="selected"' : ""}>
      <div class="p-title">${escHtml(d.title)}</div>
      <div class="p-meta">${escHtml(_addedOn(d.added_at))}</div>
    </li>`).join("");
  if (state.mode === "documents") {
    const n = state.documents.length;
    $("#count-line").textContent = n === rows.length
      ? `${n} document${n === 1 ? "" : "s"}`
      : `${rows.length} of ${n} shown`;
  }
}

function selectDocument(id) {
  state.selectedDocId = id;
  renderDocuments();
  hideEmptyState();
  $("#document-detail").hidden = false;
  renderDocumentDetail();
}

function renderDocumentDetail(opts) {
  const force = Boolean(opts && opts.force);
  const pane = $("#document-detail");
  const doc = (state.documents || []).find(d => d.id === state.selectedDocId);
  if (!doc) {
    pane.dataset.docId = "";
    pane.innerHTML = _documentEmptyStateHtml();
    return;
  }
  // Re-rendering replaces the iframe and throws away the reading
  // position; a tab switch or list reload must not do that to the
  // document already open. `force` is for a real change of what the
  // pane must show: popped out elsewhere, or back.
  if (!force && pane.dataset.docId === doc.id && pane.querySelector(".pdf-viewer")) return;
  pane.dataset.docId = doc.id;
  const inOwnWindow = Boolean(state.detached && state.detached.kind === "document");
  const elsewhere = !inOwnWindow && isDetachedElsewhere("document", doc.id);
  pane.innerHTML = `
    <div class="pd-head">
      <div class="pd-head-titles">
        <h1 class="doc-title">${escHtml(doc.title)}</h1>
        <div class="pd-authors muted">${escHtml(doc.filename)} · ${escHtml(_addedOn(doc.added_at))}</div>
      </div>
      <div class="pd-head-actions">
        <button class="btn" data-doc-rename>Rename</button>
        ${inOwnWindow ? "" : `<button class="btn" data-doc-popout>Pop out ⧉</button>`}
        ${inOwnWindow ? "" : `<button class="btn" data-doc-project>Add to project</button>`}
      </div>
    </div>
    ${elsewhere ? detachedPlaceholderHtml("document", doc.id)
                : pdfPaneHtml(`/document/${encodeURIComponent(doc.id)}/pdf`, doc.title)}`;

  pane.querySelector("[data-doc-rename]").addEventListener("click", () => _startRename(pane, doc));
  const pop = pane.querySelector("[data-doc-popout]");
  if (pop) pop.addEventListener("click", () => openDetached("document", doc.id));
  const proj = pane.querySelector("[data-doc-project]");
  if (proj) proj.addEventListener("click", () =>
    window.ProjectMembership.openFor("document", doc.id));
}

/** Rename in place: the title becomes an input. Enter or leaving the
 *  field saves, Escape cancels. Only the title changes — the id, which
 *  note links and projects point at, stays put. */
function _startRename(pane, doc) {
  const h1 = pane.querySelector(".doc-title");
  if (!h1 || h1.querySelector("input")) return;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "doc-title-input";
  input.value = doc.title;
  h1.textContent = "";
  h1.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const title = input.value.trim();
    if (!save || !title || title === doc.title) { h1.textContent = doc.title; return; }
    try {
      const meta = await api(`/api/document/${encodeURIComponent(doc.id)}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      doc.title = meta.title;
      h1.textContent = meta.title;
      renderDocuments();
      toast("renamed", "ok");
    } catch (e) {
      h1.textContent = doc.title;
      toast("rename failed: " + e.message, "err");
    }
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
}

function _addedOn(ts) {
  return ts ? `added ${ts.slice(0, 10)}` : "";
}

function _documentEmptyStateHtml() {
  return `
    <div class="project-empty">
      <h2>Documents</h2>
      <p>PDFs that are not papers — a book chapter, a handout. Read,
         highlight and take notes on them exactly as on a paper.</p>
      <p>Nothing is looked up online. Use <strong>Add document…</strong> to add one.</p>
    </div>`;
}

async function _uploadDocument(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const doc = await api("/api/documents", { method: "POST", body: form });
    toast(`added ${doc.title}`, "ok");
    await loadDocuments();
    selectDocument(doc.id);
  } catch (e) {
    toast("add failed: " + e.message, "err");
  }
}

(function wireDocumentUpload() {
  const btn = document.getElementById("btn-add-document");
  const picker = document.getElementById("document-picker");
  if (!btn || !picker) return;
  btn.addEventListener("click", () => picker.click());
  picker.addEventListener("change", () => {
    const f = picker.files && picker.files[0];
    picker.value = "";              // the same file can be chosen again
    _uploadDocument(f);
  });
})();
