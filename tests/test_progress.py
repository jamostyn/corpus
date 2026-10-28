"""The shared progress channel, and auto-bridges after an import.

Jack, 2026-09-17: "whenever new papers are added can you automatically
search for bridges? and can you make sure that the loading process is
incredibly transparent so you can know what step it is on, what
function is being performed, and how much is left."

The second half is what makes the first half acceptable. Auto-running
the bridge search was DECLINED on 2026-09-14 — and recorded as
declined — because hanging a silent ~40s network call off Add PDFs is
a bad trade. Visible progress is precisely what changes that, so the
two halves ship together.

Network is stubbed in every endpoint test here.
"""
from __future__ import annotations

import time

import pytest

import progress


@pytest.fixture(autouse=True)
def _clean_slot():
    progress.reset()
    yield
    progress.reset()


@pytest.fixture(autouse=True)
def _no_citer_network(monkeypatch):
    """The after-import chain fetches citers before the bridge search
    (2026-09-22). These tests are about the chain's shape, and the suite
    never touches OpenAlex — stub the fetch, record what it was asked."""
    import citers
    calls = []
    monkeypatch.setattr(citers, "backfill",
                        lambda slugs=None, on_step=None, force=False: calls.append(list(slugs or [])) or {})
    return calls


# ---------- the channel ----------

def test_an_idle_server_reports_inactive(client, corpus_dir):
    """Catches: reporting a phantom job on a fresh boot, which would
    leave a progress strip on screen with nothing running."""
    assert client.get("/api/progress").get_json() == {"active": False}


def test_a_running_job_reports_phase_detail_and_counts():
    """Catches: dropping any of the three levels Jack asked for by
    name — which step (phase index), what function (phase), and how
    much is left (done/total)."""
    job = progress.start("Importing papers", ["Reading PDFs", "Finding bridges"])
    job.step("Reading PDFs", "smith-2020.pdf", 3, 25)
    s = progress.snapshot()
    assert s["active"] and not s["finished"]
    assert s["job"] == "Importing papers"
    assert s["phase"] == "Reading PDFs"
    assert s["detail"] == "smith-2020.pdf"
    assert (s["done_units"], s["total_units"]) == (3, 25)
    assert (s["phase_index"], s["phase_count"]) == (1, 2)


def test_a_second_job_cannot_evict_a_running_one():
    """Catches: letting a background task clobber the slot mid-import.

    The bridge search starts while the scan's job is still open. If it
    called `start()` the user would watch the import's progress vanish
    and be replaced, which reads as the import having failed."""
    assert progress.start("first", ["a"]) is not None
    assert progress.start("second", ["b"]) is None
    assert progress.snapshot()["job"] == "first"


def test_a_finished_job_can_be_replaced():
    """Catches: a one-shot slot. Two consecutive scans must both
    report."""
    progress.start("first", ["a"]).finish()
    assert progress.start("second", ["b"]) is not None


def test_a_finished_job_lingers_then_goes_quiet(monkeypatch):
    """Catches: either extreme. Clearing instantly means a poll landing
    just after completion sees nothing and the user never learns it
    finished; never clearing leaves a stale "done" banner up forever."""
    progress.start("job", ["a"]).finish()
    assert progress.snapshot()["finished"] is True

    base = progress._now()
    monkeypatch.setattr(progress, "_now",
                        lambda: base + progress.LINGER_SECONDS + 1)
    assert progress.snapshot() == {"active": False}


def test_an_error_is_reported_not_swallowed():
    """Catches: a failed job reading as a successful one. The strip
    renders `error` differently, and it is the only signal the user
    gets that a background step died."""
    progress.start("job", ["a"]).finish("something broke")
    s = progress.snapshot()
    assert s["finished"] is True and s["error"] == "something broke"


def test_steps_after_completion_are_ignored():
    """Catches: a late background write resurrecting a finished job.

    Threads do not stop on request. A stray `step()` after `finish()`
    would flip the strip back to "running" with no job behind it."""
    job = progress.start("job", ["a"])
    job.step("a", "real work", 1, 2)
    job.finish()
    job.step("a", "late write", 99, 99)
    s = progress.snapshot()
    assert s["finished"] is True
    # The payload must be untouched too. Asserting only `finished`
    # missed a mutation that kept the flag but overwrote the detail,
    # so the strip showed a stale job's final state with a later
    # thread's text pasted into it.
    assert s["detail"] == "real work", "a post-finish step was applied"
    assert s["done_units"] == 1


# ---------- the import hook ----------

def _pdfless_summary(corpus_dir, slug):
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        f"---\ntitle: {slug}\nyear: 2020\nauthor: T, A.\ndoi: 10.1000/{slug}\n---\n\n"
        "## References\n", encoding="utf-8")


