"""No pane renders a bare ISO country code.

Jack, 2026-09-17: "can you also have it show the full name of the
country? not sure which one this is."

OpenAlex stores ISO 3166-1 alpha-2 codes and Corpus rendered them raw
in NINE places across five modules — the institutions sidebar, three
spots on the institution detail, three on the author detail, the
journal detail, and the per-institution meta in the paper detail. Jack
saw one of them; fixing only that one would leave eight.

That is the standing rule in this codebase: a change to one view gets
ported to every view of the same shape. Nothing enforces it but a test,
so this is the test.

Source-level assertions — these renderers need a live DOM and real API
payloads, so the vm harness cannot execute them (see TESTING.md §
Known gaps). The formatting itself IS executed, in
tests/src/countries.test.js.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"

# Every module that renders a country. Kept explicit rather than
# globbed: a new module rendering one must be added here deliberately.
_RENDERERS = ("app.js", "author-detail.js", "institution-detail.js",
              "journal-detail.js", "paper-detail.js")


def _code(name: str) -> str:
    """Module source with `//` comments stripped.

    Comments in these files discuss `country_code` by name while
    explaining the fix. Searching raw text matches the prose rather
    than the code — a trap this repo has hit three times."""
    src = (_SRC / name).read_text(encoding="utf-8")
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in src.split("\n"))


@pytest.mark.parametrize("module", _RENDERERS)
def test_no_module_escapes_a_country_code_straight_into_markup(module):
    """Catches: a country rendered raw, here or in a module added later.

    `escHtml(x.country_code)` is the exact shape of the reported bug.
    Every country value must pass through `Countries.name` or
    `Countries.withCode` first, so the reader sees "Netherlands" rather
    than "NL"."""
    bad = re.findall(r"escHtml\(\s*[A-Za-z_.\[\]0-9]*country_code\s*\)", _code(module))
    assert not bad, (
        f"{module} renders a raw country code: {bad}. "
        "Wrap it in Countries.name() (or Countries.withCode() for a row "
        "that is explicitly about the stored field).")


@pytest.mark.parametrize("module", _RENDERERS)
def test_every_module_that_mentions_a_country_actually_uses_the_helper(module):
    """Catches: a module reading `country_code` and formatting it some
    other way — a local lookup table, a `.toUpperCase()`, an inline
    ternary. One shared helper is what keeps the nine sites consistent
    and what makes the Intl fallback apply everywhere."""
    code = _code(module)
    if "country_code" not in code:
        pytest.skip(f"{module} no longer references country_code")
    assert "Countries." in code, (
        f"{module} uses country_code without going through the shared "
        "Countries helper")


def test_the_helper_is_loaded_before_every_module_that_calls_it():
    """Catches: adding countries.js to index.html in the wrong place,
    or not at all.

    The detail modules call `Countries.name` at render time, so a
    missing script tag is not a parse error — it is a ReferenceError
    the first time a user opens an institution, which reads as a blank
    pane."""
    html = (_SRC / "index.html").read_text(encoding="utf-8")
    assert 'src="countries.js"' in html, "countries.js is not loaded"
    pos = {m: html.index(f'src="{m}"') for m in _RENDERERS}
    assert html.index('src="countries.js"') < min(pos.values()), (
        "countries.js must load before every module that calls it")


def test_the_institutions_filter_searches_the_displayed_country_name():
    """Catches: the display and the filter drifting apart again.

    The list shows "Netherlands"; if `searchFields` carries only
    `country_code`, typing what is on screen finds nothing. That is the
    same defect fixed in the Add-papers picker on 2026-09-14, and the
    country change reintroduces the opportunity."""
    code = _code("app.js")
    entry = code[code.index('{ id: "institutions"'):]
    # Search from offset 1 — index 0 IS the institutions entry, so
    # searching from 0 finds itself and slices the entry to "".
    nxt = entry.find('{ id: "', 1)
    entry = entry[:nxt] if nxt != -1 else entry
    assert "institutions" in entry and len(entry) > 50, "entry slice is empty"
    m = re.search(r"searchFields:\s*\(r\) => \[([^\]]*)\]", entry)
    assert m, "the institutions mode declares no searchFields"
    assert "Countries.name(" in m.group(1), (
        "institutions are displayed by country NAME but not searchable by "
        f"it; fields are: {m.group(1).strip()}")
