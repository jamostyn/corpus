"""The paper view's sections fold (src/collapsible.js), wherever they come from.

collapsible.test.js tests the module; this pins its wiring: the paper
view and the late-loading citers both apply it, the page loads it before
paper-detail.js, and the stylesheet hides a closed section's body.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"


def test_every_renderer_of_paper_sections_applies_folding():
    """Catches the citers section (filled in after the page) or the paper
    view itself rendering without folds — the request was ALL sections."""
    pd = (_SRC / "paper-detail.js").read_text(encoding="utf-8")
    body = pd[pd.index("function renderPaperInto"):]
    assert "Collapsible.apply(" in body
    assert "Collapsible.apply(h)" in (_SRC / "citers.js").read_text(encoding="utf-8")


def test_the_module_loads_before_the_paper_view():
    """Catches collapsible.js missing from index.html or loading after
    paper-detail.js (Collapsible undefined on the first render)."""
    html = (_SRC / "index.html").read_text(encoding="utf-8")
    assert html.index('src="collapsible.js"') < html.index('src="paper-detail.js"')


def test_a_closed_section_shows_only_its_heading():
    """Catches the fold class being set with nothing hiding the body."""
    css = (_SRC / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.pd-fold:not\(\.pd-open\) > :not\(h3\):not\(h4\)\s*\{\s*display:\s*none", css)
