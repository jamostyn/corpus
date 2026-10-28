// Corpus — modal registry. Shared by every part of the app that
// needs to ask "is a modal open right now?" — most importantly the
// arrow-key sidebar-nav handler, which must yield to modals so
// arrow-keys type into their inputs instead of moving the sidebar.
//
// Loaded BEFORE app.js so `Modals.anyOpen()` is defined by the time
// app.js's top-level event wiring runs.
//
// Two ways to opt in:
//
//   1. `Modals.watchSelector(sel)` — cheapest. Modals whose "open"
//      state = "the element with this selector exists in the DOM"
//      (or `[hidden]` = false). Corpus's shipped `.modal-overlay`
//      pattern is registered by default; dev-only bundles register
//      their own class names at load-time, so app.js never carries
//      dev-only class names.
//
//   2. `Modals.register(el)` / `Modals.unregister(el)` — explicit
//      element-based registration. Use when your modal doesn't
//      follow a shared class convention.

(function () {
  const openElements = new Set();
  const watchedSelectors = [
    // Shipped default: any element with `.modal-overlay` that isn't
    // `[hidden]`. Settings, tooltip-picker in prod, etc.
    ".modal-overlay:not([hidden])",
  ];

  function watchSelector(sel) {
    if (typeof sel === "string" && sel && !watchedSelectors.includes(sel)) {
      watchedSelectors.push(sel);
    }
  }

  function register(el) {
    if (el) openElements.add(el);
    return () => openElements.delete(el);
  }

  function unregister(el) {
    openElements.delete(el);
  }

  function anyOpen() {
    if (openElements.size > 0) return true;
    for (const sel of watchedSelectors) {
      if (document.querySelector(sel)) return true;
    }
    return false;
  }

  window.Modals = { watchSelector, register, unregister, anyOpen };
})();
