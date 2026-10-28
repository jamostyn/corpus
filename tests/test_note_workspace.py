"""The detached note workspace — note left, PDF right, highlight links.

Jack, 2026-09-21: "i want to be able to pop out notes to occupy the
full screen like i can for papers … a button … to pop out a panel that
shows the pdfs (if any) tagged in this note … when you click on a link
to a paper in fullscreen note mode instead of bringing you to the
paper, it makes that paper be in view for the panel … a new button …
links to a specific highlight … so if you click the linked full quote
in the note, it brings up that paper and scrolls to that highlight"

Four parts, four groups of tests below. The detached-key parsing is
pure, so it is EXTRACTED from app.js and executed in node; the rest are
source-level, because the workspace needs a live DOM, a popped-out
window and a PDF.js iframe (see TESTING.md § Known gaps).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from notes_api import (_NOTE_EXTRA_LINK_DATA_ATTRS, _NOTE_LINK_ATTRS,
                       _NOTE_LINK_DATA_ATTRS, _sanitize_note_html)

_SRC = Path(__file__).resolve().parent.parent / "src"
_APP = _SRC / "app.js"
_NOTES = _SRC / "notes.js"
_WS = _SRC / "note-workspace.js"
_VIEWER = _SRC / "vendor" / "pdfjs" / "web" / "corpus-highlights.js"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _nocomments(src: str) -> str:
    """Strip BOTH comment forms.

    Stripping only `//` left the `/** … */` docblocks in place, and a
    test asserting "this file must not use X" then matched the comment
    explaining why it doesn't. That trap has bitten this suite four
    times now."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", l) for l in src.split("\n"))


