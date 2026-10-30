"""Top tabs grouped by purpose (index.html .tab-group).

Requirement (2026-10-29): papers and documents together; authors,
institutions and journals together; notes and projects together; every
experimental tab in its own group. Each group is its own pill.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HTML = (_ROOT / "src" / "index.html").read_text(encoding="utf-8")


def _groups():
    nav = _HTML[_HTML.index('<nav class="tabs" id="tabs">'):]
    nav = nav[:nav.index("</nav>")]
    nav = re.sub(r"<!--.*?-->", "", nav, flags=re.S)
    out = []
    for m in re.finditer(r'<div class="tab-group([^"]*)"([^>]*)>(.*?)</div>', nav, re.S):
        out.append({"cls": m.group(1), "attrs": m.group(2),
                    "tabs": re.findall(r'data-tab="([^"]+)"', m.group(3))})
    assert sum(len(g["tabs"]) for g in out) == len(re.findall(r'data-tab="', nav)), \
        "a tab sits outside every group"
    return out


def test_the_tabs_are_in_the_four_agreed_groups():
    """Catches a tab moved to the wrong group, or a new tab added outside
    any group (it would float between pills)."""
    assert [g["tabs"] for g in _groups()] == [
        ["papers", "documents"],
        ["authors", "institutions", "journals"],
        ["notes", "projects"],
        ["testing", "graph", "exploration"],
    ]


def test_only_experimental_tabs_sit_in_the_hidden_experimental_group():
    """Catches a shipped tab put in the experimental group (users would
    never see it: the group ships hidden), a dev tab outside it, and an
    empty experimental pill in shipped builds."""
    app = (_ROOT / "src" / "app.js").read_text(encoding="utf-8")
    dev_modes = set(re.findall(r'\{ id: "(\w+)"[^}]*?devOnly: true', app, re.S))
    assert dev_modes == {"testing", "graph", "exploration"}
    groups = _groups()
    exp = [g for g in groups if "tab-group-experimental" in g["cls"]]
    assert len(exp) == 1 and set(exp[0]["tabs"]) == dev_modes
    assert "data-dev-only" in exp[0]["attrs"] and "hidden" in exp[0]["attrs"]
    # The one reveal must reach the group as well as its tabs.
    assert 'document.querySelectorAll(".tabs [data-dev-only]")' in app


def test_the_extractor_tab_is_named_for_what_it_holds():
    """Catches the catch-all "Testing" label coming back: each experiment
    has its own tab, named for the experiment."""
    tab = re.search(r'<button[^>]*data-tab="testing"[^>]*>([^<]*)</button>', _HTML).group(1)
    assert tab == "Text extractor"
