"""Newest-added first, everywhere there is a sort (2026-10-29).

Authors, institutions and journals have no date of their own; their
"Date added" is the newest `added_at` among their papers. The default
sort for every sortable list comes from one place (app.js
`defaultSort`), so the Papers sidebar and the note link picker agree.
"""
from __future__ import annotations

import re
from pathlib import Path

from test_aggregators import _PAPER_A, _PAPER_B

_ROOT = Path(__file__).resolve().parent.parent


def _seed(corpus_dir):
    a = _PAPER_A.replace("schema_version: 1", "schema_version: 1\nadded_at: 2026-01-05T10:00:00Z")
    b = _PAPER_B.replace("schema_version: 1", "schema_version: 1\nadded_at: 2026-09-01T08:00:00Z")
    (corpus_dir / "summaries" / "kahneman-1979.md").write_text(a)
    (corpus_dir / "summaries" / "tversky-1981.md").write_text(b)


def test_entities_carry_the_date_their_newest_paper_was_added(client, corpus_dir):
    """Catches an author / institution / journal row reporting its OLDEST
    paper's date (or none), which would sort them wrongly."""
    _seed(corpus_dir)
    authors = {r["key"]: r for r in client.get("/api/authors").get_json()}
    assert authors["kahneman-daniel"]["added_at"] == "2026-09-01T08:00:00Z"   # on both papers
    insts = {r["name"]: r for r in client.get("/api/institutions").get_json()}
    assert insts["Stanford University"]["added_at"] == "2026-09-01T08:00:00Z"
    journals = {r["name"]: r for r in client.get("/api/journals").get_json()}
    assert journals["Econometric Society"]["added_at"] == "2026-01-05T10:00:00Z"


def test_a_missing_date_never_wins():
    """Catches "unknown" or "" outranking a real date in the max."""
    import entities_api
    assert entities_api.latest_added(["", "unknown", "2025-01-01T00:00:00Z"]) == "2025-01-01T00:00:00Z"
    assert entities_api.latest_added(["", "unknown"]) == ""


def test_every_list_that_can_sort_offers_date_added():
    """Catches a sortable list without the default key — it would quietly
    open alphabetical while the others open newest first."""
    app = (_ROOT / "src" / "app.js").read_text(encoding="utf-8")
    starts = [(m.group(1), m.start()) for m in re.finditer(r'\{ id: "(\w+)"', app)]
    entries = {mid: app[a:(starts[i + 1][1] if i + 1 < len(starts) else len(app))]
               for i, (mid, a) in enumerate(starts)}
    for mode in ("papers", "authors", "institutions", "journals", "documents"):
        sorts = entries[mode].split("sorts: [", 1)[1].split("\n    ],", 1)[0]
        assert re.search(r'key: "added_at".*defaultDir: "desc"', sorts), mode


def test_the_sidebar_and_the_link_picker_take_the_same_default():
    """Catches the two places drifting apart: the Papers sidebar seeded
    from its own literal while the picker used the first sort."""
    app = (_ROOT / "src" / "app.js").read_text(encoding="utf-8")
    notes = (_ROOT / "src" / "notes.js").read_text(encoding="utf-8")
    assert "state.papersSort = (({ key, dir }) => ({ field: key, dir }))(defaultSort(MODES_BY_ID.papers));" in app
    assert 'papersSort:  null,' in app
    assert "return defaultSort(m);" in notes