# ---------- part 1: the detached key ----------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_detached_hash_round_trips_kind_and_id():
    """Catches: a key format that cannot express a note.

    The window identity was a bare paper slug everywhere — the Map key,
    the pywebview bridge, the close event. A note needs its own
    namespace or `note:abc` and a paper called `note:abc` collide."""
    src = _read(_APP)
    start = src.index("function _readDetachedHash(")
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                fn = src[start:i + 1]
                break
    kinds = re.search(r'const DETACH_KINDS = (\[[^\]]*\]);', src)
    assert kinds, "DETACH_KINDS is gone"
    script = f"""
const DETACH_KINDS = {kinds.group(1)};
{fn}
const cases = ["note:abc", "paper:schunn-2001", "schunn-2001", "", "bogus:x", "notes"];
const out = {{}};
for (const c of cases) {{
  global.location = {{ hash: "#detached=" + encodeURIComponent(c) }};
  const r = _readDetachedHash();
  out[c] = [r.kind, r.id];
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", script], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["note:abc"] == ["note", "abc"]
    assert got["paper:schunn-2001"] == ["paper", "schunn-2001"]
    # A bare slug is a paper — windows popped out by an older build
    # must keep working.
    assert got["schunn-2001"] == ["paper", "schunn-2001"]
    assert got[""] == [None, None]
    # An unknown kind falls back to paper rather than rendering nothing.
    assert got["bogus:x"] == ["paper", "x"]
    # A colon is the ONLY thing that introduces a kind. Splitting a
    # bare value some other way (say, everything but the last char)
    # happens to survive most inputs because the unknown-kind fallback
    # catches the garbage — but a paper slugged "notes" would then be
    # read as kind "note", id "notes", and open the wrong window.
    assert got["notes"] == ["paper", "notes"]


def test_every_detached_map_lookup_uses_the_composite_key():
    """Catches: one call site still keying the Map by a bare slug.

    `state.detachedWindows` is now keyed "<kind>:<id>". A leftover raw
    slug lookup silently misses, so the window is reported as closed and
    a second one opens on top of it."""
    src = _nocomments(_read(_SRC / "paper-detail.js"))
    for m in re.finditer(r"detachedWindows\.(get|set|has|delete)\(([^)]*)\)", src):
        assert "detachKey(" in m.group(2), (
            f"detachedWindows keyed without detachKey: {m.group(0)}")


# ---------- part 2 + 3: the panel ----------

def test_the_panel_has_its_own_post_helper():
    """Catches: reusing app.js's `_postToViewer`.

    That one targets `#paper-detail .pdf-viewer`, which does not exist
    in a popped-out note window — messages would go nowhere and the
    panel would silently never scroll."""
    ws = _nocomments(_read(_WS))
    assert "#nw-panel-body iframe" in ws, "the panel must address its own iframe"
    assert "_postToViewer(" not in _nocomments(_read(_WS)), (
        "the workspace must not CALL the paper pane's post helper")


def test_a_paper_link_targets_the_panel_before_switching_mode():
    """Catches: intercepting AFTER `switchMode`.

    Switching tabs in a detached window tears down the split layout, so
    an interception that runs afterwards flashes a broken pane on every
    link click — and the note the user is reading disappears."""
    src = _nocomments(_read(_APP))
    blk = src[src.index("if (entityLink) {"):src.index("} else if (revealLink)")]
    intercept = blk.index('state.detached && state.detached.kind === "note"')
    switch = blk.index("switchMode(entityLink.m.id)")
    assert intercept < switch, (
        "the detached-note interception must run before switchMode")


def test_only_paper_links_are_redirected_to_the_panel():
    """Catches: sending author/journal links to a panel that only shows
    PDFs. They have nowhere to go in this window; navigating would blank
    it."""
    src = _nocomments(_read(_APP))
    blk = src[src.index('state.detached && state.detached.kind === "note"'):]
    blk = blk[:blk.index("switchMode(entityLink.m.id)")]
    assert 'entityLink.m.linkAttr === "paper"' in blk


def test_the_note_editor_renders_into_a_host_rather_than_being_duplicated():
    """Catches: a second copy of the note editor for the workspace.

    Two editors would drift — the toolbar, autosave, undo and the
    entity-link picker all live in `renderNoteDetail`. One function,
    two mount points."""
    notes = _read(_NOTES)
    assert re.search(r"function renderNoteDetail\(host\)", notes), (
        "renderNoteDetail must take a host element")
    assert 'const pane = host || $("#note-detail");' in notes


# ---------- part 4: highlight links ----------

def test_the_highlight_attribute_survives_a_save():
    """Catches: forgetting the sanitizer allow-list.

    A stripped attribute is invisible until the next autosave, then the
    link silently degrades. This is the exact failure the notes parity
    test was written for, and a new link shape has to go through it."""
    html = ('<a href="#" class="note-entity-link" data-open-paper="schunn-2001" '
            'data-open-highlight="hl-42">quoted</a>')
    out = _sanitize_note_html(html)
    assert 'data-open-highlight="hl-42"' in out
    assert 'data-open-paper="schunn-2001"' in out


def test_a_highlight_id_that_could_escape_the_corpus_is_rejected():
    """Catches: exempting the new attribute from the value pattern.

    Every other data-open-* value is checked; a highlight id must be
    too, or the one attribute nobody validated becomes the way in."""
    out = _sanitize_note_html('<a href="#" data-open-highlight="../../etc/passwd">x</a>')
    assert "data-open-highlight" not in out


def test_highlight_is_not_smuggled_into_the_entity_mode_list():
    """Catches: adding "highlight" to `_NOTE_LINK_ATTRS`.

    That tuple mirrors the MODES entries declaring `linkAttr` — one per
    navigable entity — and is parity-tested against app.js. A highlight
    is a position inside a paper, not a tab; putting it there breaks
    that contract and implies a Highlights mode that does not exist."""
    assert "highlight" not in _NOTE_LINK_ATTRS
    assert "data-open-highlight" in _NOTE_EXTRA_LINK_DATA_ATTRS
    assert "data-open-highlight" in _NOTE_LINK_DATA_ATTRS


def test_a_highlight_link_always_carries_its_paper():
    """Catches: emitting `data-open-highlight` alone.

    The paper attribute is what makes the link degrade: in the docked
    view, or when the highlight has since been erased, it still opens
    the right paper instead of doing nothing."""
    notes = _nocomments(_read(_NOTES))
    fn = notes[notes.index("function _highlightLinkHtml("):]
    fn = fn[:fn.index("function _insertHighlightLink(")]
    assert "data-open-highlight=" in fn
    # The kind attribute is data-open-paper OR data-open-document
    # (documents, 2026-09-25), chosen from the picked highlight's kind.
    assert '"document" ? "document" : "paper"' in fn


def test_pick_mode_takes_precedence_over_the_other_click_rules():
    """Catches: placing the pick branch after the Note Mode guard.

    `state.noteMode` is off by default, so a pick armed from the
    workspace would never fire — the user would click highlights and
    nothing would happen, with no error."""
    src = _nocomments(_read(_VIEWER))
    start = src.index('document.addEventListener("click", (e) => {')
    blk = src[start:start + 2500]          # the listener body; comments are gone
    pick = blk.index("state.pickMode")
    note_guard = blk.index("if (!state.noteMode)")
    assert pick < note_guard, "the pick branch must precede the Note Mode guard"


def test_a_missed_pick_click_stays_armed():
    """Catches: disarming on any click.

    Clicking beside a highlight is the common miss. Disarming there
    means the button appears to do nothing and must be pressed again."""
    src = _nocomments(_read(_VIEWER))
    blk = src[src.index("if (state.pickMode) {"):]
    blk = blk[:blk.index("if (state.highlightMode) return;")]
    assert re.search(r"if \(!picked\) return;", blk), (
        "a click that hits no highlight must leave pick mode armed")


# "Scrolling to an unknown highlight does not jump" used to live here as a
# check for the literal line `if (!el) return false;`. That line was the
# bug — it also gave up on every highlight whose page was not rendered
# yet (Jack, 2026-09-22). The behaviour is now tested for real, against
# the viewer's actual functions, in tests/src/highlight-scroll.test.js
# ("an erased highlight does not move the viewer").


def test_a_highlight_link_scrolls_in_the_docked_view_too():
    """Catches: making scroll-to-highlight a workspace-only behaviour.

    The same link exists in the Notes tab. Opening the paper but not
    scrolling does half the job silently, and the user cannot tell the
    link from an ordinary paper link."""
    src = _nocomments(_read(_APP))
    assert "_scrollPaperPaneToHighlight(" in src, (
        "the docked path must scroll to the highlight")
    blk = src[src.index("switchMode(entityLink.m.id);"):]
    blk = blk[:blk.index("} else if (revealLink)")]
    assert "_scrollPaperPaneToHighlight(hid)" in blk
