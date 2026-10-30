"""Every API key Settings asks for is used, and its hint says so.

Settings showed "Stored, not yet used" under both keys long after
Semantic Scholar and OpenAlex were wired in; and from the other side, the
OpenAlex key was stored but read by nothing until 2026-09-22. A key field
must lead to code that reads it.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_each_secret_key_has_a_settings_field_and_a_reader():
    """Catches a key the user can type in that no request ever sends
    (the 2026-09-22 OpenAlex bug), and a SECRET_KEYS entry with no field."""
    import config_api
    html = (_ROOT / "src" / "index.html").read_text(encoding="utf-8")
    readers = "\n".join(p.read_text(encoding="utf-8")
                        for p in (_ROOT / "python" / "extract").glob("*.py"))
    for key in config_api.SECRET_KEYS:
        env = f"CORPUS_{key.upper()}"
        assert re.search(rf'environ\.get\(\s*"{env}"', readers), f"nothing reads {env}"
    js = (_ROOT / "src" / "app.js").read_text(encoding="utf-8")
    for key in config_api.SECRET_KEYS:
        assert f"payload.keys.{key}" in js, f"Settings never sends {key}"
    assert "not yet used" not in html.lower()
