// Live progress for long-running jobs.
//
// Requirement (2026-09-17, after a 25-paper import): the loading process
// shows which step it is on, what is being performed, and how much is
// left. The log for that import shows `POST /api/scan` at 26.6s and
// the bridge search at 21.4s — about 48 seconds behind a single
// "scanning corpus…" toast.
//
// Polls `/api/progress`, which reports whichever job the server is
// running. One channel for scan, Add PDFs and the bridge search, so
// there is one place that decides how progress LOOKS rather than three
// that drift apart.
//
// Depends at call-time on `escHtml` from app.js.

window.Progress = (function () {
  "use strict";

  const POLL_MS = 500;
  // How long to keep polling for a job the server has not reported yet.
  //
  // Bug (2026-09-21): the import progress only showed on a second scan.
  // The first poll fires the instant the
  // button is pressed and can reach the server BEFORE `progress.start()`
  // runs. It saw `active: false` and stopped polling for good. A second
  // press found the job already running, which is why that one worked.
  const START_GRACE_MS = 8000;
  // A finished banner is information for a few seconds, then clutter.
  // Previously polling stopped with the banner still rendered, and
  // nothing ever hid it.
  const DONE_LINGER_MS = 4000;
  const ERROR_LINGER_MS = 15000;
  let timer = null;
  let onDone = null;
  let watchStarted = 0;      // when watch() began; bounds the grace period
  let seenActive = false;    // has THIS watch seen the job running yet?
  let hideTimer = null;

  function _el() { return document.getElementById("job-progress"); }

  /** 328.8 -> "5:28". Whole seconds, minutes after 60.
   *
   *  The step text used to shift as the seconds ticked up (2026-09-22). Tenths of a second changed the
   *  string's width ten times a second ("9.9s" -> "10.0s" is also one
   *  character longer), and the right-aligned meta line re-flowed each
   *  time. Whole seconds change once a second; with tabular digits
   *  (styles.css, .jp-meta) each change is width-neutral. */
  function formatElapsed(s) {
    const t = Math.max(0, Math.floor(Number(s) || 0));
    if (t < 60) return `${t}s`;
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  }

  function _bar(done, total) {
    // Only render a bar when the units mean something. A bar stuck at
    // 0% reads as "hung"; no bar reads as "working", which is the
    // honest signal for a phase with no countable units.
    if (!total || total <= 0) return "";
    const pct = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
    return `<div class="jp-bar"><div class="jp-fill" style="width:${pct}%"></div></div>`;
  }

  function render(p) {
    const el = _el();
    if (!el) return;
    if (!p || !p.active) { el.hidden = true; el.innerHTML = ""; return; }

    el.hidden = false;
    if (p.error) {
      el.innerHTML = `<div class="jp-line jp-err">${escHtml(p.job)} — ${escHtml(p.error)}</div>`;
      return;
    }
    if (p.finished) {
      el.innerHTML = `<div class="jp-line jp-ok">${escHtml(p.job)} — done in ${escHtml(formatElapsed(p.elapsed_s))}</div>`;
      return;
    }

    // Each value is anchored in its own slot so text does not shift as
    // characters change (2026-09-22).
    //
    // These three used to be joined into ONE right-aligned string. Any
    // one of them changing width — "9s" to "10s", "9/100" to "10/100",
    // a phase count appearing — re-flowed the whole string, so the step
    // text slid left every second. Now each value owns a fixed-width
    // slot (styles.css, .jp-step/.jp-count/.jp-time) and can only move
    // within its own box. An empty slot keeps its width, so values do
    // not jump sideways when one of them is absent.
    const slot = (cls, text) =>
      `<span class="${cls}">${escHtml(text)}</span>`;
    const stepOf = (p.phase_count && p.phase_index)
      ? `step ${p.phase_index} of ${p.phase_count}` : "";
    const count = (p.total_units > 0) ? `${p.done_units}/${p.total_units}` : "";
    // Three levels, deliberately: the JOB (what you asked for), the
    // PHASE (which function is running), and the DETAIL (which file or
    // paper it is on). All three are named explicitly.
    el.innerHTML =
      `<div class="jp-line">` +
        `<span class="jp-job">${escHtml(p.job)}</span>` +
        `<span class="jp-phase">${escHtml(p.phase || "starting…")}</span>` +
        `<span class="jp-meta">` +
          slot("jp-step", stepOf) +
          slot("jp-count", count) +
          slot("jp-time", formatElapsed(p.elapsed_s)) +
        `</span>` +
      `</div>` +
      (p.detail ? `<div class="jp-detail">${escHtml(p.detail)}</div>` : "") +
      _bar(p.done_units, p.total_units);
  }

  // One poll in flight at a time. The interval fires every 500ms whether
  // or not the last answer has arrived, and under a heavy import the
  // server has taken 10s to answer one. Overlapping polls then complete
  // out of order, and an old snapshot landing after a new one rolls the
  // banner back — a step shown going backwards, or stuck.
  let inFlight = false;

  async function tick() {
    if (inFlight) return;
    inFlight = true;
    let p = null;
    try {
      const r = await fetch("/api/progress", { cache: "no-store" });
      p = await r.json();
    } catch (_) {
      // A dropped poll is not worth surfacing — the next one is 500ms
      // away, and the job itself is unaffected.
      return;
    } finally {
      inFlight = false;
    }
    if (p && p.active) seenActive = true;

    // Not started yet: keep waiting, silently, within the grace period.
    if (!p || !p.active) {
      if (!seenActive && Date.now() - watchStarted < START_GRACE_MS) return;
      render(null);
      stop();
      return;
    }

    render(p);
    if (p.finished) {
      stop();
      _scheduleHide(p.error ? ERROR_LINGER_MS : DONE_LINGER_MS);
      if (onDone) { const f = onDone; onDone = null; f(p); }
    }
  }

  function _scheduleHide(ms) {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      hideTimer = null;
      // A new job may have started while this banner lingered; only hide
      // if nothing is polling.
      if (!timer) render(null);
    }, ms);
  }

  /** Begin polling. `done` fires once when the job finishes, which is
   *  how callers know to reload the papers list — the job outlives the
   *  request that started it (the bridge search runs on after /api/scan
   *  has already returned). */
  function watch(done) {
    onDone = done || null;
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    if (timer) return;
    watchStarted = Date.now();
    seenActive = false;
    timer = setInterval(tick, POLL_MS);
    tick();
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  return { watch, stop, render, tick, formatElapsed,
           // Exposed for tests; the timings are the contract being fixed.
           START_GRACE_MS, DONE_LINGER_MS };
})();
