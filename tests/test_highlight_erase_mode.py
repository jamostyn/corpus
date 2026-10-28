"""Erase mode in the PDF highlight layer — structural invariants.

`src/vendor/pdfjs/web/corpus-highlights.js` is an IIFE that runs inside
the PDF.js viewer iframe. It returns early without a `?file=/pdf/<slug>`
param, and every code path needs a live text layer, a selection, and
PDF.js's page DOM. The Node `vm` harness in tests/src/ cannot supply any
of that, so there is NO behavioural coverage of this file.

What IS mechanically checkable is the set of invariants whose violation
is silent rather than loud. Each test below pins one of those. They are
source-level assertions, the same technique
`tests/test_script_load_order.py` uses against index.html.

The behavioural claims — that dragging actually erases, that the confirm
appears — are verified by hand only.
"""
from __future__ import annotations

import re
from pathlib import Path

_JS = (Path(__file__).resolve().parent.parent
       / "src" / "vendor" / "pdfjs" / "web" / "corpus-highlights.js")
_CSS = _JS.with_suffix(".css")


def _src() -> str:
    return _JS.read_text(encoding="utf-8")


def test_erase_mode_keeps_the_text_layer_interactive():
    """Catches: `refreshInteractionMode` forgetting eraseMode.

    Note Mode sets `body.corpus-note-only`, which flips pointer-events
    OFF for the text layer and ON for the highlight rects. Erase mode
    drag-selects TEXT, so if eraseMode is missing from that condition,
    arming the eraser while Note Mode is on produces a tool that cannot
    select anything — it looks broken with no error."""
    m = re.search(r"const noteOnly = ([^;]+);", _src())
    assert m, "refreshInteractionMode no longer computes `noteOnly`"
    cond = m.group(1)
    assert "state.eraseMode" in cond, (
        "eraseMode must suppress corpus-note-only or the eraser cannot "
        f"select text; got: {cond}")


def test_erase_takes_precedence_inside_handle_selection():
    """Catches: the erase branch being dropped or placed after the
    highlight-mode guard.

    `handleSelection` returns early when `!state.highlightMode`. If the
    erase dispatch sits after that guard, the eraser silently does
    nothing whenever highlight mode is off — which is its normal
    state."""
    src = _src()
    body = src[src.index("function handleSelection()"):]
    erase_at = body.index("state.eraseMode")
    guard_at = body.index("if (!state.highlightMode) return;")
    assert erase_at < guard_at, (
        "the eraseMode dispatch must come BEFORE the highlightMode guard")


def test_erase_and_highlight_toggles_are_mutually_exclusive():
    """Catches: one toggle failing to switch the other off.

    Both modes act on the same drag. With both flags set, a single drag
    would hit whichever branch is checked first — the other mode's
    button stays lit while doing nothing, which reads as a dead
    control."""
    src = _src()
    assert "state.highlightMode && state.eraseMode" in src, (
        "the Highlight button must clear eraseMode")
    assert "state.eraseMode && state.highlightMode" in src, (
        "the Erase button must clear highlightMode")


def test_erasing_a_highlight_that_has_a_note_asks_first():
    """Catches: removing the confirm on note-carrying highlights.

    A note is user-authored prose and the data model cascades it with
    its highlight, so an unconfirmed erase destroys writing with no undo.
    The right-click removal path already confirms; the eraser must not
    be a silent way around that."""
    src = _src()
    fn = src[src.index("function eraseSelection()"):
             src.index("function handleSelection()")]
    assert "window.confirm" in fn, "eraseSelection lost its confirmation"
    assert "typeof h.note" in fn, (
        "the confirm must be gated on highlights that actually carry notes")


def test_eraser_does_not_confirm_when_no_notes_are_involved():
    """Catches: confirming on EVERY erase.

    The eraser exists because removal was too fiddly; a modal on every
    drag would make it as annoying as the path it replaces. The confirm
    must sit behind a `withNotes.length` check, not run unconditionally."""
    src = _src()
    fn = src[src.index("function eraseSelection()"):
             src.index("function handleSelection()")]
    assert re.search(r"if\s*\(\s*withNotes\.length\s*\)", fn), (
        "the confirm must be conditional on notes being present")


def test_erase_notifies_the_parent_so_note_cards_are_removed():
    """Catches: erasing a highlight but leaving its note card in the
    gutter. The parent shell renders note cards from the highlight list
    it receives via postMessage; without a notify, the card stays on
    screen anchored to a highlight that no longer exists.

    Asserts the GUARANTEE, not the call site. An earlier version of this
    test required `notifyParentHighlights()` to appear literally inside
    `eraseSelection`, and it broke when that call moved into the shared
    `commitHighlights` funnel even though the behaviour was unchanged —
    a test that fails on a behaviour-preserving refactor is testing the
    wrong thing."""
    src = _src()
    fn = src[src.index("function eraseSelection()"):
             src.index("function handleSelection()")]
    assert "commitHighlights(" in fn or "notifyParentHighlights()" in fn, (
        "eraseSelection must notify the parent, directly or via the funnel")
    funnel = src[src.index("function commitHighlights("):
                 src.index("function undoLast()")]
    assert "notifyParentHighlights()" in funnel, (
        "the funnel every mutation uses must notify the parent")


def test_selection_geometry_is_computed_in_one_place():
    """Catches: the erase path growing its own copy of the
    selection→rects→bounds logic.

    Design-doc §3 explains why rects must come from the text SPANS and
    not from `range.getClientRects()`. A second implementation would
    drift from that and produce subtly misaligned erase targets, so both
    paths go through the shared helpers."""
    src = _src()
    for helper in ("function resolveSelection(",
                   "function highlightsOverlapping("):
        assert src.count(helper) == 1, f"{helper} should be defined exactly once"
    # Both the subsume rule and the eraser must go through the shared
    # overlap query rather than filtering state.highlights themselves.
    #
    # This test used to also require `function boundsOf(`. That helper
    # was DELETED on 2026-09-09 when the overlap test moved from
    # bounding-box to rect-to-rect — it had no other caller. Asserting a
    # specific helper exists is testing the implementation; what matters
    # is that there is exactly one overlap query and both callers use it.
    assert src.count("highlightsOverlapping(") == 3, (
        "expected one definition plus exactly two call sites "
        "(handleSelection's subsume branch and eraseSelection)")


def test_erase_toggle_is_visually_distinct_from_the_other_toggles():
    """Catches: the destructive toggle sharing the amber `.toggled`
    styling used by Highlight and Note Mode. Three identical-looking lit
    buttons, one of which deletes, is a misclick waiting to happen."""
    css = _CSS.read_text(encoding="utf-8")
    assert "#corpusEraseBtn.toggled" in css, (
        "the Erase toggle needs its own active styling")
