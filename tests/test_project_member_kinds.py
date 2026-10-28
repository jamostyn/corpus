"""Projects: the JS↔Python agreement on what a project can contain.

Two independent lists have to agree on the member kinds:

  * `src/app.js` — the MODES entries declaring `memberKind`, which
    derive `window.PROJECT_MEMBER_MODES` (the picker, the detail
    sections and the sidebar count line all iterate it).
  * `python/projects_api.py` — `_PROJECT_MEMBER_KINDS`, which the
    /members endpoint validates against.

Drift here is silent in both directions: a kind only in Python is an
endpoint accepting members nothing can render, and a kind only in JS is
a picker whose every click 400s. Same treatment as the `linkAttr`
parity test next door.
"""
from __future__ import annotations

import re
from pathlib import Path

from projects_api import _PROJECT_MEMBER_KINDS

_APP_JS = Path(__file__).resolve().parent.parent / "src" / "app.js"
_PROJECTS_JS = Path(__file__).resolve().parent.parent / "src" / "projects.js"


def _app() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def _js_member_kinds() -> list[str]:
    """Every `memberKind: "..."` declared on a MODES entry."""
    return re.findall(r'memberKind:\s*"([a-z]+)"', _app())


def test_js_and_python_agree_on_member_kinds():
    """Catches: adding a member kind on one side only.

    Add `memberKind: "author"` to a MODES entry and the project detail
    grows an "Add authors…" button whose every click 400s on
    `bad_member_kind`. Add it to Python only and the endpoint stores
    members the UI has no section to display."""
    assert sorted(_js_member_kinds()) == sorted(_PROJECT_MEMBER_KINDS)


def test_every_member_kind_declares_the_nouns_the_ui_renders():
    """Catches: declaring `memberKind` without `memberNoun` /
    `memberNounPlural`.

    `_projectCountLine` and the detail section headers interpolate
    those directly. Missing ones render the literal string "undefined"
    in the sidebar under every project — visible, but only once the
    tab is opened with real data."""
    src = _app()
    for kind in _PROJECT_MEMBER_KINDS:
        m = re.search(r'memberKind:\s*"' + kind + r'"', src)
        assert m, f"no MODES entry declares memberKind {kind!r}"
        # Scan this MODES entry only — from its `{ id: "` to the next.
        # Brace-matching is not viable here: entries contain arrow
        # functions and template literals (see test_note_link_attrs.py).
        start = src.rfind('{ id: "', 0, m.start())
        end = src.find('{ id: "', m.end())
        entry = src[start:end if end != -1 else len(src)]
        assert "memberNoun:" in entry, f"{kind} has no memberNoun"
        assert "memberNounPlural:" in entry, f"{kind} has no memberNounPlural"


def test_every_member_kind_has_a_loadable_list_for_the_picker():
    """Catches: a member kind on a mode the picker cannot populate.

    `_openMemberPicker` reads `state[mode.stateKey]` and calls
    `mode.load()` when it is empty. A memberKind on an entry without
    both leaves the picker permanently showing "Nothing to add" — a
    dead button with no error."""
    src = _app()
    for kind in _PROJECT_MEMBER_KINDS:
        m = re.search(r'memberKind:\s*"' + kind + r'"', src)
        start = src.rfind('{ id: "', 0, m.start())
        end = src.find('{ id: "', m.end())
        entry = src[start:end if end != -1 else len(src)]
        assert "stateKey:" in entry, f"{kind} has no stateKey"
        assert "load:" in entry, f"{kind} has no load function"


def test_the_picker_reuses_mode_labels_rather_than_copying_them():
    """Catches: projects.js growing its own copy of "how a paper is
    named in a list".

    Papers already carry `linkLabel` (used by the notes entity-link
    picker). If the project picker hard-coded `${r.author} (${r.year})`
    instead, the two pickers would show the same paper differently and
    drift further on every tweak."""
    src = _PROJECTS_JS.read_text(encoding="utf-8")
    assert "mode.memberLabel || mode.linkLabel" in src, (
        "_memberLabel must fall back to the mode's existing linkLabel")
    assert src.count("function _memberLabel(") == 1


def test_member_rows_do_not_rely_on_the_deep_link_delegation():
    """Catches: emitting `data-open-<kind>` for project member rows.

    app.js's deep-link handler iterates LINKABLE_MODES, which contains
    papers but NOT notes — a note is not a link target for the notes
    editor. A note row emitting `data-open-note` therefore renders as a
    link that silently does nothing when clicked. Going through the
    mode's own `select` works for every member kind by construction.

    This was live for about ten minutes while the feature was built;
    it was caught writing the CODE_MAP row, not by a test, which is
    why there is now a test."""
    src = _PROJECTS_JS.read_text(encoding="utf-8")
    # Bound to renderProjectDetail ONLY, and strip `//` comments: the
    # comment inside _wireProjectDetail explains why data-open-* is
    # wrong, and an unbounded search matches that prose instead of the
    # code. (Third time this trap has bitten in this repo — see
    # test_mode_action_buttons._strip_js_comments.)
    body = src[src.index("function renderProjectDetail("):
               src.index("function _wireProjectDetail(")]
    body = "\n".join(re.sub(r"//.*$", "", ln) for ln in body.split("\n"))
    assert "data-open-" not in body, (
        "member rows must not use the data-open-* deep-link delegation")
    assert "data-member-kind" in body and "data-member-id" in body
    wire = src[src.index("function _wireProjectDetail("):]
    assert "switchMode(mode.id)" in wire and "mode.select(" in wire, (
        "member clicks must switch tab and select through the mode itself")
