"""The two derived-data caches, and their invalidation.

Added 2026-09-17. Measured on a 590-summary corpus, every list
endpoint re-read and re-parsed the WHOLE corpus on every request:
`parse_frontmatter` was 76% of server time (8730 parses across 9
requests where 590 would do), and once that was cached
`parse_ref_line` took over at ~31,870 reference lines per request.

Two caches now sit in front of that work:

  * `_api_common._read_summary` — parsed frontmatter + body, validated
    on (mtime_ns, size).
  * `citations.build_index` — the whole citation index, memoised on a
    (count, newest mtime, total size) fingerprint of summaries/.

A cache that returns stale data is worse than the cost it saves, so
almost every test here is an INVALIDATION test. The speed itself is not
asserted — timings are machine-dependent and would make the suite
flaky; what is asserted is that the work is actually skipped, by
counting calls.
"""
from __future__ import annotations

import time

import pytest


def _write(corpus_dir, slug, title="A Paper", doi="10.1000/x", refs=""):
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        f"---\ntitle: {title}\nyear: 2020\nauthor: Test, A.\ndoi: {doi}\n---\n\n"
        f"## References\n{refs}\n", encoding="utf-8")


# ---------- summary cache: invalidation ----------

def test_an_edited_summary_is_re_read(client, corpus_dir):
    """Catches: caching without checking whether the file changed.

    A re-extract rewrites the .md. If the cache never revalidates, the
    UI keeps showing the old title until the app restarts — data loss
    in appearance, with nothing in the logs."""
    _write(corpus_dir, "a-2020", title="Before")
    assert client.get("/api/papers").get_json()[0]["title"] == "Before"
    _write(corpus_dir, "a-2020", title="After The Edit")
    assert client.get("/api/papers").get_json()[0]["title"] == "After The Edit"


def test_a_same_size_edit_is_re_read(client, corpus_dir):
    """Catches: validating on mtime alone, or on size alone.

    Two separate near-misses. Size alone misses any edit that keeps the
    byte count. mtime alone is safe in principle but depends on the
    filesystem's clock resolution; a rewrite inside the same tick would
    serve stale content. The pair is what makes this reliable."""
    _write(corpus_dir, "a-2020", title="AAAAAAAA")
    before = (corpus_dir / "summaries" / "a-2020.md").stat().st_size
    assert client.get("/api/papers").get_json()[0]["title"] == "AAAAAAAA"

    _write(corpus_dir, "a-2020", title="BBBBBBBB")
    assert (corpus_dir / "summaries" / "a-2020.md").stat().st_size == before, (
        "fixture bug: the two writes must be the same size")
    assert client.get("/api/papers").get_json()[0]["title"] == "BBBBBBBB"


def test_a_deleted_summary_disappears_and_leaves_no_cache_entry(client, corpus_dir):
    """Catches: serving a paper that no longer exists, and leaking its
    cache entry forever.

    Slug canonicalisation on re-extract renames files, so deletions are
    not rare. An unbounded cache would also grow for the life of the
    process."""
    import _api_common
    _write(corpus_dir, "a-2020")
    _write(corpus_dir, "b-2021")
    assert len(client.get("/api/papers").get_json()) == 2

    (corpus_dir / "summaries" / "b-2021.md").unlink()
    assert len(client.get("/api/papers").get_json()) == 1
    assert not any(k.endswith("b-2021.md") for k in _api_common._SUMMARY_CACHE), (
        "cache still holds an entry for a deleted summary")


def test_a_new_summary_appears(client, corpus_dir):
    """Catches: caching the DIRECTORY LISTING as well as the files.

    Adding a paper must show up on the next request — Corpus scans the
    inbox and writes summaries while the app is running."""
    _write(corpus_dir, "a-2020")
    assert len(client.get("/api/papers").get_json()) == 1
    _write(corpus_dir, "b-2021")
    assert len(client.get("/api/papers").get_json()) == 2


# ---------- summary cache: the work is actually skipped ----------

