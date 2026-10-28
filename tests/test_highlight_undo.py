"""Single-step undo for highlight / unhighlight.

Same coverage caveat as `tests/test_highlight_erase_mode.py`:
`corpus-highlights.js` is an IIFE inside the PDF.js viewer iframe and
cannot be loaded by the Node `vm` harness, so nothing here executes the
undo. These are source-level assertions on the invariants whose
violation is SILENT — an undo that quietly fails to cover one mutation
site looks identical to an undo that works, right up until the user
loses a highlight.

Whether pressing Undo actually restores anything is verified by hand.
"""
from __future__ import annotations

import re
from pathlib import Path

_JS = (Path(__file__).resolve().parent.parent
       / "src" / "vendor" / "pdfjs" / "web" / "corpus-highlights.js")


def _src() -> str:
    return _JS.read_text(encoding="utf-8")


def _mutation_sites() -> list[str]:
    """Every line that reassigns or pushes to `state.highlights`,
    excluding the loader and the undo restore itself."""
    out = []
    for line in _src().splitlines():
        t = line.strip()
        if not (t.startswith("state.highlights =") or
                t.startswith("state.highlights.push(")):
            continue
        # loadHighlights seeds from the server; undoLast restores.
        if "data.highlights" in t or "= []" in t or "state.undo.highlights" in t:
            continue
        out.append(t)
    return out


def test_every_highlight_mutation_is_inside_the_undo_funnel():
    """Catches: a mutation site that bypasses commitHighlights.

    This is THE invariant. There are five places that change the
    highlight set (add, recolour, same-colour remove, subsume-on-
    overlap, erase, right-click remove). If one mutates directly, the
    snapshot is not taken and Undo silently reverts to a stale state —
    or worse, reverts a DIFFERENT action than the one the user just
    performed. Adding a sixth site without wrapping it fails here."""
    src = _src()
    sites = _mutation_sites()
    assert sites, "no mutation sites found — the detector needs updating"
    for site in sites:
        idx = src.index(site)
        # Walk back to the nearest enclosing function-ish boundary and
        # require a commitHighlights call between it and the mutation.
        window = src[max(0, idx - 1200):idx]
        assert "commitHighlights(" in window, (
            f"mutation not inside the undo funnel: {site!r}")


def test_the_snapshot_is_taken_in_exactly_one_place():
    """Catches: per-site snapshotting creeping back in.

    Two places that clone the array is two places to forget. The clone
    belongs to commitHighlights alone."""
    # Exclude the definition — `function cloneHighlights()` contains the
    # same substring, so a naive count is always one too high and the
    # assertion would be about the wrong thing.
    calls = re.findall(r"(?<!function )cloneHighlights\(\)", _src())
    assert len(calls) == 1, (
        f"cloneHighlights() must be called only by commitHighlights; "
        f"found {len(calls)} calls")


def test_undo_is_single_level():
    """Catches: undo growing a stack, or becoming re-appliable.

    Jack asked for the last action only. `undoLast` must clear the
    snapshot after applying it, or pressing Undo twice reverts a second,
    older action the user never asked about."""
    src = _src()
    fn = src[src.index("function undoLast()"):src.index("function clearUndo()")]
    assert "state.undo = null" in fn, "undoLast must clear the snapshot"
    assert "push(" not in fn, "undo must not maintain a stack"


def test_the_clone_is_deep_enough_to_capture_a_recolour():
    """Catches: a shallow array copy.

    Recolouring mutates `highlight.color` on an object that is already
    in the array. `[...state.highlights]` copies the references, so the
    'snapshot' would carry the NEW colour and undo would be a no-op for
    the recolour case specifically — the subtlest of the five."""
    src = _src()
    fn = src[src.index("function cloneHighlights()"):
             src.index("function commitHighlights(")]
    assert "Object.assign({}, h" in fn, "highlight objects must be cloned"
    assert "rects" in fn, "rects arrays must be cloned too"


def test_note_edits_invalidate_the_snapshot():
    """Catches: leaving the snapshot live across a note edit.

    The snapshot is a whole-array clone. Applying it after the user has
    typed a note would revert that typing along with the highlight
    change — destroying writing the user never asked to undo."""
    src = _src()
    for handler in ('d.type === "update-note"', 'd.type === "delete-note"'):
        i = src.index(handler)
        # Bound the search to THIS handler's own branch. A fixed-size
        # window overruns into the next `else if`, so removing
        # clearUndo() from one handler still passed because the other
        # handler's call was inside the window — a mutation survived on
        # exactly that.
        nxt = src.find("} else if", i)
        block = src[i:nxt if nxt != -1 else i + 400]
        assert "clearUndo()" in block, (
            f"{handler} must clear the undo snapshot")


def test_undo_button_enabled_state_has_one_owner():
    """Catches: the button's disabled state being set ad hoc.

    Two places deciding whether Undo is clickable is how you get a lit
    button that does nothing. `refreshUndoButton` owns it."""
    src = _src()
    assert src.count("refreshUndoButton()") >= 3, (
        "refreshUndoButton must run after commit, after undo, and at build")
    # The only `.disabled =` assignments should be the initial false-y
    # one at construction and the one inside refreshUndoButton.
    assigns = re.findall(r"\w+\.disabled\s*=", src)
    assert len(assigns) <= 2, f"too many places set disabled: {assigns}"


def test_undo_notifies_the_parent_gutter():
    """Catches: undoing a removal but leaving the note gutter stale.

    Restoring a highlight that carried a note must bring its card back;
    the parent renders cards from the posted highlight list."""
    src = _src()
    fn = src[src.index("function undoLast()"):src.index("function clearUndo()")]
    assert "notifyParentHighlights()" in fn


def test_undo_shortcut_ignores_shift_so_redo_is_not_swallowed():
    """Catches: binding plain Cmd-Z so broadly that Cmd-Shift-Z (the
    conventional redo chord) is also consumed. There is no redo here, so
    that chord must fall through rather than silently undoing."""
    src = _src()
    i = src.index('e.key !== "z"')
    window = src[i:i + 300]
    assert "e.shiftKey" in window, "the Cmd-Z handler must exclude Shift"
