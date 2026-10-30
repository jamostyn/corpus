// The top bar (styles.css .topbar / .tabs).
//
// Bug (2026-10-28): the tabs had no space above them. With nine tabs (dev
// builds) the bar is wider than the default 1200px window, so its items
// shrank and their labels wrapped onto two lines, filling the 50px bar.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const CSS = fs.readFileSync(path.join(__dirname, "..", "..", "src", "styles.css"), "utf8");

function rule(selector) {
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = CSS.match(new RegExp("(^|\\n)" + esc + "\\s*\\{([^}]*)\\}"));
  assert.ok(m, `no rule for ${selector}`);
  return m[2];
}

test("nothing in the bar wraps or shrinks except the tab strip", () => {
  // Catches the wrap: buttons and tabs breaking onto two lines.
  const all = rule(".topbar > *");
  assert.match(all, /flex-shrink:\s*0/);
  assert.match(all, /white-space:\s*nowrap/);
  const tab = rule(".tabs .tab");
  assert.match(tab, /white-space:\s*nowrap/);
  assert.match(tab, /flex-shrink:\s*0/);
});

test("a narrow window scrolls the tab strip instead of squeezing it", () => {
  // Catches the strip keeping min-width:auto, which forces the whole bar
  // wider than the window and pushes Settings off-screen.
  const strip = rule(".topbar > .tabs");
  assert.match(strip, /min-width:\s*0/);
  assert.match(strip, /overflow-x:\s*auto/);
});

test("the tab strip leaves room above and below inside the bar", () => {
  // Catches a tab or strip taller than the bar: strip padding + tab
  // padding + line height must sit inside --topbar-h with a margin.
  const px = (re, text) => Number((text.match(re) || [])[1]);
  const bar = px(/--topbar-h:\s*(\d+)px/, CSS);
  const tab = rule(".tabs .tab");
  const tabH = px(/line-height:\s*(\d+)px/, tab) + 2 * px(/padding:\s*(\d+)px/, tab);
  const stripH = tabH + 2 * px(/padding:\s*(\d+)px/, rule(".tab-group"));
  assert.ok(bar - stripH >= 12, `strip ${stripH}px in a ${bar}px bar`);
});
