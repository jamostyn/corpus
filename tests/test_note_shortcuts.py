"""Note-editor formatting chords — the handler wiring.

The toolbar SPEC is tested behaviourally in
`tests/src/note-shortcuts.test.js`, which loads notes.js and reads the
real `_NOTE_TOOLBAR`. What that cannot reach is the keydown handler
itself: it is defined inside `_wireNoteEditor`, which needs the
note-detail DOM, a live note record, and `document.execCommand`.

So these are source-level assertions on the handler's wiring — the
invariants whose violation is silent. Whether pressing Cmd-B actually
bolds is verified by hand.
"""
from __future__ import annotations

import re
from pathlib import Path

_JS = Path(__file__).resolve().parent.parent / "src" / "notes.js"


def _src() -> str:
    return _JS.read_text(encoding="utf-8")


def _key_handler() -> str:
    src = _src()
    start = src.index("const keyHandler = (e) => {")
    return src[start:src.index("title.addEventListener(\"keydown\", keyHandler);")]


def _key_handler_code() -> str:
    """The handler with `//` comments stripped.

    Needed because the handler's own comment explains WHY it does not
    call execCommand — a naive substring check matches that prose and
    the assertion becomes about documentation rather than code. It
    failed exactly that way when first written."""
    out = []
    for line in _key_handler().splitlines():
        i = line.find("//")
        out.append(line if i == -1 else line[:i])
    return "\n".join(out)


def test_chords_are_looked_up_in_the_toolbar_spec():
    """Catches: the handler growing its own list of chords.

    A second list is a second place to edit. Bind ⌘B in the handler
    while the toolbar says something else and the button and the
    shortcut do different things — with nothing failing."""
    h = _key_handler_code()
    assert "_NOTE_TOOLBAR.find" in h, (
        "the chord handler must resolve keys from _NOTE_TOOLBAR, not a "
        "local list")
    assert not re.search(r'e\.key\s*===\s*"[biu]"', h), (
        "found a hard-coded formatting chord; these belong in the spec")


def test_chords_dispatch_through_the_toolbar_button():
    """Catches: the handler calling execCommand directly.

    The button's click handler does focus restoration, the
    indent/outdent special-casing, the history checkpoint, and the save
    schedule. A keyboard path that calls execCommand itself skips all
    of it — most visibly, the edit lands outside the undo history, so
    Cmd-Z afterwards reverts the wrong thing."""
    code = _key_handler_code()
    assert "btn.click()" in code, "chords should dispatch via the toolbar button"
    assert "execCommand" not in code, (
        "the chord handler must not call execCommand itself")


def test_force_save_moved_off_cmd_s_but_still_exists():
    """Catches: force-save being silently dropped when ⌘S became
    strikethrough, or being left on ⌘S where it now shadows the
    formatting chord.

    Autosave covers the common case, but removing a binding the user
    did not ask to lose is its own bug — it moved to ⌘⇧S."""
    h = _key_handler()
    assert "commitSave()" in h, "force-save binding disappeared entirely"
    m = re.search(r'if \(\(e\.key === "s" \|\| e\.key === "S"\) && e\.shiftKey\)', h)
    assert m, "force-save should now require Shift"


def test_formatting_chords_are_checked_before_the_save_chord():
    """Catches: the ⌘⇧S save branch shadowing ⌘S strikethrough.

    Both branches test the `s` key. If save is checked first without a
    strict Shift requirement, plain ⌘S saves instead of striking
    through — the exact regression this reordering exists to avoid."""
    h = _key_handler()
    assert h.index("_NOTE_TOOLBAR.find") < h.index("commitSave()"), (
        "the toolbar-spec lookup must run before the save branch")


def test_formatting_chords_ignore_shift_and_alt():
    """Catches: ⌘⇧S (save) or ⌘⌥-anything also triggering formatting.

    Without the modifier guard, the spec lookup matches on the letter
    alone and ⌘⇧S would strike through AND save."""
    h = _key_handler()
    assert "!e.shiftKey && !e.altKey" in h, (
        "the formatting branch must exclude Shift and Alt")


def test_undo_chord_still_reaches_the_note_history():
    """Catches: the new formatting branch swallowing ⌘Z.

    `z` has no `key` entry in the toolbar spec, so the lookup should
    miss and fall through — but if someone later adds one, undo breaks
    silently. This pins that ⌘Z still routes to the history."""
    h = _key_handler()
    assert "_historyUndo" in h, "Cmd-Z must still reach the note history"
    assert '"z"' in h
