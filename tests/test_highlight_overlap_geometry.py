"""Highlight overlap geometry — the real functions, executed.

Bug, 2026-09-09: "when i highlight two lines with the highlight ending
early on the second line, then i try to highlight starting further down
the second line and going into a third line, it erases the first
highlight even though they are not overlapping."

Cause: `highlightsOverlapping` compared each STORED rect against the
BOUNDING BOX of the new selection. A selection spanning the end of line
2 and the start of line 3 has a bounding box that also covers the whole
START of line 2 — text the user never touched. Anything highlighted
there was judged "overlapping" and deleted.

Every other test of `corpus-highlights.js` is a source-level assertion,
because the file is an IIFE needing a live text layer (see
`test_highlight_erase_mode.py` and TESTING.md § Known gaps). These two
functions are the exception: they are PURE geometry over plain objects.
So this file EXTRACTS them from the real source and runs them in node
against real coordinates. It is the only behavioural coverage of that
file, and it exists because a structural test cannot tell a correct
overlap rule from a wrong one — the bug above passed every structural
test in the suite.

The functions are extracted, never copied. A test carrying its own copy
of the geometry would have agreed with the buggy version.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_JS = (Path(__file__).resolve().parent.parent
       / "src" / "vendor" / "pdfjs" / "web" / "corpus-highlights.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _extract(name: str) -> str:
    """Pull one top-level function out of the IIFE by brace matching.

    Fails loudly if the function is gone or renamed — a silent "" here
    would make every assertion below vacuously pass.
    """
    src = _JS.read_text(encoding="utf-8")
    start = src.index(f"function {name}(")
    depth, i = 0, src.index("{", start)
    for i in range(i, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting {name}")


def _run(highlights: list, page: int, rects: list) -> list[str]:
    """Return the ids `highlightsOverlapping` would delete."""
    script = f"""
{_extract("rectsOverlap")}
{_extract("highlightsOverlapping")}
const state = {{ highlights: {json.dumps(highlights)} }};
console.log(JSON.stringify(
  highlightsOverlapping({page}, {json.dumps(rects)}).map(h => h.id)));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _r(x0, y0, x1, y1):
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


# Three lines of text, normalized page coords.
_L1 = (0.10, 0.12)
_L2 = (0.13, 0.15)
_L3 = (0.16, 0.18)

# The existing highlight: all of line 1, then line 2 ending EARLY.
_EXISTING = [{"id": "a", "page": 1, "rects": [_r(0.10, _L1[0], 0.90, _L1[1]),
                                              _r(0.10, _L2[0], 0.40, _L2[1])]}]


def test_the_reported_bug_a_later_span_on_the_same_line_is_untouched():
    """Catches: reverting to a bounding-box overlap test.

    This is Jack's exact report. The new selection starts to the RIGHT
    of where the old highlight ended on line 2 and runs into line 3. Its
    bounding box covers the old highlight's line-2 rect; its actual
    glyph rects do not. Nothing may be deleted."""
    doomed = _run(_EXISTING, 1, [_r(0.55, _L2[0], 0.90, _L2[1]),
                                 _r(0.10, _L3[0], 0.60, _L3[1])])
    assert doomed == [], (
        "a selection that shares no glyphs with the existing highlight "
        "must not remove it")


def test_a_selection_that_really_covers_a_highlight_still_removes_it():
    """Catches: over-correcting into an overlap test that never fires.

    The subsume rule and the eraser both depend on this returning the
    hit. Making the predicate too strict would silently break re-
    highlighting and the eraser at once — and the test above would
    still pass."""
    doomed = _run(_EXISTING, 1, [_r(0.20, _L2[0], 0.60, _L2[1])])
    assert doomed == ["a"], "an overlapping selection must be found"


def test_overlap_is_detected_from_any_rect_not_just_the_first():
    """Catches: comparing only rects[0] on either side.

    Both sides are multi-rect. Checking only the first rect of the
    selection, or only the first of the stored highlight, would pass the
    two tests above (which happen to hit index 0) while missing real
    overlaps on later lines."""
    doomed = _run(_EXISTING, 1, [_r(0.10, 0.30, 0.90, 0.32),   # unrelated line
                                 _r(0.20, _L2[0], 0.60, _L2[1])])
    assert doomed == ["a"], "later selection rects must be tested too"


def test_highlights_on_other_pages_are_never_touched():
    """Catches: dropping the page filter.

    Coordinates are normalized per page, so a highlight at the same
    normalized spot on every page would all be deleted at once."""
    other = [dict(_EXISTING[0], page=2)]
    assert _run(other, 1, [_r(0.20, _L2[0], 0.60, _L2[1])]) == []


def test_touching_edges_do_not_count_as_overlap():
    """Catches: loosening `rectsOverlap` to `<`/`>=`.

    Adjacent selections share an edge coordinate. If a shared edge
    counted, highlighting the words immediately after an existing
    highlight would delete it — the reported bug in a subtler form."""
    doomed = _run(_EXISTING, 1, [_r(0.40, _L2[0], 0.70, _L2[1])])
    assert doomed == [], "a selection starting exactly where one ends is separate"
