"""Pickers always show the corpus as it is now, in every window.

Jack, 2026-09-29: "when a note is popped out, the link paper feature
doesnt update when new papers are added to the corpus". The note link
picker and the project member picker loaded a list only when it was
empty; only the window that ran an import reloaded its papers, so a
popped-out note kept the list from when it opened.

`app.js::fetchModeList` refetches from each tab's `listUrl`; its
behaviour is tested in tests/src/fetch-mode-list.test.js. These pin the
wiring and keep each list URL written once.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"


def _modes_entries() -> list[str]:
    app = (_SRC / "app.js").read_text(encoding="utf-8")
    block = app[app.index("const MODES = ["):app.index("const MODES_BY_ID")]
    return re.split(r"\n  \{ id: ", block)[1:]


def test_every_linkable_tab_declares_its_list_url():
    """Catches a new linkable tab without `listUrl`: its picker would fall
    back to load-if-empty and go stale exactly like the reported bug."""
    missing = [e.split('"')[1] for e in _modes_entries()
               if "linkAttr:" in e and "listUrl:" not in e]
    assert not missing, f"linkable tabs with no listUrl: {missing}"


def test_list_urls_are_written_only_on_the_modes_entries():
    """Catches a loader hard-coding its endpoint again — the loader and
    the picker could then read two different lists."""
    urls = re.findall(r'listUrl: "([^"]+)"', (_SRC / "app.js").read_text(encoding="utf-8"))
    assert len(urls) >= 5
    for f in _SRC.glob("*.js"):
        text = f.read_text(encoding="utf-8")
        for u in urls:
            assert f'api("{u}")' not in text, f"{f.name} hard-codes {u}"


def test_the_note_link_picker_refetches_every_time_it_shows_a_type():
    """Catches the refresh being guarded by an emptiness check again (the
    exact bug), or a late response drawing over another type."""
    notes = (_SRC / "notes.js").read_text(encoding="utf-8")
    body = notes[notes.index("const selectType = async (m) => {"):]
    body = body[:body.index("typesEl.innerHTML")]
    call = body.index("await fetchModeList(m)")
    assert "if (!(state[m.stateKey]" not in body[:call]
    assert "active === m && _entityPicker === overlay" in body[call:]


def test_the_project_member_picker_refetches_too():
    """Catches the member picker keeping load-if-empty, so a paper
    imported from another window could not be added to a project."""
    projects = (_SRC / "projects.js").read_text(encoding="utf-8")
    body = projects[projects.index("async function _openMemberPicker"):]
    body = body[:body.index("_pickerShell(")]
    assert "await fetchModeList(mode)" in body
    assert "mode.load()" not in body