def test_an_empty_scan_closes_its_job(client, corpus_dir):
    """Catches: leaving a job open when there was nothing to do.

    The strip would sit at "step 1 of 6" indefinitely, and the next
    scan could not start a job at all."""
    client.post("/api/scan")
    for _ in range(20):
        if progress.snapshot().get("finished"):
            break
        time.sleep(0.05)
    assert progress.snapshot()["finished"] is True


def test_an_empty_scan_does_not_run_a_bridge_search(client, corpus_dir, monkeypatch):
    """Catches: firing the network on every scan regardless.

    Scan is also how users check for nothing-to-do. A ~40s OpenAlex
    sweep on a no-op scan is the behaviour that got auto-bridges
    declined the first time."""
    import extract_api
    called = []
    monkeypatch.setattr("bridges_api.compute_bridges_now",
                        lambda job=None: called.append(job) or {})
    client.post("/api/scan")
    time.sleep(0.2)
    assert called == [], "bridge search kicked with nothing added"

    # And directly, because the caller's own `if added:` check would
    # otherwise hide a missing guard inside the hook. Mocking
    # `_after_import` itself — which an earlier version of
    # this test did — tests nothing at all.
    extract_api._after_import([], progress.NULL)
    time.sleep(0.2)
    assert called == [], "the hook ran the search despite being told 0 were added"


def test_the_scan_response_says_how_many_landed(client, corpus_dir, monkeypatch):
    """Catches: making the client re-derive `added` by summing
    statuses — a second copy of the rule that decides whether the
    bridge search runs."""
    body = client.post("/api/scan").get_json()
    assert body["added"] == 0
    assert set(body) == {"inbox_processed", "extracted", "skipped", "added"}

    # A zero corpus makes 0 correct even for a hard-coded field, which
    # let a "always report 0" mutation survive. Force a non-zero case
    # by faking the per-file result the count is derived from — no PDF
    # and no network, which the suite forbids.
    import extract_api
    monkeypatch.setattr(extract_api, "_process_inbox_pdf",
                        lambda pdf, original_name=None: {
                            "filename": pdf.name, "status": "extracted",
                            "slug": pdf.stem, "renamed": False})
    monkeypatch.setattr(extract_api, "_after_import", lambda slugs, job=None: None)
    (corpus_dir / "inbox" / "fake-2020.pdf").write_bytes(b"%PDF-1.4\n")
    body = client.post("/api/scan").get_json()
    assert body["added"] == 1, "added is not derived from what actually landed"


def test_bridges_are_kicked_once_per_batch_not_once_per_paper(corpus_dir, monkeypatch):
    """Catches: recomputing inside the per-file loop.

    The bridge search is a whole-corpus operation. Running it per paper
    would make a 25-file import 25x slower for an answer thrown away 24
    times."""
    import extract_api
    runs = []
    monkeypatch.setattr("bridges_api.compute_bridges_now",
                        lambda job=None: runs.append(job) or {})
    extract_api._after_import([f"p{i}" for i in range(25)], progress.NULL)
    for _ in range(40):
        if runs:
            break
        time.sleep(0.05)
    assert runs == [progress.NULL], f"expected one run reusing the caller's job, got {runs}"


def test_the_auto_search_reuses_the_imports_job(corpus_dir, monkeypatch):
    """Catches: the background search calling `start()`.

    Handing the import's own job to the search is what keeps the two
    looking like one six-step sequence instead of the import seeming to
    finish and a second job appearing from nowhere."""
    import extract_api
    seen = []
    monkeypatch.setattr("bridges_api.compute_bridges_now",
                        lambda job=None: seen.append(job) or {})
    job = progress.start("Importing papers", ["Reading PDFs"])
    extract_api._after_import(["a-2020"], job)
    for _ in range(40):
        if seen:
            break
        time.sleep(0.05)
    assert seen == [job], "the search started its own job instead of reusing the import's"


def test_a_failed_bridge_search_does_not_look_like_a_failed_import(corpus_dir, monkeypatch):
    """Catches: an exception in the background thread killing the job
    silently, or reporting as if the papers were lost.

    By the time the search runs the papers are already on disk. The
    error must name the bridge search specifically."""
    import extract_api

    def boom(job=None):
        raise RuntimeError("network down")
    monkeypatch.setattr("bridges_api.compute_bridges_now", boom)

    job = progress.start("Importing papers", ["Reading PDFs"])
    extract_api._after_import(["a-2020", "b-2020", "c-2020"], job)
    for _ in range(40):
        s = progress.snapshot()
        if s.get("finished"):
            break
        time.sleep(0.05)
    s = progress.snapshot()
    assert s["finished"] is True
    assert "bridge" in (s["error"] or "").lower(), s["error"]


# ---------- 2026-09-22: citers fetched on every import ----------

