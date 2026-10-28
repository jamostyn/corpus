"""Smoke tests for /api/scan — verifies the two-pass shape.

/api/scan now processes `inbox/*.pdf` first, then backfills any
un-summarized PDFs in `papers/`. Response has:
  * inbox_processed: [ {filename, status, slug?, ...} ]
  * extracted:       [slug, ...]   (papers/ backfill)
  * skipped:         int

We can't run a real extract without a real PDF + network, so these
tests exercise only the empty-corpus + no-inbox cases + response
shape. The actual extract pipeline is covered by manual click-through.
"""


def test_scan_empty_returns_expected_shape(client, corpus_dir):
    """Fresh corpus, nothing in inbox, nothing in papers: 200 with the
    documented shape and every field zeroed/empty.

    `added` joined the response on 2026-09-17: the frontend and the
    auto-bridge hook both need to know whether anything actually
    landed, and deriving it by summing `inbox_processed` statuses in
    the client would be a second copy of that rule."""
    r = client.post("/api/scan")
    assert r.status_code == 200
    body = r.get_json()
    assert body == {
        "inbox_processed": [],
        "extracted":       [],
        "skipped":         0,
        "added":           0,
    }


def test_scan_skips_papers_that_already_have_summaries(client, corpus_dir):
    """A PDF-and-summary pair already present in papers/ + summaries/
    counts as `skipped`, not `extracted` — the backfill pass only
    fires when a summary is missing."""
    # Create a fake PDF + matching summary (bytes don't matter — /api/scan
    # only checks whether the .md exists).
    (corpus_dir / "papers"    / "kahneman-1979.pdf").write_bytes(b"%PDF-1.4\n%fake\n")
    (corpus_dir / "summaries" / "kahneman-1979.md" ).write_text(
        "---\ntitle: fake\nauthor: fake\nyear: 1979\nkind: article\n---\n"
    )
    r = client.post("/api/scan")
    assert r.status_code == 200
    body = r.get_json()
    assert body["skipped"] == 1
    assert body["extracted"] == []
    assert body["inbox_processed"] == []
