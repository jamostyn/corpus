// Tests for app.js::fetchModeList — the refresh the note link picker and
// the project member picker run every time they open.
//
// Bug (2026-09-29): in a popped-out note the link-paper picker did not
// pick up papers added to the corpus. The pickers
// only loaded a list when it was EMPTY, so a window that already had a
// paper list never saw papers imported after it opened.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "src", "app.js"), "utf8");
const START = SRC.indexOf("async function fetchModeList");
const SNIPPET = SRC.slice(START, SRC.indexOf("\n}\n", START) + 3);

function setup(initial) {
  const calls = [];
  const ctx = {
    state: { papers: initial, notes: ["n1"] },
    api: async (url) => { calls.push(url); return ["fresh-a", "fresh-b"]; },
  };
  vm.createContext(ctx);
  vm.runInContext(SNIPPET, ctx);
  return { ctx, calls };
}

test("a list the window already has is fetched again", async () => {
  // Catches the reported bug: a non-empty (stale) paper list was reused
  // and the newly imported paper never appeared.
  const { ctx, calls } = setup(["stale"]);
  await ctx.fetchModeList({ stateKey: "papers", listUrl: "/api/papers", load: () => {} });
  assert.deepEqual(calls, ["/api/papers"]);
  assert.deepEqual([...ctx.state.papers], ["fresh-a", "fresh-b"]);
});

test("it does not call the tab's own loader when it has a URL", async () => {
  // Catches routing the refresh through `mode.load`, which re-renders the
  // sidebar and, for documents, reloads an open PDF under the user.
  let loaded = 0;
  const { ctx } = setup([]);
  await ctx.fetchModeList({ stateKey: "papers", listUrl: "/api/papers", load: () => { loaded++; } });
  assert.equal(loaded, 0);
});

test("a tab with no URL keeps load-if-empty", async () => {
  // Catches the fallback reloading (and re-rendering) Notes on every
  // picker open, or never loading it at all.
  const { ctx } = setup([]);
  let loaded = 0;
  await ctx.fetchModeList({ stateKey: "notes", load: () => { loaded++; } });
  assert.equal(loaded, 0, "notes already in state: no reload");
  ctx.state.notes = [];
  await ctx.fetchModeList({ stateKey: "notes", load: () => { loaded++; } });
  assert.equal(loaded, 1, "empty notes: load once");
});
