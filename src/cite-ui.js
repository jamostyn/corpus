// Citations on screen — window.CiteUI.
//
//   * `mountPaper(host, slug)`: the "Cite" section of a paper's info page —
//     a style menu, the in-text citation (parenthetical and, for
//     author-date styles, narrative) and the reference-list entry, each
//     with a Copy button.
//   * `openProjectExport(project)`: the project's "Export references" —
//     every paper in the project as a reference list in the chosen style,
//     copied or saved to a file.
//
// The formatting itself is cite.js; the data is /api/paper/<slug>/csl and
// /api/project/<pid>/csl (python/cite_api.py). Relies at call time on
// app.js globals: api, toast, escHtml, escAttr; and window.Cite.

window.CiteUI = (function () {
  "use strict";

  const STYLE_KEY = "corpus.citeStyle";
  // Author-date styles also have a narrative form ("Grady et al. (2019)").
  const NARRATIVE = new Set(["apa", "chicago", "harvard", "mla"]);

  function savedStyle() {
    try { return localStorage.getItem(STYLE_KEY) || Cite.STYLES[0].id; } catch (_) { return Cite.STYLES[0].id; }
  }
  function saveStyle(id) { try { localStorage.setItem(STYLE_KEY, id); } catch (_) {} }

  function styleOptions(current) {
    return Cite.STYLES.map(s =>
      `<option value="${escAttr(s.id)}"${s.id === current ? " selected" : ""}>${escHtml(s.label)}</option>`).join("");
  }

  /** Copy with formatting (italics survive into Word / Docs) where the
   *  webview allows it, else as plain text. */
  async function copyCitation(html, label) {
    const plain = Cite.toPlain(html);
    try {
      if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([plain], { type: "text/plain" }),
        })]);
      } else {
        await navigator.clipboard.writeText(plain);
      }
      toast(`${label} copied`, "ok");
    } catch (e) {
      toast("copy failed: " + e.message, "err");
    }
  }

  // ---------- the paper's Cite section ----------

  function sectionHtml() {
    return `
      <div class="pd-cite" id="pd-cite">
        <h3>Cite</h3>
        <div class="pd-cite-bar"><label>Style <select class="pd-cite-style">${styleOptions(savedStyle())}</select></label></div>
        <div class="pd-cite-body"><p class="muted">Loading…</p></div>
      </div>`;
  }

  async function mountPaper(host, slug) {
    if (!host) return;
    let item;
    try {
      item = (await api(`/api/paper/${encodeURIComponent(slug)}/csl`)).item;
    } catch (e) {
      host.querySelector(".pd-cite-body").innerHTML = `<p class="muted">Citation unavailable: ${escHtml(e.message)}</p>`;
      return;
    }
    const select = host.querySelector(".pd-cite-style");
    const paint = async () => {
      const styleId = select.value;
      saveStyle(styleId);
      const body = host.querySelector(".pd-cite-body");
      try {
        const r = await Cite.format([item], styleId, "html");
        const row = r.rows[0];
        const lines = [["In text", row.intext]];
        if (NARRATIVE.has(styleId) && row.narrative) lines.push(["In a sentence", row.narrative]);
        lines.push(["Reference list", r.bibliography[0] || row.reference]);
        body.innerHTML = lines.map(([label, html], i) => `
          <div class="pd-cite-row">
            <span class="pd-cite-label">${escHtml(label)}</span>
            <span class="pd-cite-out">${html}</span>
            <button class="btn ghost" data-cite-copy="${i}">Copy</button>
          </div>`).join("") + _notes(item);
        body.querySelectorAll("[data-cite-copy]").forEach(b => b.addEventListener("click", () => {
          const [label, html] = lines[+b.dataset.citeCopy];
          copyCitation(html, label);
        }));
      } catch (e) {
        body.innerHTML = `<p class="muted">Could not format this citation: ${escHtml(e.message)}</p>`;
      }
    };
    select.addEventListener("change", paint);
    await paint();
  }

  /** What the reference is missing, said plainly, so a gap is not mistaken
   *  for the style's choice. */
  function _notes(item) {
    const gaps = [];
    if (!item.author) gaps.push("authors");
    if (!item.issued) gaps.push("year");
    if (item.type === "chapter") gaps.push("the book's editors and publisher");
    return gaps.length
      ? `<p class="muted pd-cite-note">Not in this paper's record: ${escHtml(gaps.join(", "))}.</p>`
      : "";
  }

  // ---------- exporting a project's references ----------

  function _safeName(s) {
    return (String(s || "references").replace(/[^\w .-]+/g, "").trim() || "references").slice(0, 80);
  }

  async function openProjectExport(project) {
    let data;
    try {
      data = await api(`/api/project/${encodeURIComponent(project.id)}/csl`);
    } catch (e) {
      toast("export failed: " + e.message, "err");
      return;
    }
    if (!data.items.length) { toast("This project has no papers to cite.", "err"); return; }
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay cite-export";
    overlay.innerHTML = `
      <div class="modal">
        <header class="modal-header">
          <h2>References — ${escHtml(data.title)}</h2>
          <button class="btn ghost" data-cite-act="close" aria-label="Close">✕</button>
        </header>
        <div class="modal-body">
          <label>Style <select class="cite-export-style">${styleOptions(savedStyle())}</select></label>
          <span class="muted cite-export-count">${data.items.length} paper${data.items.length === 1 ? "" : "s"}</span>
          <div class="cite-export-list"><p class="muted">Formatting…</p></div>
        </div>
        <footer class="modal-footer">
          <button class="btn" data-cite-act="copy">Copy</button>
          <button class="btn primary" data-cite-act="save">Save as file…</button>
        </footer>
      </div>`;
    document.body.appendChild(overlay);
    const select = overlay.querySelector(".cite-export-style");
    let current = null;
    const paint = async () => {
      saveStyle(select.value);
      current = await Cite.format(data.items, select.value, "html");
      overlay.querySelector(".cite-export-list").innerHTML =
        `<ol class="cite-export-refs">${current.bibliography.map(h => `<li>${h}</li>`).join("")}</ol>`;
    };
    select.addEventListener("change", paint);
    overlay.addEventListener("click", async (e) => {
      const act = e.target.dataset && e.target.dataset.citeAct;
      if (act === "close" || e.target === overlay) overlay.remove();
      if (!current) return;
      if (act === "copy") copyCitation(`<div>${current.bibliography.map(h => `<p>${h}</p>`).join("")}</div>`, "References");
      if (act === "save") {
        const text = current.bibliography.map(Cite.toPlain).join("\n\n") + "\n";
        const name = `${_safeName(data.title)} — references (${Cite.styleById(select.value).label}).txt`;
        await saveText(name, text);
      }
    });
    await paint();
  }

  /** Save through the desktop bridge's save dialog; in a plain browser
   *  (dev fallback) a download link does the same job. */
  async function saveText(name, text) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_text_file) {
      // Literal `window.pywebview.api.<method>` form: the bridge contract
      // test finds calls by it.
      const r = await window.pywebview.api.save_text_file(name, text);
      if (r === "saved") toast("References saved", "ok");
      else if (r === "failed") toast("save failed", "err");
      return;
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return { sectionHtml, mountPaper, openProjectExport, copyCitation, _notes, _safeName };
})();
