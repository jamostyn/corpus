// Why Corpus is showing in a browser — window.WindowNotice.
//
// When the app window cannot open, the launcher serves the app in the
// default browser and GET /api/config carries `window_error`
// ({reason, detail}; python/window_fallback.py). This bar says so once
// per session, with the fix when one is known.

window.WindowNotice = (function () {
  "use strict";

  const WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/";
  const SEEN_KEY = "corpus.windowNotice.dismissed";

  /** The bar's inner HTML for one `window_error`, or "" for none. */
  function html(info) {
    if (!info || !info.reason) return "";
    const msg = info.reason === "webview2_missing"
      ? `Corpus opened in your browser because its window needs the Microsoft Edge WebView2 Runtime. ` +
        `<a href="${WEBVIEW2_URL}" target="_blank" rel="noopener">Install WebView2</a>, then restart Corpus.`
      : `Corpus opened in your browser because its window could not start. Everything works the same here.`;
    const detail = info.detail ? `<div class="wn-detail">${escHtml(info.detail)}</div>` : "";
    return `<div class="wn-text">${msg}${detail}</div><button class="btn ghost" id="wn-dismiss">Dismiss</button>`;
  }

  function show(info) {
    const bar = document.getElementById("window-notice");
    if (!bar) return;
    let dismissed = false;
    try { dismissed = sessionStorage.getItem(SEEN_KEY) === "1"; } catch (_) {}
    const inner = dismissed ? "" : html(info);
    bar.innerHTML = inner;
    bar.hidden = !inner;
    const btn = document.getElementById("wn-dismiss");
    if (btn) btn.addEventListener("click", () => {
      bar.hidden = true;
      try { sessionStorage.setItem(SEEN_KEY, "1"); } catch (_) {}
    });
  }

  return { html, show };
})();