def test_an_import_fetches_citers_for_what_it_added_before_bridges(corpus_dir, monkeypatch, _no_citer_network):
    """Catches the request not being met: Jack asked that citers be
    fetched by default on import. Also catches fetching the WHOLE corpus
    on each import (~3,000 requests) instead of just the added papers,
    and running the bridge search first (it is next in line to use them)."""
    import extract_api
    order = []
    monkeypatch.setattr("citers.backfill",
                        lambda slugs=None, on_step=None, force=False: order.append(("citers", list(slugs))) or {})
    monkeypatch.setattr("bridges_api.compute_bridges_now",
                        lambda job=None: order.append(("bridges",)) or {})
    extract_api._after_import(["new-2024", "other-2025"], progress.NULL)
    for _ in range(40):
        if len(order) == 2:
            break
        time.sleep(0.05)
    assert order == [("citers", ["new-2024", "other-2025"]), ("bridges",)]


def test_a_failed_citer_fetch_still_runs_the_bridge_search(corpus_dir, monkeypatch):
    """Catches one post-import step taking the next down with it."""
    import extract_api

    def boom(*a, **k):
        raise RuntimeError("openalex down")
    ran = []
    monkeypatch.setattr("citers.backfill", boom)
    monkeypatch.setattr("bridges_api.compute_bridges_now",
                        lambda job=None: ran.append(True) or {})
    extract_api._after_import(["x-2020"], progress.NULL)
    for _ in range(40):
        if ran:
            break
        time.sleep(0.05)
    assert ran == [True]


def test_both_import_routes_build_their_phases_from_one_definition():
    """Catches Scan and Add PDFs drifting apart: they had two hand-built
    phase lists, so a new phase could land in one and not the other."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "python" / "extract_api.py").read_text()
    assert src.count("progress.start(") == src.count("import_phases(") - 1  # minus the def
    import extract_api
    import citers
    phases = extract_api.import_phases(["Reading PDFs"])
    assert citers.PHASE in phases
    assert phases.index(citers.PHASE) < phases.index("Resolving papers")


# ---------- 2026-09-22: one import at a time, and owned writes ----------

def test_a_second_import_is_refused_while_one_is_running(client, corpus_dir):
    """Catches the bug Jack reported: "for the last batch it kept jumping
    between 100 and 98 papers total".

    server.log shows two scans of the same inbox finishing two seconds
    apart (added=64 and added=37). Each had counted the inbox at a
    different moment — 100 files, then 98 after two had been moved — and
    both wrote their own count into the one progress slot, so the total
    alternated. They were also processing each other's files."""
    (corpus_dir / "inbox" / "a.pdf").write_bytes(b"%PDF-1.4\n")
    progress.start("Importing papers", ["Reading PDFs"])
    r = client.post("/api/scan")
    assert r.status_code == 409, "a second scan ran alongside the first"
    assert r.get_json()["error"] == "busy"
    assert (corpus_dir / "inbox" / "a.pdf").exists(), "the refused scan still took the inbox"
    assert progress.snapshot()["job"] == "Importing papers"


def test_add_pdfs_is_refused_while_an_import_is_running(client, corpus_dir):
    """Same collision through the other door. Add PDFs and Scan share the
    inbox and the progress slot, so whichever starts second must be told
    no rather than silently interleaving."""
    import io
    progress.start("Importing papers", ["Reading PDFs"])
    r = client.post("/api/extract", data={"files": (io.BytesIO(b"%PDF-1.4\n"), "x.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 409 and r.get_json()["error"] == "busy"


def test_a_refused_caller_cannot_write_into_the_running_job():
    """Catches the deeper cause: writes used to go through a module-level
    `step()` that wrote to whatever was in the slot. A caller whose
    `start()` was refused could still overwrite the running job's phase
    and counts — which is exactly how one scan's "100" and another's
    "98" ended up in the same banner."""
    first = progress.start("Importing papers", ["Reading PDFs"])
    first.step("Reading PDFs", "real", 3, 100)
    assert progress.start("Importing papers", ["Reading PDFs"]) is None

    stale = progress.Job(first.token + 99)          # a handle nobody was issued
    stale.step("Reading PDFs", "intruder", 1, 98)
    s = progress.snapshot()
    assert (s["done_units"], s["total_units"]) == (3, 100), "a foreign write landed"
    assert s["detail"] == "real"

    stale.finish("intruder's error")
    assert progress.snapshot()["finished"] is False, "a foreign caller ended the job"


def test_a_search_refused_the_slot_reports_nowhere_rather_than_hijacking(corpus_dir, monkeypatch):
    """Catches the fallback that used to exist: `compute_bridges_now`
    called `progress.start`, ignored the False, and stepped anyway —
    putting bridge phases into an unrelated job's banner."""
    import bridges_api
    monkeypatch.setattr(bridges_api, "_corpus_openalex_map",
                        lambda: ({}, {}, {}, 0))
    owner = progress.start("Importing papers", ["Reading PDFs"])
    owner.step("Reading PDFs", "mine", 2, 5)
    bridges_api.compute_bridges_now()               # wants its own job, is refused
    s = progress.snapshot()
    assert s["job"] == "Importing papers" and s["detail"] == "mine"
    assert s["finished"] is False
