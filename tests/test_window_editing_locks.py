"""One editor per paper and per note, across windows — plus the viewer URL.

Jack filed these on 2026-09-21 from the note workspace:

  * "theres an error where the note can be open in pop out and the normal
    view. fix this to prevent editing over anything"
  * "when a paper is open here it also shouldnt be able to be opened in
    another window to prevent double editing"
  * "the table of contents starts out open when i clicked on the paper
    link here. it should always start closed"

The window lock for papers lives in launcher.py's _Bridge because it is
the only process that sees every window; that part gets real behavioural
tests. The frontend parts need a DOM and are held by source assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"


def _nocomments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.split("\n"))


def _js(name: str) -> str:
    return _nocomments((_SRC / name).read_text(encoding="utf-8"))


# ---------- the launcher's paper lock (behaviour) ----------

@pytest.fixture
def bridge():
    # Loaded by path, the same way test_bridge_contract.py does: launcher.py
    # is not importable as a module from the tests package.
    import importlib.util
    spec = importlib.util.spec_from_file_location("corpus_launcher_locks",
                                                  _ROOT / "launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    b = mod._Bridge()
    b._told = []
    b._tell_main = lambda event, detail: b._told.append((event, detail))
    return b


def test_a_note_panel_can_claim_a_free_paper(bridge):
    """Catches the claim refusing everything, which would leave the panel
    permanently showing "already open in another window"."""
    assert bridge.set_panel_paper("note:a", "paper:pan-2025-1") == "ok"
    assert bridge._panel_holder("paper:pan-2025-1") == "note:a"


def test_a_second_note_cannot_claim_the_same_paper(bridge):
    """Catches two panels editing one paper — two highlight savers, last
    writer wins, the other's highlights gone."""
    bridge.set_panel_paper("note:a", "paper:pan-2025-1")
    assert bridge.set_panel_paper("note:b", "paper:pan-2025-1") == "busy"


def test_a_paper_popped_out_on_its_own_cannot_be_claimed(bridge):
    """Catches checking only other panels and forgetting real windows."""
    bridge._detached["paper:pan-2025-1"] = object()
    assert bridge.set_panel_paper("note:a", "paper:pan-2025-1") == "busy"


def test_a_paper_in_a_panel_cannot_be_popped_out(bridge):
    """Catches enforcing the lock in one direction only."""
    bridge.set_panel_paper("note:a", "paper:pan-2025-1")
    assert bridge.open_detached("paper:pan-2025-1", "http://x", "t") == "busy"


def test_releasing_frees_the_paper_and_tells_the_main_window(bridge):
    """Catches a paper staying locked after its panel closes, and the
    main window never learning it can un-lock its paper pane."""
    bridge.set_panel_paper("note:a", "paper:pan-2025-1")
    assert bridge.set_panel_paper("note:a", None) == "ok"
    assert bridge._panel_holder("paper:pan-2025-1") is None
    assert ("corpus-panel-paper", {"note": "note:a", "slug": None}) in bridge._told


def test_switching_papers_in_one_panel_moves_the_claim(bridge):
    """Catches a panel holding every paper it ever showed."""
    bridge.set_panel_paper("note:a", "paper:pan-2025-1")
    bridge.set_panel_paper("note:a", "paper:yang-2020")
    assert bridge._panel_holder("paper:pan-2025-1") is None
    assert bridge.set_panel_paper("note:b", "paper:pan-2025-1") == "ok"


def test_a_document_is_locked_the_same_way(bridge):
    """Catches the lock covering papers only. A document can be open in a
    note's panel or popped out (2026-09-25); both save highlights, so the
    two must refuse each other exactly as a paper's do."""
    assert bridge.set_panel_paper("note:a", "document:chapter-3") == "ok"
    assert bridge.open_detached("document:chapter-3", "http://x", "t") == "busy"
    assert bridge.set_panel_paper("note:b", "document:chapter-3") == "busy"
    # …and a paper whose slug happens to equal a document's id is a
    # different thing, not a collision.
    assert bridge.set_panel_paper("note:b", "paper:chapter-3") == "ok"