def test_a_repeat_request_does_not_re_parse(client, corpus_dir, monkeypatch):
    """Catches: a cache that stores but never hits — the whole point.

    Counting parses rather than timing: a timing assertion would be
    flaky on a loaded machine, and would still pass if the cache were
    merely 'usually fast'."""
    import _api_common
    calls = []
    real = _api_common.parse_frontmatter
    monkeypatch.setattr(_api_common, "parse_frontmatter",
                        lambda t: (calls.append(1), real(t))[1])
    for s in ("a-2020", "b-2021", "c-2022"):
        _write(corpus_dir, s)

    client.get("/api/papers")
    first = len(calls)
    assert first >= 3, "fixture bug: the first request should parse every summary"
    client.get("/api/papers")
    client.get("/api/authors")
    assert len(calls) == first, (
        f"re-parsed {len(calls) - first} summaries that had not changed")


def test_mutating_a_returned_dict_cannot_corrupt_the_cache(client, corpus_dir):
    """Catches: handing out the cached dict itself.

    No caller mutates frontmatter today, but one that did would poison
    every later reader in the process, and the symptom would appear in
    an unrelated endpoint."""
    import _api_common
    from _paths import summaries_dir
    _write(corpus_dir, "a-2020", title="Original")

    md = summaries_dir() / "a-2020.md"
    _api_common._fm_dict(md)                     # 1st call: cache MISS

    # Mutate the result of a cache HIT specifically. An earlier version
    # of this test mutated the miss result, which is copied on the
    # store path anyway — so removing the copy from the HIT path went
    # undetected through a full mutation run.
    hit = _api_common._fm_dict(md)
    hit["title"] = "MUTATED"
    hit["injected"] = True

    third = _api_common._fm_dict(md)
    assert third["title"] == "Original"
    assert "injected" not in third


# ---------- citation index memo ----------

def test_the_index_is_rebuilt_when_a_paper_is_added(client, corpus_dir):
    """Catches: memoising the citation index on nothing, or on a
    fingerprint that misses new files.

    `citations.py` documents that links are derived and never stored so
    that adding a paper updates every affected summary's links with no
    repair pass. A stale memo silently breaks that promise."""
    _write(corpus_dir, "a-2020", doi="10.1000/aaa")
    assert client.get("/api/citations").get_json()["totals"]["papers"] == 1
    _write(corpus_dir, "b-2021", doi="10.1000/bbb")
    assert client.get("/api/citations").get_json()["totals"]["papers"] == 2


def test_the_index_is_rebuilt_when_a_papers_references_change(client, corpus_dir):
    """Catches: a fingerprint that counts files but ignores their
    content.

    This is the case that matters most: editing one summary's
    References section changes the EDGES without changing the paper
    count. A count-only fingerprint would keep serving the old graph."""
    _write(corpus_dir, "a-2020", doi="10.1000/aaa")
    _write(corpus_dir, "b-2021", doi="10.1000/bbb")
    assert client.get("/api/citations").get_json()["totals"]["edges"] == 0

    # Corpus's own reference-line format: `- **[<label>]** — DOI: <doi>`.
    # An earlier draft appended "— in_corpus: true", which is PAPER
    # MACHINE's format — zero of Corpus's 2216 real ref lines carry it.
    # The parser correctly yielded no DOI for the invented shape, and I
    # nearly went looking for a parser bug that did not exist.
    _write(corpus_dir, "a-2020", doi="10.1000/aaa",
           refs="- **[B 2021 Some Paper]** — DOI: 10.1000/bbb\n")
    g = client.get("/api/citations").get_json()
    assert g["totals"]["edges"] == 1, "editing a reference list did not rebuild the index"
    assert ["a-2020", "b-2021"] in [list(e) for e in g["edges"]]


def test_the_index_is_rebuilt_when_a_paper_is_removed(client, corpus_dir):
    """Catches: a fingerprint that only ever grows."""
    _write(corpus_dir, "a-2020", doi="10.1000/aaa")
    _write(corpus_dir, "b-2021", doi="10.1000/bbb")
    assert client.get("/api/citations").get_json()["totals"]["papers"] == 2
    (corpus_dir / "summaries" / "b-2021.md").unlink()
    assert client.get("/api/citations").get_json()["totals"]["papers"] == 1


