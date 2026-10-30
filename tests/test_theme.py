"""Appearance setting: Match system / Light / Dark.

Requirement (2026-10-28): Settings has a dark mode that can be set by hand
or follow the system. config_api.THEMES is the one list; the Settings
<select>, the stored value and the stylesheet's dark blocks must agree.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CSS = (_ROOT / "src" / "styles.css").read_text(encoding="utf-8")


def _decls(block: str) -> dict:
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))


def _block(start: str) -> str:
    i = _CSS.index(start)
    return _CSS[i:_CSS.index("}", i)]


def test_the_settings_picker_lists_exactly_the_server_themes():
    """Catches a theme added on one side only: a picker option the server
    rejects (Save fails), or a server theme nobody can choose."""
    import config_api
    html = (_ROOT / "src" / "index.html").read_text(encoding="utf-8")
    sel = html[html.index('<select id="cfg-theme">'):]
    sel = sel[:sel.index("</select>")]
    assert tuple(re.findall(r'<option value="([^"]+)"', sel)) == config_api.THEMES
    assert config_api.DEFAULT_THEME in config_api.THEMES


def test_theme_defaults_to_system_and_round_trips(client):
    """Catches the theme not being saved, or a fresh install starting in
    a pinned theme instead of following the system."""
    assert client.get("/api/config").get_json()["theme"] == "system"
    assert client.post("/api/config", json={"theme": "dark"}).status_code == 200
    assert client.get("/api/config").get_json()["theme"] == "dark"


def test_an_unknown_theme_is_refused_and_not_stored(client):
    """Catches storing junk that the frontend would then apply as no theme
    at all, silently ignoring the user's last real choice."""
    client.post("/api/config", json={"theme": "light"})
    r = client.post("/api/config", json={"theme": "solarized"})
    assert r.status_code == 400
    assert client.get("/api/config").get_json()["theme"] == "light"


def test_every_colour_token_has_a_dark_value_and_both_dark_blocks_agree():
    """Catches (a) a new colour variable with a light value only — it
    stays light on a dark page — and (b) the pinned-dark block and the
    follow-the-system block drifting apart, so "Dark" and "Match system"
    on a dark Mac look different."""
    light = _decls(_block(":root {"))
    pinned = _decls(_block(':root[data-theme="dark"] {'))
    system = _decls(_block(':root:not([data-theme="light"]) {'))
    assert pinned == system
    layout_only = {"--topbar-h", "--sidebar-w"}
    missing = sorted(set(light) - layout_only - set(pinned))
    assert missing == [], f"no dark value for {missing}"
    assert all(pinned[k] != light[k] for k in pinned if k not in ("--accent-fg", "--warn-edge"))


def test_no_new_hard_coded_colours_outside_the_theme_blocks():
    """Catches a rule written with a literal colour (e.g. `color: #333`),
    or `background: white`, which ignores the theme and turns unreadable
    in dark mode. Shadows,
    the modal backdrop and the flash animation work on both and are
    allowed."""
    body = re.sub(r"/\*.*?\*/", "", _CSS, flags=re.S)
    for start in (":root {", ':root[data-theme="dark"] {', ':root:not([data-theme="light"]) {'):
        i = body.index(start)
        body = body[:i] + body[body.index("}", i) + 1:]
    allowed = re.compile(r"rgba\(0, 0, 0, [\d.]+\)|rgba\(74, 158, 255, [\d.]+\)"
                         r"|var\(--accent, #4c1d95\)|color: #fff;")
    body = allowed.sub("", body)
    found = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", body)
    # Named colours too: `background: white` on the Sort by controls
    # survived the first dark-mode pass because only #hex / rgb() were
    # checked, and showed as white boxes with unreadable text.
    named = re.findall(r"(?:color|background|border[\w-]*|outline)\s*:[^;{}]*?"
                       r"\b(white|black|gray|grey|silver|red|blue|green|yellow)\b", body)
    assert found == [] and named == []
