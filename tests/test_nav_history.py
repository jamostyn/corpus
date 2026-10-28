"""Back / forward navigation.

Jack, 2026-09-21: "can you add back and forward arrows somewhere up
here so you can navigate easily between different places?"

A "place" is {mode, id} — the pair every navigation already produces,
since each MODES entry declares the state key holding its selection.

Recording hangs off ONE choke point: every mode's `select` is wrapped
at MODES-construction time. The alternative was recording inside the
six select functions, the deep-link handler, the arrow-key handler and
the project member list — five copies of the same rule, which is how
"changed it here but not there" bugs happen.

`_currentPlace` and `_recordPlace` are pure over `state`, so they are
EXTRACTED from app.js and executed in node rather than asserted as
text. app.js as a whole needs a live DOM (see TESTING.md § Known gaps).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
_APP = _SRC / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _app() -> str:
    return _APP.read_text(encoding="utf-8")


def _extract(name: str) -> str:
    """One top-level function, by brace matching. Raises if it is gone
    — a silent "" would make every assertion below vacuously pass."""
    src = _app()
    start = src.index(f"function {name}(")
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting {name}")


def _run(moves: list) -> dict:
    """Replay a list of places through the REAL recorder.

    Each move is {mode, id, navigating?}. Returns the resulting history
    and index."""
    cap = re.search(r"const HISTORY_MAX = (\d+);", _app())
    assert cap, "HISTORY_MAX is gone"
    script = f"""
const HISTORY_MAX = {cap.group(1)};
const MODES_BY_ID = {{
  papers:   {{ selectedKey: "selectedSlug" }},
  notes:    {{ selectedKey: "selectedNoteId" }},
  projects: {{ selectedKey: "selectedProjectId" }},
}};
const state = {{ mode: "papers", history: [], historyAt: -1, navigating: false,
                selectedSlug: null, selectedNoteId: null, selectedProjectId: null }};
function _refreshNavArrows() {{}}
{_extract("_currentPlace")}
{_extract("_recordPlace")}
for (const mv of {json.dumps(moves)}) {{
  state.mode = mv.mode;
  state[MODES_BY_ID[mv.mode].selectedKey] = mv.id;
  state.navigating = !!mv.navigating;
  _recordPlace();
  state.navigating = false;
}}
console.log(JSON.stringify({{history: state.history, at: state.historyAt}}));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _m(mode, id, navigating=False):
    return {"mode": mode, "id": id, "navigating": navigating}


# ---------- recording ----------

def test_each_new_place_is_recorded_in_order():
    """Catches: not recording, or recording the wrong pair. Without
    this there is nothing to go back to."""
    r = _run([_m("papers", "a"), _m("papers", "b"), _m("notes", "n1")])
    assert [(h["mode"], h["id"]) for h in r["history"]] == [
        ("papers", "a"), ("papers", "b"), ("notes", "n1")]
    assert r["at"] == 2


def test_revisiting_the_same_place_does_not_stack_duplicates():
    """Catches: recording on every render rather than every MOVE.

    `switchMode` re-renders the current selection, and a list click can
    re-select what is already open. Without the no-op check, "back"
    would step through the same paper several times before going
    anywhere — which reads as a broken button."""
    r = _run([_m("papers", "a"), _m("papers", "a"), _m("papers", "a")])
    assert len(r["history"]) == 1


def test_a_tab_switch_with_no_selection_is_still_a_place():
    """Catches: requiring an id to record.

    Switching to an empty Notes tab IS somewhere the user went, and
    back must return from it."""
    r = _run([_m("papers", "a"), _m("notes", None)])
    assert [(h["mode"], h["id"]) for h in r["history"]] == [
        ("papers", "a"), ("notes", None)]


# ---------- the branch rule ----------

def test_moving_after_going_back_discards_the_forward_branch():
    """Catches: appending instead of truncating.

    This is the one rule people get wrong. Go a→b→c, press back twice
    to a, then navigate to d: c and b are gone, exactly as in a
    browser. Keeping them would make forward jump somewhere the user
    never went from here."""
    # a, b, c recorded; then "back" to a (navigating, not recorded);
    # then a real move to d.
    r = _run([_m("papers", "a"), _m("papers", "b"), _m("papers", "c")])
    assert r["at"] == 2
    # Simulate: historyAt moved to 0 by _goToPlace, then a new move.
    script_moves = [_m("papers", "a"), _m("papers", "b"), _m("papers", "c")]
    # replay with an explicit rewind is not expressible through _run,
    # so assert the truncation rule directly on the source instead.
    src = _app()
    fn = src[src.index("function _recordPlace("):src.index("async function _goToPlace(")]
    assert "slice(0, state.historyAt + 1)" in fn, (
        "a new move must truncate the forward branch")


def test_navigating_through_history_records_nothing():
    """Catches: dropping the `navigating` guard.

    Without it, pressing back RECORDS the place it landed on, so the
    history grows every time you move through it and forward can never
    work — the classic broken-back-button bug."""
    r = _run([_m("papers", "a"), _m("papers", "b"),
              _m("papers", "a", navigating=True)])
    assert len(r["history"]) == 2, "a history move was recorded as a new place"
    assert r["at"] == 1


def test_history_is_capped():
    """Catches: unbounded growth. A long session would otherwise keep
    every place forever."""
    cap = int(re.search(r"const HISTORY_MAX = (\d+);", _app()).group(1))
    r = _run([_m("papers", f"p{i}") for i in range(cap + 25)])
    assert len(r["history"]) == cap
    # The OLDEST entries are the ones dropped.
    assert r["history"][-1]["id"] == f"p{cap + 24}"


# ---------- wiring ----------

def test_recording_happens_at_exactly_one_choke_point():
    """Catches: re-sprinkling `_recordPlace()` into individual select
    functions.

    The wrap over `MODES[].select` is what makes every current AND
    future navigation path record. Calls scattered per-handler drift,
    and the one that gets forgotten is a place you cannot go back
    from."""
    src = "\n".join(l for l in _app().split("\n")
                    if not l.strip().startswith("//"))
    wrap = re.search(r"for \(const m of MODES\) \{\s*const raw = m\.select;", src)
    assert wrap, "the select wrap is gone"
    # _recordPlace is called from: the wrap, switchMode, and nowhere else.
    calls = len(re.findall(r"_recordPlace\(\)", src)) - 1   # minus the definition
    assert calls == 2, (
        f"expected exactly 2 call sites (the select wrap + switchMode), found {calls}")


def test_the_arrows_disable_at_both_ends():
    """Catches: arrows that look live with nowhere to go.

    They sit beside always-enabled tabs, so an un-disabled arrow reads
    as a dead control rather than an end-of-history state."""
    fn = _extract("_refreshNavArrows")
    assert "state.historyAt <= 0" in fn, "back must disable at the start"
    assert "state.historyAt >= state.history.length - 1" in fn, (
        "forward must disable at the end")


def test_creating_a_note_or_project_records_the_jump():
    """Catches: the create-then-select paths calling the raw function.

    `createNote` and `createProject` land you on the new thing — a
    navigation you must be able to come back from. They called
    `selectNote(...)` / `selectProject(...)` directly, bypassing the
    wrap."""
    for name, mode in (("notes.js", "notes"), ("projects.js", "projects")):
        src = (_SRC / name).read_text(encoding="utf-8")
        assert f"MODES_BY_ID.{mode}.select(" in src, (
            f"{name} still selects without going through the wrap")
