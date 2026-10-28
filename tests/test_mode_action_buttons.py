"""The top-right action slot is MODES-driven, not a chain of if-elses.

`switchMode` shows one of two things in the top-right: the corpus-wide
Add PDFs / Scan pair, or the active mode's own action button. Before
2026-09-14 that was a hard-coded `const isNotes = (id === "notes")`.
Adding Projects would have made it a second hard-coded branch — the
exact shape of the four hard-coded deep-link branches that had to be
consolidated on 2026-08-27.

So a mode now declares `actionBtnId` and switchMode iterates. These
tests pin that, plus the HTML↔MODES agreement that a new tab depends
on: CLAUDE.md promises "adding a new tab = one array entry + matching
HTML", and that promise is only true if something checks the ids line
up.

Source-level assertions on app.js / index.html — switchMode needs a
live DOM and a Flask backend, so the vm harness cannot run it (see
TESTING.md § Known gaps).
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
_APP_JS = _SRC / "app.js"
_INDEX = _SRC / "index.html"


def _app() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def _strip_js_comments(src: str) -> str:
    """Drop `//` line comments.

    Without this, a test searching for a pattern in the CODE matches
    the prose EXPLAINING why that pattern is banned — which is exactly
    what happened when this file was written: the comment above the
    action-slot loop says the word `isNotes` while describing what it
    replaced, and the test failed against its own documentation."""
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.split("\n"))


def _html() -> str:
    return _INDEX.read_text(encoding="utf-8")


def _switch_mode() -> str:
    src = _app()
    start = src.index("function switchMode(")
    # Ends at the next top-level function declaration.
    end = src.index("\nfunction ", start + 1)
    return src[start:end]


def _mode_entries() -> list[str]:
    """Each MODES entry's source text, split on the `{ id: "` marker."""
    src = _app()
    block = src[src.index("const MODES = ["):src.index("\nconst MODES_BY_ID")]
    parts = re.split(r'(?=\{ id: ")', block)
    return [p for p in parts if p.strip().startswith('{ id: "')]


def _mode_field(entry: str, field: str) -> str | None:
    m = re.search(field + r':\s*"([A-Za-z0-9_-]+)"', entry)
    return m.group(1) if m else None


# ---------- The consolidation itself ----------------------------------

def test_switch_mode_does_not_name_a_specific_tab_for_the_action_slot():
    """Catches: re-introducing `id === "notes"` (or `=== "projects"`).

    A hard-coded branch works until the third mode wants an action
    button, at which point whoever adds it copies the pattern and the
    two fall out of step — one mode's button stays visible on another
    mode's tab."""
    fn = _switch_mode()
    action_block = _strip_js_comments(
        fn[fn.index("Top-right action buttons"):fn.index("Load / render the list")])
    for bad in ('=== "notes"', '=== "projects"', "isNotes", "isProjects"):
        assert bad not in action_block, (
            f"the action-slot logic names a specific mode ({bad!r}); "
            "it must iterate MODES and read `actionBtnId`")
    assert "actionBtnId" in action_block, (
        "the action slot must be driven by the MODES `actionBtnId` field")


def test_add_and_scan_hide_exactly_when_a_mode_owns_the_action_slot():
    """Catches: leaving Add PDFs / Scan visible on Notes or Projects.

    Both act on the corpus as a whole and are meaningless — and in
    Scan's case slow and surprising — while the user is writing a note
    or arranging a project."""
    fn = _switch_mode()
    assert re.search(r"addBtn\.hidden\s*=\s*Boolean\(activeActionBtn\)", fn), (
        "Add PDFs must hide whenever the active mode owns the action slot")
    assert re.search(r"scanBtn\.hidden\s*=\s*Boolean\(activeActionBtn\)", fn), (
        "Scan must hide whenever the active mode owns the action slot")


def test_every_declared_action_button_exists_in_the_html():
    """Catches: declaring `actionBtnId` with no matching element.

    `$("#" + id)` returns null and the guard skips it, so the mode
    silently has no way to create anything — the tab loads, looks
    right, and has no New button."""
    html = _html()
    ids = re.findall(r'actionBtnId:\s*"([A-Za-z0-9_-]+)"', _app())
    assert ids, "no mode declares an action button — did the field get renamed?"
    for bid in ids:
        assert f'id="{bid}"' in html, f"#{bid} declared in MODES but absent from index.html"


def test_action_buttons_start_hidden_so_papers_does_not_show_them():
    """Catches: shipping a mode's New button without `hidden`.

    Papers is the boot mode and owns no action button. switchMode only
    runs on a tab CHANGE, so a button that isn't hidden in the markup
    sits next to Add PDFs on first paint until the user switches tabs
    and back."""
    html = _html()
    for bid in re.findall(r'actionBtnId:\s*"([A-Za-z0-9_-]+)"', _app()):
        m = re.search(r'<button[^>]*id="' + bid + r'"[^>]*>', html)
        assert m, f"#{bid} not found in index.html"
        assert "hidden" in m.group(0), f"#{bid} must start hidden"


# ---------- The HTML↔MODES contract a new tab depends on ---------------

def test_every_mode_has_its_four_elements_in_the_html():
    """Catches: adding a MODES entry without the matching markup.

    switchMode does `$("#" + other.filterId).hidden = ...` for EVERY
    mode on every switch. One missing element throws, and the throw
    happens mid-loop — so tabs after it in the array never get hidden
    and two panes render on top of each other."""
    html = _html()
    for entry in _mode_entries():
        mid = _mode_field(entry, "id")
        for field in ("filterId", "listId", "detailId"):
            val = _mode_field(entry, field)
            assert val, f"mode {mid!r} has no {field}"
            assert f'id="{val}"' in html, (
                f"mode {mid!r} declares {field}={val!r}, absent from index.html")


def test_every_mode_has_a_tab_button():
    """Catches: a mode reachable only by arrow keys.

    The tab strip is hand-written markup; a MODES entry with no
    `data-tab` button is a pane nothing can navigate to."""
    html = _html()
    for entry in _mode_entries():
        mid = _mode_field(entry, "id")
        assert f'data-tab="{mid}"' in html, f"no tab button for mode {mid!r}"


def test_projects_is_registered_as_a_mode():
    """Catches: the Projects feature losing its MODES entry in a merge.

    Every other test here is generic over MODES, so deleting the entry
    would make them all pass with Projects simply gone."""
    ids = [_mode_field(e, "id") for e in _mode_entries()]
    assert "projects" in ids, f"projects mode missing; modes are {ids}"
