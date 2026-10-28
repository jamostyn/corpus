"""Detached-window layout rules.

A popped-out window exists to read the PDF, so header chrome is pixels
of paper the user doesn't get. Bug 20260827-122449 reported the header
as too tall; the fixes are CSS overrides scoped to `body.corpus-detached`.

NO RENDERING HAPPENS IN THIS SUITE, so the actual height is not
measured here — there is no layout engine available. What these tests
pin is the set of rules whose removal would silently undo the fix, plus
one correctness rule (a dead control staying visible) that is a bug
independent of height.
"""
from __future__ import annotations

import re
from pathlib import Path

_CSS = Path(__file__).resolve().parent.parent / "src" / "styles.css"
_JS = Path(__file__).resolve().parent.parent / "src" / "paper-detail.js"


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _rule_body(selector: str) -> str:
    """The declaration block of the rule whose selector LIST contains
    `selector`. Raises if there is no such rule.

    Two traps this has to avoid, both hit while writing these tests:

    1. A plain substring search for `.pd-head-actions` also matches
       inside `body.corpus-detached .pd-head-actions`, making the base
       and override rules indistinguishable — which is the exact
       distinction being tested. So each comma-separated selector is
       compared whole.
    2. Requiring `selector` to be followed by `{` misses GROUPED rules
       (`A,\\n B { … }`) and silently returns nothing, which turns any
       `assert "none" not in body` into a tautology that passes however
       the CSS changes. A mutation that hid the source path survived
       because of exactly that, so this now raises instead of returning
       '' when the rule is absent.
    """
    for block in re.finditer(r"([^{}]+)\{([^}]*)\}", _css()):
        sels = [x.strip() for x in block.group(1).split(",")]
        # Selector lists can carry a preceding comment/newline; compare
        # against the last line of each entry.
        sels = [x.splitlines()[-1].strip() if x.splitlines() else x for x in sels]
        if selector in sels:
            return block.group(2)
    raise AssertionError(f"no CSS rule found with selector {selector!r}")


def test_pop_out_button_is_hidden_in_a_detached_window():
    """Catches: the Pop out control reappearing in the popped-out window.

    Clicking it there re-focuses the window you are already looking at —
    a control that does nothing. This is a correctness bug, not a
    cosmetic one, and it is independent of the header height."""
    body = _rule_body("body.corpus-detached #btn-pop-out")
    assert "display" in body and "none" in body, (
        "Pop out must be hidden when already detached")


def test_the_button_id_the_css_hides_actually_exists_in_the_markup():
    """Catches: the CSS hiding an id the renderer no longer emits.

    A rename in paper-detail.js would leave a selector matching nothing,
    and the dead Pop out control would quietly come back."""
    assert 'id="btn-pop-out"' in _JS.read_text(encoding="utf-8"), (
        "paper-detail.js no longer emits #btn-pop-out; update the "
        "detached-mode CSS to match")


def test_detached_action_buttons_lay_out_horizontally():
    """Catches: losing the single biggest height saving.

    `.pd-head-actions` is `flex-direction: column` by default, which
    stacks four buttons at roughly 146px. Turning that into a row is
    what reclaims most of the header."""
    body = _rule_body("body.corpus-detached .pd-head-actions")
    assert "row" in body, "detached actions must be a row, not a column"


def test_the_default_action_layout_is_still_a_column():
    """Catches: 'fixing' this by flipping the shared rule instead of
    overriding it in detached mode.

    The docked pane sits beside a 340px sidebar; a horizontal row of
    four buttons squeezes the title there. The override is deliberately
    detached-only, and a change to the base rule would regress the main
    window's layout with no test pointing at it."""
    base = _rule_body(".pd-head-actions")
    assert "column" in base, (
        "the shared .pd-head-actions rule must stay a column — compaction "
        "belongs in the body.corpus-detached override")


def test_detached_metadata_rows_collapse_onto_one_line():
    """Catches: the three reference rows (source file, summary, last
    updated) going back to their own lines, which costs ~55px.

    They are kept rather than hidden: the source path is how the user
    knows WHICH pdf they have when extraction fell back to the slug."""
    css = _css()
    assert "body.corpus-detached .pd-source-file" in css
    assert "body.corpus-detached .paper-detail .pd-updated" in css


def test_detached_still_renders_the_source_path_at_all():
    """Catches: someone reducing height by deleting the source-file line
    outright. The comment on `.pd-source-file` says it is 'always
    visible' for a reason — losing it makes a slug-titled paper
    unidentifiable."""
    body = _rule_body("body.corpus-detached .pd-source-file")
    assert "none" not in body, (
        "the source path must be compacted, not hidden")