def test_an_unchanged_corpus_does_not_rebuild_the_index(client, corpus_dir, monkeypatch):
    """Catches: a memo that never hits, leaving the 31,870-ref-lines-
    per-request cost in place while adding fingerprint work on top."""
    import citations
    builds = []
    real = citations._build_index_uncached
    monkeypatch.setattr(citations, "_build_index_uncached",
                        lambda: (builds.append(1), real())[1])
    _write(corpus_dir, "a-2020", doi="10.1000/aaa")

    client.get("/api/citations")
    assert len(builds) == 1
    client.get("/api/citations")
    client.get("/api/citations")
    assert len(builds) == 1, f"index rebuilt {len(builds)} times for an unchanged corpus"


def test_a_same_mtime_different_size_rewrite_is_re_read(client, corpus_dir):
    """Catches: validating the summary cache on mtime alone.

    Filesystem timestamps are not infinitely fine-grained, and Corpus
    writes summaries in tight loops (a scan processes an inbox of PDFs
    back to back). Two writes can land on the same mtime. The size is
    the half of the pair that catches it.

    Forced with os.utime rather than hoping for a fast enough machine,
    so the test is deterministic."""
    import os
    from _paths import summaries_dir
    md = summaries_dir() / "a-2020.md"

    _write(corpus_dir, "a-2020", title="Short")
    st = md.stat()
    assert client.get("/api/papers").get_json()[0]["title"] == "Short"

    _write(corpus_dir, "a-2020", title="A Considerably Longer Title Than Before")
    os.utime(md, ns=(st.st_atime_ns, st.st_mtime_ns))   # pin mtime back
    assert md.stat().st_mtime_ns == st.st_mtime_ns, "fixture bug: mtime not pinned"

    assert client.get("/api/papers").get_json()[0]["title"] == (
        "A Considerably Longer Title Than Before")


def test_a_same_size_reference_edit_rebuilds_the_index(client, corpus_dir):
    """Catches: a citation fingerprint that ignores mtime.

    Correcting a typo in a DOI usually keeps the byte count identical —
    "10.1000/bbb" to "10.1000/bbc" is the same length. Count and total
    size are both unchanged, so mtime is the only signal that the graph
    must be rebuilt."""
    _write(corpus_dir, "a-2020", doi="10.1000/aaa",
           refs="- **[B 2021 Some Paper]** — DOI: 10.1000/zzz\n")
    _write(corpus_dir, "b-2021", doi="10.1000/bbb")
    assert client.get("/api/citations").get_json()["totals"]["edges"] == 0

    before = (corpus_dir / "summaries" / "a-2020.md").stat().st_size
    _write(corpus_dir, "a-2020", doi="10.1000/aaa",
           refs="- **[B 2021 Some Paper]** — DOI: 10.1000/bbb\n")
    assert (corpus_dir / "summaries" / "a-2020.md").stat().st_size == before, (
        "fixture bug: the edit must keep the file the same size")

    assert client.get("/api/citations").get_json()["totals"]["edges"] == 1, (
        "a same-size reference edit did not rebuild the citation index")


def test_a_same_mtime_size_change_rebuilds_the_index(client, corpus_dir):
    """Catches: a citation fingerprint that ignores total size.

    The mirror of the test above: when two writes share an mtime, the
    summed byte count is what notices. Forced with os.utime."""
    import os
    _write(corpus_dir, "a-2020", doi="10.1000/aaa")
    _write(corpus_dir, "b-2021", doi="10.1000/bbb")
    assert client.get("/api/citations").get_json()["totals"]["edges"] == 0

    md = corpus_dir / "summaries" / "a-2020.md"
    st = md.stat()
    _write(corpus_dir, "a-2020", doi="10.1000/aaa",
           refs="- **[B 2021 Some Paper]** — DOI: 10.1000/bbb\n")
    os.utime(md, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert md.stat().st_mtime_ns == st.st_mtime_ns, "fixture bug: mtime not pinned"

    assert client.get("/api/citations").get_json()["totals"]["edges"] == 1, (
        "a same-mtime size change did not rebuild the citation index")
