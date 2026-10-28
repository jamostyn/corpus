"""The note link picker can sort every kind of thing it links to.

Requirement (2026-09-28): the note link picker can sort by any of the
tab's options, for example most recently added papers first.

Sort options are declared once per tab (`sorts` on its MODES entry) and
used by both the Papers sidebar and the picker via src/sorting.js; the
sort itself is tested in tests/src/sorting.test.js. These pin the wiring.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"


def _modes_entries() -> list[str]:
    app = (_SRC / "app.js").read_text(encoding="utf-8")
    block = app[app.index("const MODES = ["):app.index("const MODES_BY_ID")]
    return [e for e in re.split(r"\n  \{ id: ", block)[1:]]


def test_every_linkable_type_declares_sort_options():
    """Catches the "for all the options" part regressing: a new linkable
    tab added without `sorts` would show the picker with no Sort by."""
    missing = [e.split('"')[1] for e in _modes_entries()
               if "linkAttr:" in e and "sorts: [" not in e]
    assert not missing, f"linkable tabs with no sort options: {missing}"


def test_papers_offer_date_added_newest_first():
    """Catches losing the date-added, newest-first option."""
    papers = next(e for e in _modes_entries() if e.startswith('"papers"'))
    assert re.search(r'key: "added_at".*defaultDir: "desc"', papers)


def test_the_picker_sorts_before_capping_the_list():
    """Catches sorting after `.slice(0, 200)`: "newest first" would then
    only reorder whichever 200 rows came first, and the newest paper in
    a 1,000-paper corpus could be missing entirely."""
    notes = (_SRC / "notes.js").read_text(encoding="utf-8")
    body = notes[notes.index("const renderResults = () => {"):]
    body = body[:body.index("resultsEl.innerHTML = items.map")]
    assert body.index("Sorting.sortRows(") < body.index(".slice(0, 200)")


def test_the_sidebar_uses_the_shared_sort_and_menu():
    """Catches a second copy of the paper sort creeping back (it was
    `_sortPapers` until 2026-09-28) or the sidebar menu being hard-coded
    again, so it and the picker offer different options."""
    app = (_SRC / "app.js").read_text(encoding="utf-8")
    html = (_SRC / "index.html").read_text(encoding="utf-8")
    assert "_sortPapers" not in app
    assert "Sorting.sortRows(MODES_BY_ID.papers.sorts" in app
    assert "<option" not in html[html.index('id="papers-sort-field"'):html.index("papers-sort-dir")]