# ---------- the main window honours it (source) ----------

def test_the_paper_pane_treats_a_panel_held_paper_as_open_elsewhere():
    """Catches the main window ignoring the launcher's answer — the paper
    pane would stay editable while a note panel edits the same paper."""
    app = _js("app.js")
    fn = app[app.index("function isDetachedElsewhere"):]
    fn = fn[:fn.index("\n}\n")]
    # Keyed by kind since documents can sit in the panel too (2026-09-25).
    assert "_panelHolderOf(kind, id)" in fn
    assert 'addEventListener("corpus-panel-paper"' in app


def test_a_popped_out_note_is_locked_in_the_main_window():
    """Catches the reported bug: notes never had the placeholder papers
    had, so one note had two live editors autosaving over each other."""
    notes = _js("notes.js")
    fn = notes[notes.index("function renderNoteDetail"):]
    lock = fn.index('isDetachedElsewhere("note", n.id)')
    editor = fn.index("pane.innerHTML = `")
    assert lock < editor, "the lock must run before the editor is built"


def test_popping_a_note_out_lands_pending_edits_first():
    """Catches losing the last ~800ms of typing: the pop-out reads the
    note immediately, before the main window's debounced save fires."""
    app = _js("app.js")
    fn = app[app.index("async function openDetached"):]
    assert fn.index("flushNoteSave()") < fn.index("detachKey(kind, id)")


def test_placeholder_buttons_send_the_full_window_key():
    """Catches the bare-slug lookup that made Bring to front / Close that
    window do nothing: launcher.py registers windows as "paper:<slug>"."""
    pd = _js("paper-detail.js")
    assert "focus_detached(slug)" not in pd and "close_detached(slug)" not in pd
    app = _js("app.js")
    assert 'data-detach-focus="${escAttr(key)}"' in app
    assert "const key = detachKey(kind, id);" in app[app.index("function detachedPlaceholderHtml"):]


# ---------- the viewer URL ----------

def test_every_pdf_viewer_is_built_by_one_function():
    """Catches a new viewer building its own URL again.

    Three copies had drifted: only the paper pane passed pagemode=none,
    so the note panel opened with its table of contents out."""
    for f in list(_SRC.glob("*.js")) + list((_SRC / "dev_only").glob("*.js")):
        src = _nocomments(f.read_text(encoding="utf-8"))
        if f.name == "app.js":
            src = src.replace(src[src.index("function pdfViewerSrc"):
                                  src.index("window.pdfViewerSrc")], "")
        assert "viewer.html" not in src, f"{f.name} builds its own viewer URL"


def test_the_viewer_starts_with_its_sidebar_closed():
    """Catches dropping pagemode=none from the one builder."""
    app = _js("app.js")
    fn = app[app.index("function pdfViewerSrc"):app.index("window.pdfViewerSrc")]
    assert "pagemode=none" in fn


# ---------- the bug reporter's screenshot ----------

def test_bug_reporter_never_asks_for_a_canvas_webkit_will_refuse():
    """Catches the 0-byte screenshot (report 20260921-162029): un-clipping
    a ~600-row sidebar made the capture taller than WebKit's canvas limit."""
    br = _js("dev_only/bug-reporter.js")
    unclip = br[br.index("const scrollables = ["):]
    unclip = unclip[:unclip.index("].filter(Boolean)")]
    assert ".sidebar" not in unclip
    assert "MAX_CANVAS_DIM" in br and "scale," in br


def test_bug_reporter_refuses_to_file_an_empty_screenshot():
    """Catches saving "data:," as a screenshot again."""
    br = _js("dev_only/bug-reporter.js")
    assert 'canvas.toDataURL("image/png").length < 100' in br
    after = br[br.index("if (!canvas) {"):]
    assert after.index("return;") < after.index("openModal(canvas)")
