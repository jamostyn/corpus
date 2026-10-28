"""Concurrent cold reads of a summary share ONE read.

2026-09-21, after a restart: three /api/papers requests arrived together
(the main window, a popped-out note, a reload). Each walked ~620 cold
summaries on its own and all three finished after 218-251s. ~/Documents
is iCloud-synced, so a file's first read is slow and tripling the reads
tripled the wait. Meanwhile the popped-out note, which waited for that
list before fetching itself, sat blank the whole time.
"""
from __future__ import annotations

import threading
import time

import _api_common


def test_concurrent_misses_read_the_file_once(corpus_dir, monkeypatch):
    """Catches removing the miss-path lock: N threads racing on a cold
    file would each read and parse it."""
    md = corpus_dir / "summaries" / "slow-2020.md"
    md.parent.mkdir(exist_ok=True)
    md.write_text("---\ntitle: Slow\nyear: 2020\n---\nbody\n")
    _api_common.clear_summary_cache()

    reads = []
    real = _api_common.parse_frontmatter

    def slow_parse(text):
        reads.append(1)
        time.sleep(0.05)          # a cold, slow first read
        return real(text)

    monkeypatch.setattr(_api_common, "parse_frontmatter", slow_parse)
    threads = [threading.Thread(target=_api_common._read_summary, args=(md,))
               for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(reads) == 1, f"{len(reads)} threads each read the cold file"


def test_a_cache_hit_does_not_wait_on_the_lock(corpus_dir):
    """Catches taking the lock on every read, which would serialise the
    warm path — every request would queue behind any one cold miss."""
    md = corpus_dir / "summaries" / "warm-2020.md"
    md.parent.mkdir(exist_ok=True)
    md.write_text("---\ntitle: Warm\nyear: 2020\n---\n")
    _api_common.clear_summary_cache()
    assert _api_common._read_summary(md) is not None     # warm it
    with _api_common._READ_LOCK:                          # hold the lock
        got = _api_common._read_summary(md)               # must not block
    assert got and got[0]["title"] == "Warm"


def test_the_popped_out_note_does_not_wait_for_the_papers_list():
    """Catches re-adding `await loadPapers()` before the note loads.

    The note window only needs the list for panel titles; waiting on it
    left the pop-out blank for four minutes."""
    import re
    from pathlib import Path
    app = (Path(__file__).resolve().parent.parent / "src" / "app.js").read_text()
    branch = app[app.index('if (detached.kind === "note") {'):]
    branch = branch[:branch.index("} else {")]
    code = "\n".join(re.sub(r"//.*$", "", l) for l in branch.split("\n"))
    assert "await loadPapers()" not in code
    assert "await openDetachedNote" in code
