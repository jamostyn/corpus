// Collapsible sections in the paper view — window.Collapsible.
//
// Requirement (2026-10-29): the paper view's sections (Authors +
// affiliations, In-corpus connections and its Cites / Cited by / Bridges
// parts, Topics, References, Citers, Coverage, …) start collapsed behind
// a triangle and open on click. The title, the info table, the TLDR and
// the abstract stay open: they are what the page is for.
//
// A section is any block whose FIRST child is an h3 or h4. `apply(root)`
// marks them, and can run again on the same page: renderers that fill a
// section in later (citers.js) call it on what they added, and a section
// keeps the state the reader last gave it. A section opened once
// stays open on the next paper (remembered for the session, by heading
// text without its counts), so reading References across papers does not
// mean re-opening it every time.

window.Collapsible = (function () {
  "use strict";

  const ALWAYS_OPEN = [".pd-abstract", ".pd-tldr"];
  const opened = new Set();

  /** "References (42) C OA" → "References": the heading's own words, so
   *  a section keeps its open state whatever its counts and badges. */
  function sectionKey(heading) {
    const own = Array.from(heading.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent).join(" ");
    return own.replace(/\(\s*[\d,]+\s*\)/g, "").replace(/\s+/g, " ").trim();
  }

  function apply(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("h3, h4").forEach(h => {
      const box = h.parentElement;
      if (!box || box.firstElementChild !== h) return;
      if (ALWAYS_OPEN.some(sel => box.matches(sel))) return;
      box.classList.add("pd-fold");
      if (opened.has(sectionKey(h))) box.classList.add("pd-open");
      h.setAttribute("role", "button");
      h.setAttribute("aria-expanded", String(box.classList.contains("pd-open")));
    });
  }

  function toggle(heading) {
    const box = heading.parentElement;
    const open = box.classList.toggle("pd-open");
    heading.setAttribute("aria-expanded", String(open));
    const key = sectionKey(heading);
    if (open) opened.add(key); else opened.delete(key);
  }

  document.addEventListener("click", (e) => {
    const h = e.target.closest && e.target.closest(".pd-fold > h3, .pd-fold > h4");
    if (!h) return;
    // A button or link inside the heading ("Search again", "Refresh")
    // does its own job and must not also fold the section.
    if (e.target.closest("button, a, input, select")) return;
    toggle(h);
  });

  return { apply, sectionKey, _opened: opened };
})();
