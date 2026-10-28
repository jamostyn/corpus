"""Guard against the Phase-1 regression: app.js's top-level event-wire
block references functions defined in feature modules (createNote,
selectNote, renderNoteDetail, etc.). If a feature module loads AFTER
app.js, those identifiers are undefined at parse time and the wire
block dies on the first ReferenceError — silently swallowing every
event handler registered further down (which is how "clicking tabs
did nothing" happened once).

The fix: feature modules load BEFORE app.js in index.html. This test
locks that order in so a well-meaning reorder can't reintroduce the
same bug.
"""
from pathlib import Path
import re

_INDEX_HTML = Path(__file__).resolve().parent.parent / "src" / "index.html"


def _script_order():
    """Return the ordered list of <script src="…"> filenames in
    index.html (in document order, external scripts only)."""
    src = _INDEX_HTML.read_text()
    return re.findall(r'<script\s+src="([^"]+)"', src)


def test_feature_modules_load_before_app_js():
    """Every extracted feature module must appear BEFORE app.js in
    index.html's script order. If someone puts app.js first, its
    top-level `addEventListener("click", createNote)` explodes with
    ReferenceError at parse time — no visible failure, just dead
    handlers below the throw site."""
    order = _script_order()
    assert "app.js" in order, "app.js not loaded from index.html"
    app_idx = order.index("app.js")
    for mod in ("notes.js", "paper-detail.js", "author-detail.js",
                "institution-detail.js", "journal-detail.js"):
        assert mod in order, f"{mod} not loaded from index.html"
        assert order.index(mod) < app_idx, (
            f"{mod} must load BEFORE app.js (Phase 1 regression check)"
        )


def test_tooltips_load_first():
    """tooltips.default.js defines the window.TOOLTIPS_DEFAULT dict.
    Everything else assumes it's already there."""
    order = _script_order()
    assert order[0] == "tooltips.default.js", \
        f"expected tooltips.default.js first, got {order[0]}"


def test_provenance_loads_before_detail_modules():
    """provenance.js defines window.Provenance / window.Coverage.
    Every detail module references those namespaces at parse time
    (via `const alias = Provenance.badgeFromArr` at the top of the
    render function), so provenance.js must load first."""
    order = _script_order()
    assert "provenance.js" in order, "provenance.js not loaded from index.html"
    prov_idx = order.index("provenance.js")
    for mod in ("paper-detail.js", "author-detail.js",
                "institution-detail.js", "journal-detail.js"):
        assert order.index(mod) > prov_idx, (
            f"{mod} must load AFTER provenance.js — it aliases "
            f"Provenance.badgeFromArr and Coverage.* at parse time"
        )


def test_nav_loads_before_app_js():
    """nav.js defines window.Nav. app.js's arrow-key handler calls
    `Nav.nextIndex(...)`."""
    order = _script_order()
    assert "nav.js" in order, "nav.js not loaded from index.html"
    assert order.index("nav.js") < order.index("app.js"), (
        "nav.js must load BEFORE app.js"
    )


def test_entity_keys_loads_before_paper_detail():
    """entity-keys.js defines window.EntityKeys. paper-detail.js
    calls EntityKeys.author / EntityKeys.journal at render time when
    building deep-link anchors."""
    order = _script_order()
    assert "entity-keys.js" in order, "entity-keys.js not loaded from index.html"
    assert order.index("entity-keys.js") < order.index("paper-detail.js"), (
        "entity-keys.js must load BEFORE paper-detail.js"
    )


def test_entity_detail_loads_before_author_institution_journal():
    """entity-detail.js defines window.EntityDetail. author-detail /
    institution-detail / journal-detail all call EntityDetail.render()
    from their render function. Load order matters because these
    detail modules alias `EntityDetail` at call time — if it's
    missing when the function runs, the render throws."""
    order = _script_order()
    assert "entity-detail.js" in order, "entity-detail.js not loaded from index.html"
    ed = order.index("entity-detail.js")
    for mod in ("author-detail.js", "institution-detail.js", "journal-detail.js"):
        assert order.index(mod) > ed, (
            f"{mod} must load AFTER entity-detail.js"
        )


def test_corpus_links_loads_before_paper_detail():
    """corpus-links.js defines window.CorpusLinks. paper-detail.js's
    renderDetail calls CorpusLinks.render() unconditionally — it is no
    longer wrapped in a "do we have links?" guard, so if the module
    isn't loaded yet the whole paper-info pane throws on every paper,
    not just on ones with citation links."""
    order = _script_order()
    assert "corpus-links.js" in order, "corpus-links.js not loaded from index.html"
    assert order.index("corpus-links.js") < order.index("paper-detail.js"), (
        "corpus-links.js must load BEFORE paper-detail.js"
    )


def test_modals_loads_before_app_js():
    """modals.js defines window.Modals. app.js's arrow-key handler
    calls `Modals.anyOpen()`. Dev-only modules also call
    `Modals.watchSelector(...)` at load-time, but those are loaded
    dynamically at runtime — only the static ordering vs app.js
    matters here."""
    order = _script_order()
    assert "modals.js" in order, "modals.js not loaded from index.html"
    assert order.index("modals.js") < order.index("app.js"), (
        "modals.js must load BEFORE app.js — app.js's arrow-key "
        "handler references window.Modals at call-time, but the "
        "load-time ordering documents the dependency intent."
    )
