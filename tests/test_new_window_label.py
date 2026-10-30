"""Every "open in its own window" button says "Open in new window".

Requirement (2026-10-29): the phrase "Pop out" is replaced. The label
lives once, in app.js (NEW_WINDOW_LABEL); the paper, note and document
buttons all use it.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"


def _code(name: str) -> str:
    src = (_SRC / name).read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", ln) for ln in src.split("\n"))


def test_the_three_window_buttons_use_the_one_label():
    """Catches a button keeping its own hard-coded text, which is how the
    old wording would survive in one place after a rename."""
    assert 'const NEW_WINDOW_LABEL = "Open in new window";' in _code("app.js")
    for f, marker in (("paper-detail.js", 'id="btn-pop-out"'),
                      ("notes.js", 'id="btn-note-popout"'),
                      ("documents.js", "data-doc-popout>")):
        src = _code(f)
        i = src.index(marker)
        button = src[src.rindex("<button", 0, i):src.index("</button>", i)]
        assert "${NEW_WINDOW_LABEL}" in button, f
        assert "title=" not in button, f"{f}: no tooltips in the shipped UI"


def test_no_user_visible_pop_out_wording_is_left():
    """Catches "Pop out" left in visible text — a text node in markup, or
    a toast / placeholder / aria-label string — anywhere in the shipped
    frontend. Element ids such as btn-pop-out are not visible and stay."""
    word = re.compile(r"\bpop(ped)?[ -]out\b", re.I)
    visible = re.compile(r">([^<>]*)<|toast\(\s*[\"'`]([^\"'`]*)"
                         r"|(?:placeholder|aria-label)=\"([^\"]*)\"")
    left = []
    for p in list(_SRC.glob("*.js")) + [_SRC / "index.html"]:
        for m in visible.finditer(_code(p.name)):
            text = next(g for g in m.groups() if g is not None)
            if word.search(text):
                left.append(f"{p.name}: {text.strip()[:60]}")
    assert left == []
