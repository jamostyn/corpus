"""Note entity links: the JS↔Python agreement, and the sanitizer.

A note links to a paper / author / institution / journal with an
ordinary `<a data-open-<type>="<id>">`. Two independent lists have to
agree on `<type>`:

  * `src/app.js` — the MODES entries declaring `linkAttr`, which drive
    both the deep-link click handler and the notes link picker.
  * `python/notes_api.py` — `_NOTE_LINK_ATTRS`, which the sanitizer
    uses to decide what survives a save.

If they drift, the failure is silent and delayed: the link works while
the note is open, then vanishes on reload because the save stripped the
attribute. That is the worst shape of bug this codebase can produce, so
it gets a parity test — the same treatment `entity-keys.js` gets in
tests/test_metadata.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from notes_api import _NOTE_LINK_ATTRS, _sanitize_note_html

_APP_JS = Path(__file__).resolve().parent.parent / "src" / "app.js"


def _js_link_attrs() -> list[str]:
    """Every `linkAttr: "..."` declared on a MODES entry in app.js."""
    src = _APP_JS.read_text(encoding="utf-8")
    return re.findall(r'linkAttr:\s*"([a-z]+)"', src)


def test_js_and_python_agree_on_link_attrs():
    """Catches: adding a linkable entity type on one side only.

    Add `linkAttr: "dataset"` to a MODES entry and the picker will
    happily insert `data-open-dataset` links — which the sanitizer then
    strips on the next save, losing the link with no error anywhere."""
    assert sorted(_js_link_attrs()) == sorted(_NOTE_LINK_ATTRS)


def test_every_link_attr_has_a_mode_that_can_select_it():
    """Catches: a `linkAttr` on a MODES entry with no `select` function.

    app.js's deep-link handler calls `mode.select(id)`. A linkable mode
    without one throws on click, which reads to the user as a dead
    link."""
    src = _APP_JS.read_text(encoding="utf-8")
    for attr in _NOTE_LINK_ATTRS:
        m = re.search(r'linkAttr:\s*"' + attr + r'"', src)
        assert m, f"no MODES entry declares linkAttr {attr!r}"
        # Scan from the start of this MODES entry to the start of the
        # next one. Brace-matching is not worth it here: the entries
        # contain arrow functions and template literals, so a
        # `{...}` regex cannot span them.
        start = src.rfind('{ id: "', 0, m.start())
        end = src.find('{ id: "', m.end())
        entry = src[start:end if end != -1 else m.end() + 400]
        for required in ("select:", "linkId:", "linkLabel:", "linkNoun:"):
            assert required in entry, f"{attr} MODES entry is missing {required}"


# ---------- sanitizer ----------

@pytest.mark.parametrize("attr", _NOTE_LINK_ATTRS)
def test_link_attribute_survives_sanitising(attr):
    """Catches: the sanitizer stripping data-open-* on save.

    This is the failure that makes links work in-session and die on
    reload. Before entity links existed, `<a>` allowed only href and
    title, so every one of these would have been dropped."""
    html = f'<p><a href="#" data-open-{attr}="smith-2023">Smith</a></p>'
    out = _sanitize_note_html(html)
    assert f'data-open-{attr}="smith-2023"' in out
    assert ">Smith<" in out


def test_link_to_a_key_with_dots_and_underscores_survives():
    """Catches: an over-tight value pattern. Real keys include
    `issn-2772-3925`, `ror-00dcv1019`, and paper slugs like
    `pan-2025-1` and `RB_CriterionLearningSimulation_BC_2015`."""
    for key in ("issn-2772-3925", "ror-00dcv1019", "pan-2025-1",
                "RB_CriterionLearningSimulation_BC_2015", "10.1037_a0016026"):
        html = f'<a href="#" data-open-paper="{key}">x</a>'
        assert f'data-open-paper="{key}"' in _sanitize_note_html(html)


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "a b",
    "javascript:alert(1)",
    "<script>",
    "x" * 300,
    "",
])
def test_malformed_link_values_are_dropped(bad):
    """Catches: relaxing the identifier pattern.

    The value goes straight into a navigation call and an API path, so
    anything outside the slug/key charset is dropped WHOLE rather than
    cleaned — a partially-scrubbed identifier would navigate somewhere
    unintended instead of failing."""
    out = _sanitize_note_html(f'<a href="#" data-open-paper="{bad}">x</a>')
    assert "data-open-paper" not in out
    assert ">x<" in out, "the link text must survive even when the target doesn't"


def test_unknown_data_attributes_are_still_stripped():
    """Catches: allowing `data-*` wholesale instead of the named four.

    A blanket data-attribute allowance would let a note carry arbitrary
    state into the DOM."""
    out = _sanitize_note_html(
        '<a href="#" data-open-paper="ok" data-evil="1" data-open-dataset="x">t</a>')
    assert 'data-open-paper="ok"' in out
    assert "data-evil" not in out
    assert "data-open-dataset" not in out


def test_links_still_reject_javascript_hrefs():
    """Catches: the new data-attr branch accidentally bypassing the
    existing javascript:/data: href guard."""
    out = _sanitize_note_html(
        '<a href="javascript:alert(1)" data-open-paper="ok">t</a>')
    assert "javascript" not in out.lower()
    assert 'data-open-paper="ok"' in out


def test_entity_link_class_survives_so_styling_applies():
    """Catches: the marker class being stripped on save.

    `src/styles.css` styles note links via `a.note-entity-link`. If the
    sanitizer drops the class, links render styled while the note is
    open and as plain text after a reload — a round-trip-only bug that
    is easy to miss by hand. Found exactly that way."""
    out = _sanitize_note_html(
        '<a href="#" class="note-entity-link" data-open-paper="x">t</a>')
    assert 'class="note-entity-link"' in out


def test_other_classes_on_links_are_still_stripped():
    """Catches: allowing arbitrary classes on <a>, which would let a
    note restyle itself using app chrome classes."""
    out = _sanitize_note_html(
        '<a href="#" class="btn danger note-entity-link" data-open-paper="x">t</a>')
    assert "btn" not in out and "danger" not in out
    assert "note-entity-link" in out
