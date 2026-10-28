// Corpus — pure arithmetic for arrow-key list navigation.
//
// Given a list of `itemCount` items with `currentIndex` currently
// selected (or -1 / out-of-range if none), return the index of the
// next / prev item, or null if there's nowhere to move.
//
// direction: +1 = ArrowDown, -1 = ArrowUp.
//
// "Nothing selected" edge case: pretend the previous position was
// just off the end so ArrowDown selects the first item and ArrowUp
// selects the last one. Matches the original app.js behavior.
//
// Extracted from the arrow-key handler in `app.js` so the tricky
// arithmetic gets real unit tests without needing a DOM. The DOM
// side (findIndex against LI attributes, scrollIntoView, etc.) stays
// in app.js where it belongs.

(function () {
  function nextIndex({ itemCount, currentIndex, direction }) {
    if (itemCount <= 0) return null;
    let cur = currentIndex;
    if (typeof cur !== "number" || cur < 0 || cur >= itemCount) {
      // No / invalid current selection → seed just off the end so
      // the arithmetic below lands on the near end.
      cur = direction > 0 ? -1 : itemCount;
    }
    const next = direction > 0
      ? Math.min(itemCount - 1, cur + 1)
      : Math.max(0, cur - 1);
    return (next === currentIndex) ? null : next;
  }

  window.Nav = { nextIndex };
})();
