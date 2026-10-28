"""The paper pane's "Add to project" button, and what it depends on.

Jack, 2026-09-21: "can you add a button somewhere in the paper view up
here to add a paper to a project."

Membership was only editable from the project side. The reverse entry
point crosses three boundaries, and every one of them fails SILENTLY —
the button is still there, still clickable, and nothing happens:

  * `src/paper-detail.js` calls `window.ProjectMembership.openFor`,
    which `src/projects.js` has to export under exactly that name.
  * It passes the literal kind `"paper"`, which has to be the papers
    MODE's `memberKind` and therefore in Python's
    `_PROJECT_MEMBER_KINDS` (held by test_project_member_kinds.py).
  * It posts to endpoints `python/projects_api.py` has to route.

These are source assertions, not behaviour: projects.js needs a real
DOM and a live `api()`. What they buy is that a rename on one side of
any of those three seams shows up here instead of in Jack's hands.
"""
from __future__ import annotations

import re
from pathlib import Path

from projects_api import _PROJECT_MEMBER_KINDS

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
_PAPER_DETAIL = _SRC / "paper-detail.js"
_PROJECTS_JS = _SRC / "projects.js"
_APP_JS = _SRC / "app.js"
_PROJECTS_API = _ROOT / "python" / "projects_api.py"


def _nocomments(src: str) -> str:
    """Strip both comment forms before searching.

    A test asserting "this file references X" otherwise matches the
    comment that merely mentions X — projects.js's new section carries
    a comment naming paper-detail.js, and paper-detail.js carries one
    naming projects.js. That trap has bitten this suite repeatedly."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.split("\n"))


def _read(p: Path) -> str:
    return _nocomments(p.read_text(encoding="utf-8"))


# ---------- the button exists and is wired ----------

def test_the_paper_pane_renders_and_wires_the_button():
    """Catches rendering the button without wiring it, or wiring an id
    that is never rendered — both leave a control that does nothing.

    The id is required in two distinct roles: inside the `.pd-head-actions`
    markup, and in the lookup that attaches the handler. Since 2026-09-25
    that lookup is scoped to the render host (`q(...)`, see
    test_paper_view_single_renderer.py), not the document-wide `$()`.
    """
    src = _read(_PAPER_DETAIL)
    assert 'id="btn-add-to-project"' in src, "button not rendered"
    assert 'q("#btn-add-to-project")' in src, "button never looked up"
    # Rendered inside the header action group Jack pointed at, not
    # somewhere further down the pane.
    head = src[src.index('class="pd-head-actions"'):]
    head = head[:head.index("</div>")]
    assert 'id="btn-add-to-project"' in head


# ---------- seam 1: the exported entry point ----------

def test_paper_detail_calls_an_entry_point_projects_actually_exports():
    """Catches renaming `ProjectMembership.openFor` on one side.

    paper-detail.js resolves it at click time off `window`, so a rename
    in projects.js raises only when the user clicks — there is no load
    error, no console warning until then.
    """
    caller = _read(_PAPER_DETAIL)
    owner = _read(_PROJECTS_JS)
    assert "window.ProjectMembership.openFor(" in caller
    assert re.search(r"window\.ProjectMembership\s*=\s*\{[^}]*openFor", owner), \
        "projects.js does not export ProjectMembership.openFor"


def test_membership_logic_lives_in_projects_not_the_paper_pane():
    """Catches paper-detail.js growing its own membership calls.

    The paper pane is a renderer. If it starts POSTing to
    /api/project/<id>/members itself there are two places that know how
    membership is edited, and the project-side one is the one with the
    count/refresh handling.
    """
    caller = _read(_PAPER_DETAIL)
    assert "/api/project/" not in caller
    assert "/api/member-projects/" not in caller


# ---------- seam 2: the member kind ----------

def test_the_kind_passed_from_the_paper_pane_is_a_real_member_kind():
    """Catches passing a kind the server rejects.

    `openFor("paper", slug)` hard-codes the string. If the papers MODE's
    `memberKind` were ever renamed, Python's validation would 400 on
    every click while both sides still looked self-consistent.
    """
    caller = _read(_PAPER_DETAIL)
    m = re.search(r'window\.ProjectMembership\.openFor\(\s*"([a-z]+)"', caller)
    assert m, "could not find the kind passed to openFor"
    kind = m.group(1)
    assert kind in _PROJECT_MEMBER_KINDS
    app = _read(_APP_JS)
    assert f'memberKind: "{kind}"' in app, \
        f"{kind!r} is not declared as a memberKind on any MODES entry"


# ---------- seam 3: the endpoints ----------

def test_the_picker_only_calls_endpoints_that_are_routed():
    """Catches a typo'd or renamed URL.

    Both are built with template literals, so a wrong path is a 404 at
    click time rather than anything a linter would catch.
    """
    owner = _read(_PROJECTS_JS)
    api = _PROJECTS_API.read_text(encoding="utf-8")
    assert "/api/member-projects/" in owner
    assert '"/api/member-projects/<kind>/<mid>"' in api
    assert "/members" in owner
    assert '"/api/project/<pid>/members"' in api


# ---------- the shared shell ----------

def test_both_pickers_go_through_one_shell():
    """Catches a third copy of the picker modal markup.

    projects.js already carried a comment admitting the modal markup was
    duplicated with notes.js. Adding the paper-side picker as a second
    copy inside the same file is where that stops being acceptable, so
    the shell was extracted. This asserts it stayed extracted: exactly
    one place builds the overlay.
    """
    owner = _read(_PROJECTS_JS)
    assert owner.count("modal-overlay pj-picker-overlay") == 1, \
        "the picker overlay markup is built in more than one place"
    # One definition plus two call sites. Counted separately because the
    # definition's own destructured signature matches a naive search for
    # the call shape — which is how this assertion first read 3 and
    # failed against correct code.
    assert owner.count("function _pickerShell({") == 1, "shell defined more than once"
    assert owner.count("_pickerShell({") == 3, \
        "expected one definition and exactly two callers"


def test_a_failed_toggle_does_not_report_success():
    """Catches optimistically flipping the tick.

    The picker stays open so several projects can be ticked in a row, so
    it has to re-render rows from what the server did. Returning the
    intended state on error would show a checkmark against a project the
    paper was never filed into.
    """
    owner = _read(_PROJECTS_JS)
    fn = owner[owner.index("async function _toggleMembership"):]
    fn = fn[:fn.index("\nwindow.ProjectMembership")]
    catch = fn[fn.index("catch"):]
    assert "return wasSelected" in catch, \
        "_toggleMembership must return the UNCHANGED state when the call fails"
