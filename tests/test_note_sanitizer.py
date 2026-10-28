"""Note HTML sanitizer — the allow-list, the clamps, and the strip.

These tests lock in the current shape of `_sanitize_note_html` so a
future refactor of the sanitizer can't silently open a hole or drop a
formatting tag the editor relies on.
"""


def _s(html):
    from notes_api import _sanitize_note_html
    return _sanitize_note_html(html)


# --- basic allow-list ---

def test_keeps_formatting_tags():
    assert _s("<p>hello <strong>w</strong> <em>o</em></p>") == \
           "<p>hello <strong>w</strong> <em>o</em></p>"


def test_keeps_lists():
    assert "<ul>" in _s("<ul><li>a</li></ul>") and "</li></ul>" in _s("<ul><li>a</li></ul>")


def test_keeps_nested_lists():
    """Indent (Tab or → button) produces nested <ul>/<ol> structures.
    Sanitiser must preserve the nesting — dropping either the inner
    <ul> or the <li> would flatten indented items back to depth 1."""
    src = "<ul><li>top<ul><li>nested</li></ul></li></ul>"
    out = _s(src)
    # Both levels survive.
    assert out.count("<ul>") == 2
    assert out.count("</ul>") == 2
    assert "nested" in out
    # Same for ordered.
    src_ol = "<ol><li>1<ol><li>a</li></ol></li></ol>"
    out_ol = _s(src_ol)
    assert out_ol.count("<ol>") == 2
    assert out_ol.count("</ol>") == 2


def test_keeps_li_phantom_class():
    """When the user indents the FIRST item of a list, the editor
    wraps it in a phantom <li class="li-phantom"> that CSS hides.
    That specific class must survive sanitisation."""
    src = '<ul><li class="li-phantom"><ul><li>indented-first</li></ul></li></ul>'
    out = _s(src)
    assert 'class="li-phantom"' in out


def test_strips_other_li_classes():
    """Any class other than li-phantom must be stripped from <li>."""
    src = '<ul><li class="attacker exploit li-phantom"><ul><li>x</li></ul></li></ul>'
    out = _s(src)
    # Allowed class kept, others dropped.
    assert 'class="li-phantom"' in out
    assert "attacker" not in out
    assert "exploit" not in out

    # Class with NONE of the allow-listed values → attribute dropped.
    src2 = '<ul><li class="attacker">x</li></ul>'
    out2 = _s(src2)
    assert "class=" not in out2
    assert "attacker" not in out2


def test_keeps_line_break_producers():
    # <div>, <p>, <br> all need to survive so Enter-produced markup
    # doesn't vanish on the save round-trip.
    for tag in ("div", "p", "br"):
        s = _s(f"<{tag}>x</{tag}>") if tag != "br" else _s("a<br>b")
        assert tag in s


# --- script / event-handler injection ---

def test_strips_script_tag():
    out = _s("<script>alert(1)</script>keep")
    assert "<script>" not in out
    assert "</script>" not in out
    assert "keep" in out


def test_strips_img_and_onerror():
    out = _s('<img src=x onerror=alert(1)>drop')
    assert "<img" not in out


def test_strips_javascript_href():
    out = _s('<a href="javascript:alert(1)">bad</a> <a href="https://ok.com">good</a>')
    assert "javascript:" not in out
    assert 'href="https://ok.com"' in out


# --- font-size clamping on span ---

def test_span_font_size_kept():
    assert _s('<span style="font-size: 20px">x</span>') == '<span style="font-size: 20px">x</span>'


def test_span_font_size_clamped_high():
    out = _s('<span style="font-size: 9999px">x</span>')
    assert 'font-size: 120px' in out


def test_span_font_size_clamped_low():
    out = _s('<span style="font-size: 0px">x</span>')
    assert 'font-size: 1px' in out


def test_span_font_size_rejects_non_px():
    assert _s('<span style="font-size: 2em">x</span>') == '<span>x</span>'


def test_span_style_strips_other_props():
    out = _s('<span style="color:red;font-size:20px;background:url(x)">x</span>')
    assert 'font-size: 20px' in out
    assert 'color' not in out
    assert 'background' not in out
    assert 'url' not in out


# --- table markup ---

def test_table_basic():
    out = _s('<table class="note-table"><tr><td>a</td><td>b</td></tr></table>')
    assert '<table class="note-table">' in out
    assert '<tr>' in out and '<td>a</td>' in out


def test_table_style_kept_only_for_dim_props():
    out = _s('<td style="background:red;position:fixed;width:100px">x</td>')
    assert 'width: 100px' in out
    assert 'background' not in out and 'position' not in out


def test_table_dims_clamped():
    out = _s('<table style="width:99999px"><tr><td>x</td></tr></table>')
    assert 'width: 4000px' in out


def test_table_class_allowlist():
    out = _s('<table class="attacker note-table other"><tr><td>x</td></tr></table>')
    assert 'class="note-table"' in out
    assert 'attacker' not in out


def test_table_colspan_rowspan_clamped():
    out = _s('<td colspan="3" rowspan="999">x</td>')
    assert 'colspan="3"' in out
    assert 'rowspan="100"' in out  # max is 100


def test_empty_string_survives():
    assert _s("") == ""
    assert _s(None) == ""
