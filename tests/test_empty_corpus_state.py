"""The empty main pane must say WHICH empty it is.

Bug, 2026-09-09: `corpus_dir` had been pointed at a folder of 4288
unrelated files. `loadPapers()` succeeded with `[]`, `hideEmptyState()`
ran, and the app rendered a blank sidebar and a blank pane with no
message. A mis-pointed folder was visually identical to a working
corpus that happens to be empty.

These are source-level assertions on `src/app.js` and `src/index.html`.
The boot path lives in an async IIFE that needs `fetch`, the DOM and a
running server, so the vm harness cannot execute it — see TESTING.md
§ Known gaps. What IS checkable is that the two cases are still
distinguished and that the path is still surfaced.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
_APP = _SRC / "app.js"
_HTML = _SRC / "index.html"


def _app() -> str:
    return _APP.read_text(encoding="utf-8")


def test_an_empty_corpus_keeps_the_empty_state_visible():
    """Catches: reverting to an unconditional `hideEmptyState()` after
    loadPapers.

    That is the exact shape of the original bug — the load SUCCEEDS
    with zero papers, so nothing errors and nothing is shown. The
    regression is silent by construction."""
    src = _app()
    boot = src[src.index("if (state.config.corpus_dir)"):]
    boot = boot[:boot.index("\n}")]
    assert "state.papers.length" in boot, (
        "boot must branch on whether any papers were actually loaded")
    assert 'showEmptyState("empty-corpus")' in boot, (
        "an empty corpus must show the empty-corpus state")


def test_the_two_empty_reasons_are_distinguished():
    """Catches: collapsing both cases back into one message.

    'Pick a corpus directory to get started' is wrong and confusing
    when a directory IS picked — it implies the app did not register
    the choice."""
    src = _app()
    assert 'showEmptyState("no-corpus")' in src
    assert 'showEmptyState("empty-corpus")' in src
    fn = src[src.index("function showEmptyState("):
             src.index("function hideEmptyState(")]
    assert 'reason === "empty-corpus"' in fn


def test_the_empty_corpus_message_names_the_path():
    """Catches: dropping the corpus path from the message.

    Naming the folder is the whole fix. Without it the user still
    cannot tell a mis-point from a genuinely empty corpus — they would
    have to open Settings to find out where the app is reading from."""
    src = _app()
    fn = src[src.index("function showEmptyState("):
             src.index("function hideEmptyState(")]
    assert "corpus_dir" in fn, "the message must read the configured path"
    assert "#empty-state-path" in fn, "the path element must be looked up"
    # Asserting the lookups exist is NOT enough: a mutation that deleted
    # the two assignment lines left both references in place (the `const`
    # declarations) and still passed. Check the value is actually written
    # to the element and that the element is un-hidden for this case.
    assert re.search(r"path\.textContent\s*=\s*dir", fn), (
        "the resolved corpus_dir must be written into #empty-state-path")
    assert re.search(r"path\.hidden\s*=\s*!dir", fn), (
        "the path element must be revealed when a dir is known")


def test_the_elements_the_function_writes_to_exist_in_the_markup():
    """Catches: the JS targeting ids the HTML no longer has.

    `$()` returns null and the assignment throws, taking the whole boot
    path down — so a rename here turns a cosmetic fix into a blank
    app."""
    html = _HTML.read_text(encoding="utf-8")
    for el_id in ("empty-state", "empty-state-title", "empty-state-body",
                  "empty-state-path", "empty-choose-dir"):
        assert f'id="{el_id}"' in html, f"index.html is missing #{el_id}"


def test_the_path_element_hides_properly():
    """Catches: the `[hidden]` gotcha. `.empty-state-path` is given
    `display: inline-block`, which BEATS the default
    `[hidden] { display: none }` — so without an explicit override the
    path stays on screen in the first-run state, showing an empty grey
    box."""
    css = (_SRC / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.empty-state-path\[hidden\]\s*\{[^}]*display:\s*none",
                     css), (
        ".empty-state-path sets display, so it needs an explicit "
        "[hidden] override")


def test_scaffolding_docstring_matches_behaviour():
    """Catches: the docstring drifting back to claiming a guard that
    does not exist.

    `ensure_corpus_layout` said it created subdirs 'if the user-picked
    root is empty'. It never checked. That false claim is why nobody
    noticed it scattering directories into a folder of 4288 files."""
    path = (Path(__file__).resolve().parent.parent
            / "python" / "extract" / "_paths.py")
    src = path.read_text(encoding="utf-8")
    fn = src[src.index("def ensure_corpus_layout("):]
    fn = fn[:fn.index("\n\n\n")] if "\n\n\n" in fn else fn
    doc = fn[:fn.index('"""', fn.index('"""') + 3)]
    assert "if the user-picked root is empty" not in doc, (
        "the docstring claims an emptiness check the code does not do")
    assert "UNCONDITIONAL" in doc, (
        "the docstring should state that it scaffolds unconditionally")


# ---------- the loading state ----------
#
# Added 2026-09-20. Jack: "i just re ran the command and it forgot my
# corpus location." Nothing had forgotten anything — `~/.corpus/config.json`
# was correct and untouched. The pane simply started on the no-corpus
# copy and `boot()` cannot reach a conclusion until `loadPapers()`
# returns, which on a cold 209-summary corpus measured ~20s (5.4 MB,
# ~95ms per file on first access; 0.12s warm).
#
# So for twenty seconds Corpus displayed "Pick a corpus directory to
# get started" to a user whose corpus was fine. The message was the
# bug.

def test_the_first_paint_does_not_instruct_the_user_to_pick_a_folder():
    """Catches: the markup starting on a CONCLUSION.

    "Welcome to Corpus / Pick a corpus directory" is what the app says
    when there is no corpus. Rendering it before `loadConfig()` has
    even resolved states something the app does not yet know, and on a
    slow corpus it states it for twenty seconds."""
    html = _HTML.read_text(encoding="utf-8")
    block = html[html.index('id="empty-state"'):html.index('id="empty-choose-dir"')]
    assert "Pick a corpus directory" not in block, (
        "the initial markup still tells the user to pick a directory")
    assert "Loading" in block, "the initial markup should read as loading"


def test_boot_names_the_corpus_before_the_slow_read():
    """Catches: reordering so the path appears only after loadPapers().

    The whole point is that the folder Corpus is using is on screen
    BEFORE the twenty-second read, not after it. If `showEmptyState
    ("loading")` moves below `loadPapers()`, the user is back to
    staring at a pane that cannot name their corpus."""
    src = _app()
    fn = src[src.index("async function boot("):src.index("function _hasPywebviewBridge(")]
    load_at = fn.index("await loadPapers()")
    loading_at = fn.index('showEmptyState("loading")')
    assert loading_at < load_at, (
        "the loading state must be shown before loadPapers() is awaited")


def test_the_loading_state_shows_the_configured_path():
    """Catches: a loading message that doesn't say WHICH corpus.

    "Loading…" alone is not an answer to "did it forget my corpus?".
    Naming the folder is the entire remedy for the reported bug."""
    src = _app()
    fn = src[src.index('if (reason === "loading")'):src.index('if (reason === "empty-corpus")')]
    assert "corpus_dir" in fn, "the loading state must read the configured path"
    assert "path.textContent" in fn, "the loading state must render the path"


def test_the_loading_state_offers_no_folder_picker():
    """Catches: leaving the "Choose corpus directory…" button visible
    while loading.

    Offering to change the folder mid-load is what made a working
    corpus look lost — it implies the app is waiting on a decision
    when it is actually just reading."""
    src = _app()
    fn = src[src.index('if (reason === "loading")'):src.index('if (reason === "empty-corpus")')]
    assert "btn.hidden        = true" in fn or "btn.hidden = true" in fn, (
        "the loading state must hide the folder picker")


def test_the_other_two_reasons_still_show_the_button():
    """Catches: hiding the picker for every reason.

    `no-corpus` and `empty-corpus` both NEED the button — it is the
    only way to set or change the folder. A blanket hide would make
    first-run setup impossible."""
    src = _app()
    fn = src[src.index("function showEmptyState("):src.index("function hideEmptyState(")]
    after_loading = fn[fn.index('if (reason === "loading")'):]
    assert "btn.hidden = false" in after_loading, (
        "the non-loading reasons must restore the picker button")
