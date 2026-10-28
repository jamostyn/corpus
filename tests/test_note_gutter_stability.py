"""The note gutter must not rebuild itself while you are typing in it.

Bug, 2026-09-09: "when i am writing a note on a paper, it randomly
jumps up to the top of the document every once and a while."

The loop, traced through the code:

    type in a note card
      -> 600ms input debounce -> postMessage "update-note"
      -> iframe scheduleSave() 200ms -> saveNow() -> POST
      -> saveNow's wrapper calls notifyParentHighlights()
      -> parent handler calls _renderNoteGutter() unconditionally
      -> gutter.innerHTML = ...   destroys the focused textarea,
                                  and zeroes gutter.scrollTop
      -> the zeroing fires a scroll event
      -> the capture-phase sync listener forwards it as "set-scroll: 0"
      -> the PDF jumps to the top

Every hop is a direct call, so the chain is certain; the one browser
behaviour taken on trust is that replacing innerHTML resets scrollTop
and fires a scroll event.

These are source-level assertions on `src/app.js`. The boot path and
the gutter both need a live DOM, a PDF.js iframe and postMessage, so
the vm harness cannot execute them — see TESTING.md § Known gaps. Every
test below pins a link in that chain whose removal is SILENT.
"""
from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent / "src" / "app.js"


def _app() -> str:
    return _APP.read_text(encoding="utf-8")


def _render_fn() -> str:
    src = _app()
    return src[src.index("function _renderNoteGutter("):
               src.index("function _focusNoteCard(")]


def test_unchanged_card_sets_are_updated_in_place():
    """Catches: going back to rebuilding on every message.

    This is the bug itself. A rebuild while the user types destroys the
    focused textarea and resets the gutter's scroll — and because the
    two panes are scroll-synced, that scroll reset is what yanks the
    PDF to the top."""
    fn = _render_fn()
    assert "dataset.noteSig" in fn, (
        "the gutter must remember which cards it rendered")
    assert re.search(r"gutter\.dataset\.noteSig === signature", fn), (
        "an unchanged card set must take an in-place path, not a rebuild")


def test_the_focused_textarea_is_never_written_to():
    """Catches: the in-place path assigning `ta.value` unconditionally.

    Assigning to a textarea moves the caret to the end EVEN IF the value
    is identical. The note text round-trips back from the server on
    every save, so without the activeElement guard the caret would jump
    to the end of the note about once a second while typing — a subtler
    version of the same bug."""
    fn = _render_fn()
    assert "document.activeElement" in fn, (
        "the in-place update must skip the textarea that has focus")
    m = re.search(r"ta\s*!==\s*document\.activeElement[^\n]*\n?[^\n]*ta\.value\s*=", fn)
    assert m, "the activeElement check must guard the value assignment"


def test_a_real_rebuild_preserves_scroll_position():
    """Catches: dropping the scroll restore.

    Adding or deleting a note legitimately changes the card set, so a
    rebuild still happens — and it still zeroes scrollTop. Without the
    restore, creating a second note while scrolled halfway down a paper
    would fling the PDF back to page 1."""
    fn = _render_fn()
    assert "prevScroll" in fn, "the rebuild path must capture scrollTop first"
    assert re.search(r"gutter\.scrollTop\s*=\s*prevScroll", fn), (
        "the rebuild path must restore the captured scrollTop")


def test_the_scroll_restore_does_not_echo_back_to_the_viewer():
    """Catches: restoring scroll without setting `_scrollSyncing`.

    The capture-phase listener forwards ANY gutter scroll to the iframe
    as `set-scroll`. A programmatic restore that does not set the guard
    would be forwarded too — turning the fix into a different jump."""
    fn = _render_fn()
    block = fn[fn.index("prevScroll"):]
    assert "_scrollSyncing = true" in block, (
        "the programmatic scroll restore must suppress the sync listener")


def test_the_empty_state_clears_the_signature():
    """Catches: leaving a stale signature when all notes are deleted.

    The empty branch replaces the gutter's contents with placeholder
    markup that has no cards. If the signature survived, deleting every
    note and re-adding the same ones would take the in-place path
    against markup where the cards no longer exist — and silently
    render nothing."""
    fn = _render_fn()
    empty = fn[:fn.index("withNotes.sort(")]
    assert "delete gutter.dataset.noteSig" in empty, (
        "the empty branch must clear the render signature")


def test_the_resize_observer_is_only_torn_down_when_nodes_are_replaced():
    """Catches: disconnecting the observer on the in-place path.

    The teardown used to sit at the top of the function, which was
    correct while every call rebuilt. With an in-place path that never
    re-observes, an unconditional disconnect kills resize-driven
    relayout after the first update — cards stop reflowing as their
    text grows. This regression was introduced and caught while making
    the fix."""
    fn = _render_fn()
    assert "dropObserver" in fn, "observer teardown should be a named helper"
    # It must NOT run before the in-place branch returns.
    inplace_at = fn.index("gutter.dataset.noteSig === signature")
    calls = [m.start() for m in re.finditer(r"dropObserver\(\)", fn)]
    assert calls, "dropObserver is never called"
    early = [c for c in calls if c < inplace_at]
    # The only permitted early call is inside the empty-gutter branch,
    # which also replaces nodes.
    for c in early:
        empty_branch = fn.rindex("if (!withNotes.length)", 0, c)
        assert empty_branch is not None, (
            "dropObserver runs before the in-place branch outside the "
            "empty-gutter case")


def test_focus_helper_is_shared_by_both_paths():
    """Catches: duplicating the focus-and-place-caret logic.

    Both the in-place and rebuild paths honour `focusNoteId` (the
    click-a-highlight-to-ping-its-note feature). Two copies would drift,
    and the drift would only show on whichever path is rarer."""
    src = _app()
    assert src.count("function _focusNoteCard(") == 1
    assert src.count("_focusNoteCard(") >= 3, (
        "both render paths should call the shared focus helper")
