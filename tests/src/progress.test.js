// Tests for src/progress.js — the floating job-progress banner.
//
// Bug (2026-09-21): the import progress only showed on a second scan, and
// did not go away when done.
//
// Both were timing bugs, invisible to anyone reading the render code:
//   * the first poll can beat the server's `progress.start()`, saw
//     `active: false`, and stopped polling for good;
//   * on finish, polling stopped with the "done" banner still drawn, and
//     nothing ever hid it.
//
// Timers and fetch are faked so each poll is stepped by hand.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

function setup() {
  const el = { hidden: true, innerHTML: "" };
  const replies = [];
  const timeouts = [];
  let now = 1000;
  const g = loadInVM(["progress.js"], {
    document: { getElementById: () => el, addEventListener() {} },
    fetch: async () => ({ json: async () => replies.shift() || { active: false } }),
    setInterval: () => 1,          // polls are driven by calling tick()
    clearInterval: () => {},
    setTimeout: (fn, ms) => { timeouts.push({ fn, ms }); return timeouts.length; },
    clearTimeout: () => {},
    Date: { now: () => now },
  });
  return { P: g.window.Progress, el, replies, timeouts,
           advance: (ms) => { now += ms; } };
}

test("a first poll that beats the server does not end the watch", async () => {
  // The reported bug. Scan is pressed, the first poll lands before the
  // job registers, and the banner never appears for that press.
  const { P, el, replies } = setup();
  P.watch();
  await new Promise(r => setImmediate(r));          // initial tick: inactive
  replies.push({ active: true, job: "Importing papers", phase: "Reading PDFs",
                 phase_index: 1, phase_count: 6, done_units: 3, total_units: 25,
                 elapsed_s: 2 });
  await P.tick();
  assert.equal(el.hidden, false, "banner must appear once the job registers");
  assert.match(el.innerHTML, /Importing papers/);
});

test("a watch with no job at all still gives up after the grace period", async () => {
  // Catches polling forever: a Scan that finds an empty inbox never
  // starts a job, and an unbounded wait would poll every 500ms for the
  // rest of the session.
  const { P, el, advance } = setup();
  P.watch();
  await new Promise(r => setImmediate(r));
  advance(P.START_GRACE_MS + 1);
  await P.tick();
  assert.equal(el.hidden, true);
});

test("the finished banner hides itself", async () => {
  // The other half of the report: "it doesnt go away when its done."
  const { P, el, replies, timeouts } = setup();
  replies.push({ active: true, finished: true, job: "Importing papers", elapsed_s: 40 });
  P.watch();
  await new Promise(r => setImmediate(r));
  assert.equal(el.hidden, false);
  assert.match(el.innerHTML, /done in 40s/);
  const hide = timeouts.find(t => t.ms === P.DONE_LINGER_MS);
  assert.ok(hide, "finishing must schedule a hide");
  hide.fn();
  assert.equal(el.hidden, true);
});

// ---------- 2026-09-22: stuck step, jittering meta line ----------

test("a later phase renders as that step, not step 1", () => {
  // Catches the step counter being pinned — the server's phase_index is
  // the only input, and it must reach the banner as-is.
  const { P, el } = setup();
  P.render({ active: true, job: "Importing papers", phase: "Fetching citations",
             phase_index: 4, phase_count: 6, done_units: 42, total_units: 736, elapsed_s: 328.8 });
  assert.match(el.innerHTML, /step 4 of 6/);
});

test("a poll is not issued while the previous one is still waiting", async () => {
  // Catches overlapping polls: under load a reply took 10s, and an old
  // snapshot arriving after a newer one rolls the banner back.
  const el = { hidden: true, innerHTML: "" };
  let calls = 0, release;
  const g = loadInVM(["progress.js"], {
    document: { getElementById: () => el, addEventListener() {} },
    fetch: () => { calls++; return new Promise(r => { release = r; }); },
    setInterval: () => 1, clearInterval() {}, setTimeout: () => 0, clearTimeout() {},
    Date: { now: () => 0 },
  });
  const P = g.window.Progress;
  const first = P.tick();
  P.tick(); P.tick();
  assert.equal(calls, 1, "a second poll started before the first returned");
  release({ json: async () => ({ active: false }) });
  await first;
});

test("elapsed time is whole seconds, then minutes", () => {
  // Catches tenths coming back: they changed the line's width ten times
  // a second and made everything jitter.
  const { P } = setup();
  assert.equal(P.formatElapsed(9.9), "9s");
  assert.equal(P.formatElapsed(60), "1:00");
  assert.equal(P.formatElapsed(328.8), "5:28");
});

test("the meta line uses tabular digits", () => {
  // Catches dropping the CSS half of the jitter fix — proportional
  // digits ("1" narrower than "8") shift the text on every tick.
  const css = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "..", "..", "src", "styles.css"), "utf8");
  const rule = css.slice(css.indexOf(".jp-meta {"), css.indexOf("}", css.indexOf(".jp-meta {")));
  assert.match(rule, /font-variant-numeric:\s*tabular-nums/);
});

test("each meta value is its own anchored slot", () => {
  // Catches the three values being joined back into one string (they
  // were, and the text shifted as the
  // characters changed): a shared box re-flows every value when any one
  // of them changes width.
  const { P, el: host } = setup();
  P.render({ active: true, job: "Importing papers", phase: "Reading PDFs",
             phase_index: 1, phase_count: 6, done_units: 9, total_units: 100,
             elapsed_s: 9 });
  const step = host.innerHTML.match(/<span class="jp-step">([^<]*)</)[1];
  const count = host.innerHTML.match(/<span class="jp-count">([^<]*)</)[1];
  const time = host.innerHTML.match(/<span class="jp-time">([^<]*)</)[1];
  assert.equal(step, "step 1 of 6");
  assert.equal(count, "9/100");
  assert.equal(time, "9s");

  // A slot with nothing to show still exists, so the others do not
  // slide over into its space when a phase reports no units.
  P.render({ active: true, job: "Importing papers", phase: "Finding bridges",
             phase_index: 5, phase_count: 6, done_units: 0, total_units: 0,
             elapsed_s: 70 });
  assert.match(host.innerHTML, /<span class="jp-count"><\/span>/);
  assert.equal(host.innerHTML.match(/<span class="jp-time">([^<]*)</)[1], "1:10");
});

test("every meta slot has a fixed width in the stylesheet", () => {
  // Catches the CSS half going missing: without a width per slot the
  // markup change alone does nothing, because each span would size to
  // its content and still shift its neighbours.
  const css = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "..", "..", "src", "styles.css"), "utf8");
  for (const cls of ["jp-step", "jp-count", "jp-time"]) {
    const rule = css.slice(css.indexOf(`.${cls}`), css.indexOf("}", css.indexOf(`.${cls}`)));
    assert.match(rule, /width:\s*\d+ch/, `${cls} has no fixed width`);
    assert.match(rule, /text-align:\s*right/, `${cls} is not anchored to one edge`);
  }
});
