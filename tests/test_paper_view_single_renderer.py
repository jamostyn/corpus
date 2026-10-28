"""One paper-info renderer, usable in any host.

Jack (bug report, 2026-09-25), on the popped-out note's side panel: "i
should be able to see all the paper info here. not just this limited
info". The panel had its own compact renderer — title, authors, year,
venue, DOI, abstract — because the full one wrote into `#paper-detail`
directly and could not be pointed anywhere else.

These are source-level checks, stated as such: the renderer needs a
dozen browser globals (provenance badges, coverage table, corpus links,
tooltips), so a behavioural JS test would be mostly stubs. What CAN go
wrong is structural, and both ways are pinned here.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _body_of(js: str, fn: str) -> str:
    """Text of top-level function `fn`, up to the next top-level function."""
    start = js.index(f"function {fn}(")
    nxt = re.search(r"\n(?:async )?function \w+\(", js[start + 1:])
    return js[start:start + 1 + nxt.start()] if nxt else js[start:]


def test_the_note_panel_uses_the_shared_renderer_not_its_own():
    """Catches the panel growing a second, cut-down paper view again —
    the exact state Jack reported. Every field added to the main view
    would then be missing from the panel until someone noticed."""
    ws = (SRC / "note-workspace.js").read_text(encoding="utf-8")
    assert "renderPaperInto(" in ws, "the note panel no longer renders the full paper view"
    assert "frontmatter" not in ws, "the note panel is reading paper fields itself — a second renderer"


def test_the_renderer_never_reaches_for_the_main_pane():
    """Catches re-coupling the renderer to `#paper-detail`. Inside a
    note window that would paint the panel's paper into the main pane
    (hidden there) and leave the panel blank, and its buttons would wire
    to whichever copy the document query found first."""
    js = (SRC / "paper-detail.js").read_text(encoding="utf-8")
    body = _body_of(js, "renderPaperInto")
    assert body.count("function renderPaperInto(") == 1
    assert '"#paper-detail"' not in body and "'#paper-detail'" not in body, \
        "renderPaperInto looks up #paper-detail instead of its host"
    # Every element lookup goes through the host, not the document.
    assert not re.search(r'(?<![\w.])\$\(\s*["\'][#.]', body), \
        "renderPaperInto uses the document-wide $() helper for an element lookup"
    assert "document.getElementById" not in body and "document.querySelector" not in body


def test_citers_paint_into_the_host_they_are_given():
    """Catches Citers falling back to a document-wide id lookup when a host
    was passed. With the paper view in two places, the citer list would
    land in whichever `#pd-citers-host` came first in the document."""
    js = (SRC / "citers.js").read_text(encoding="utf-8")
    assert re.search(r"async function load\(slug, hasDoi, host\)", js)
    assert "_hostEl = host" in js
