"""Anything that ships `hidden` must actually be hidden.

Any CSS `display: <not none>` rule beats the browser's own
`[hidden] { display: none }`, so an element that starts hidden in
index.html and whose class sets `display: flex` (or grid, block, …) shows
anyway — unless the class also has a `[hidden]` override. This has bitten
Corpus repeatedly (tab panes persisting across tab switches); the
experimental tab group (2026-10-29) is the latest such element.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CSS = re.sub(r"/\*.*?\*/", "", (_ROOT / "src" / "styles.css").read_text(encoding="utf-8"), flags=re.S)
_HTML = re.sub(r"<!--.*?-->", "", (_ROOT / "src" / "index.html").read_text(encoding="utf-8"), flags=re.S)


def _classes_with_display():
    out = set()
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _CSS):
        if re.search(r"(^|;)\s*display:\s*(?!none)\w", body):
            for part in sel.split(","):
                m = re.fullmatch(r"\s*\.([\w-]+)\s*", part)   # a bare .class selector
                if m:
                    out.add(m.group(1))
    return out


def _overridden(cls: str) -> bool:
    return re.search(rf"\.{re.escape(cls)}\[hidden\][^{{]*\{{[^}}]*display:\s*none", _CSS) is not None


def test_every_element_that_starts_hidden_stays_hidden():
    """Catches a `display:` rule on a class used by an element that ships
    with `hidden` or that a script hides, without the matching
    `.class[hidden]` override — the element would stay on screen."""
    displayed = _classes_with_display()
    missing = set()
    # Elements hidden in the markup, plus elements a script hides by id
    # (`$("#x").hidden = …`, `getElementById("x").hidden = …`).
    js = "\n".join(p.read_text(encoding="utf-8") for p in (_ROOT / "src").glob("*.js"))
    ids = set(re.findall(r"""(?:\$\(\s*["']#|getElementById\(\s*["'])([\w-]+)["']\s*\)\s*\.hidden\s*=""", js))
    # …and through a variable: `const w = $("#x"); … w.hidden = …`.
    for var, el in re.findall(r"""(\w+)\s*=\s*(?:\$\(\s*["']#|document\.getElementById\(\s*["'])([\w-]+)["']\s*\)""", js):
        if re.search(rf"\b{re.escape(var)}\.hidden\s*=", js):
            ids.add(el)
    tags = re.findall(r"<[a-z]+\b[^>]*\bhidden\b[^>]*>", _HTML)
    tags += [t for t in re.findall(r"<[a-z]+\b[^>]*>", _HTML)
             if (m := re.search(r'id="([^"]+)"', t)) and m.group(1) in ids]
    for tag in tags:
        m = re.search(r'class="([^"]+)"', tag)
        for cls in (m.group(1).split() if m else []):
            if cls in displayed and not _overridden(cls):
                missing.add(cls)
    assert sorted(missing) == []
