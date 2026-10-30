// Collapsible paper-view sections (src/collapsible.js).
//
// Requirement (2026-10-29): sections start collapsed behind a triangle;
// the abstract and TLDR stay open; opening one keeps it open on the next
// paper.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

// A minimal element: enough of the DOM for collapsible.js.
class El {
  constructor(tag, cls = [], text = "") {
    this.tagName = tag.toUpperCase(); this.cls = new Set(cls); this.children = []; this.parentElement = null;
    this.attrs = {}; this.childNodes = text ? [{ nodeType: 3, textContent: text }] : [];
    const self = this;
    this.classList = { add: c => self.cls.add(c), contains: c => self.cls.has(c),
      toggle: c => (self.cls.has(c) ? (self.cls.delete(c), false) : (self.cls.add(c), true)) };
  }
  add(...kids) { for (const k of kids) { k.parentElement = this; this.children.push(k); this.childNodes.push(k); } return this; }
  get firstElementChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  matches(sel) { return sel.startsWith(".") && this.cls.has(sel.slice(1)); }
  querySelectorAll(sel) {
    const want = sel.split(",").map(s => s.trim().toUpperCase());
    const out = [];
    const walk = (n) => { for (const k of n.children) { if (want.includes(k.tagName)) out.push(k); walk(k); } };
    walk(this); return out;
  }
  closest(sel) {
    for (let n = this; n; n = n.parentElement) {
      if (sel === "button, a, input, select" && ["BUTTON", "A", "INPUT", "SELECT"].includes(n.tagName)) return n;
      if (sel.startsWith(".pd-fold >") && ["H3", "H4"].includes(n.tagName) && n.parentElement && n.parentElement.cls.has("pd-fold")) return n;
    }
    return null;
  }
}

function page() {
  const root = new El("div");
  const abs = new El("div", ["pd-abstract"]).add(new El("h3", [], "Abstract"), new El("p"));
  const refs = new El("div", ["pd-refs"]).add(new El("h3", [], "References (42)"), new El("ol"));
  const btn = new El("button", [], "Search again");
  const bridges = new El("div", ["pd-bridges"]).add(new El("h4", [], "Bridges (3)").add(btn), new El("ul"));
  const links = new El("div", ["pd-links"]).add(new El("h3", [], "In-corpus connections"), bridges);
  root.add(abs, refs, links);
  return { root, abs, refs, links, bridges, btn };
}

function load() {
  let onClick = null;
  const sb = loadInVM(["collapsible.js"], { document: { addEventListener: (t, f) => { if (t === "click") onClick = f; } } });
  return { C: sb.Collapsible, click: (target) => onClick({ target }) };
}

test("sections fold closed; the abstract does not", () => {
  // Catches every section staying open (the request) or the abstract
  // being folded away with them.
  const { C } = load();
  const p = page();
  C.apply(p.root);
  assert.ok(p.refs.cls.has("pd-fold") && !p.refs.cls.has("pd-open"));
  assert.ok(p.links.cls.has("pd-fold") && p.bridges.cls.has("pd-fold"), "sub-sections fold too");
  assert.ok(!p.abs.cls.has("pd-fold"));
});

test("a click on the heading opens it, a click on a button inside does not", () => {
  // Catches "Search again" in the Bridges heading also folding the section.
  const { C, click } = load();
  const p = page();
  C.apply(p.root);
  click(p.btn);
  assert.ok(!p.bridges.cls.has("pd-open"));
  click(p.refs.children[0]);
  assert.ok(p.refs.cls.has("pd-open"));
  assert.equal(p.refs.children[0].attrs["aria-expanded"], "true");
});

test("an opened section stays open on the next paper, whatever its count", () => {
  // Catches the open state being lost on every paper, or keyed on the
  // count ("References (42)" vs "References (7)") so it never matches.
  const { C, click } = load();
  const a = page();
  C.apply(a.root);
  click(a.refs.children[0]);
  const b = page();
  b.refs.children[0].childNodes = [{ nodeType: 3, textContent: "References (7)" }];
  C.apply(b.root);
  assert.ok(b.refs.cls.has("pd-open"));
  assert.equal(C.sectionKey(b.refs.children[0]), "References");
});

test("applying twice changes nothing", () => {
  // Catches the late renderer (citers.js) re-applying and closing a
  // section the reader just opened.
  const { C, click } = load();
  const p = page();
  C.apply(p.root);
  click(p.links.children[0]);
  C.apply(p.root);
  assert.ok(p.links.cls.has("pd-open"));
});
