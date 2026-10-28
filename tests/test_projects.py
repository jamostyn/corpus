"""Projects — folders of papers and notes that don't move anything.

Added 2026-09-14 on Jack's request: "a tab for projects … these are
essentially folders of notes and papers. the notes and papers arent
actually stored in these folders, just organized that way. papers and
notes can be in multiple projects."

These are real behavioural tests through the Flask test client, not
source assertions — the whole feature is server-side CRUD over JSON
files, which the test client exercises directly.
"""
from __future__ import annotations

import json

import pytest


def _summary(corpus_dir, slug, title="A Paper", year=2020):
    (corpus_dir / "summaries" / f"{slug}.md").write_text(
        f"---\ntitle: {title}\nyear: {year}\nauthor: Test, A.\n---\n\n## References\n",
        encoding="utf-8")


def _note(corpus_dir, nid, title="A Note"):
    (corpus_dir / "notes" / f"{nid}.json").write_text(
        json.dumps({"id": nid, "title": title, "body_html": "",
                    "updated_at": "2026-09-14T00:00:00+00:00"}),
        encoding="utf-8")


def _mk(client, title="Proj"):
    return client.post("/api/projects", json={"title": title}).get_json()["id"]


# ---------- The defining property -------------------------------------

def test_a_paper_can_be_in_several_projects_at_once(client, corpus_dir):
    """Catches: storing membership as a single owning project.

    This is the requirement in Jack's own words — "papers and notes can
    be in multiple projects". A one-project-per-paper model (a `project`
    scalar on the summary, or a move-on-add) would pass a naive
    add-then-read test and fail only here."""
    _summary(corpus_dir, "schunn-2001")
    a, b = _mk(client, "Prelims"), _mk(client, "Methods")
    for pid in (a, b):
        client.post(f"/api/project/{pid}/members",
                    json={"kind": "paper", "id": "schunn-2001", "op": "add"})
    for pid in (a, b):
        got = client.get(f"/api/project/{pid}").get_json()
        assert [r["id"] for r in got["resolved"]["paper"]] == ["schunn-2001"]
    names = {p["title"] for p in
             client.get("/api/member-projects/paper/schunn-2001").get_json()}
    assert names == {"Prelims", "Methods"}


def test_adding_a_paper_does_not_move_or_touch_it(client, corpus_dir):
    """Catches: an implementation that files papers by moving the .md
    into a project folder.

    "The notes and papers arent actually stored in these folders." A
    move would break every other feature at once — the citation index,
    the aggregators and the PDF path all resolve from `summaries/`."""
    _summary(corpus_dir, "yang-2020")
    before = (corpus_dir / "summaries" / "yang-2020.md").read_text(encoding="utf-8")
    pid = _mk(client)
    client.post(f"/api/project/{pid}/members",
                json={"kind": "paper", "id": "yang-2020", "op": "add"})
    assert (corpus_dir / "summaries" / "yang-2020.md").exists()
    assert (corpus_dir / "summaries" / "yang-2020.md").read_text(encoding="utf-8") == before


def test_membership_survives_a_summary_rewrite(client, corpus_dir):
    """Catches: moving membership into the summary's YAML frontmatter.

    `prefill_summary.render_frontmatter` emits a FIXED field list with
    no pass-through, so a `projects:` key there is deleted by the next
    Re-extract — silently. This test simulates that rewrite (the
    frontmatter is replaced wholesale, as render_summary does) and
    asserts the membership is still there afterwards."""
    _summary(corpus_dir, "kadlec-2024")
    pid = _mk(client)
    client.post(f"/api/project/{pid}/members",
                json={"kind": "paper", "id": "kadlec-2024", "op": "add"})
    # Simulate a re-extract: the .md is rewritten from scratch.
    _summary(corpus_dir, "kadlec-2024", title="Rewritten By Re-extract")
    got = client.get(f"/api/project/{pid}").get_json()
    assert [r["id"] for r in got["resolved"]["paper"]] == ["kadlec-2024"]
    assert got["resolved"]["paper"][0]["title"] == "Rewritten By Re-extract"


def test_deleting_a_project_leaves_its_contents_alone(client, corpus_dir):
    """Catches: a cascade delete.

    A project is an organizational overlay. Deleting the folder must
    never delete the papers or notes filed in it — that would be
    unrecoverable data loss from a button labelled "Delete project"."""
    _summary(corpus_dir, "pan-2025")
    _note(corpus_dir, "n1")
    pid = _mk(client)
    for kind, mid in (("paper", "pan-2025"), ("note", "n1")):
        client.post(f"/api/project/{pid}/members", json={"kind": kind, "id": mid, "op": "add"})
    assert client.delete(f"/api/project/{pid}").status_code == 200
    assert (corpus_dir / "summaries" / "pan-2025.md").exists()
    assert (corpus_dir / "notes" / "n1.json").exists()


# ---------- Membership mechanics --------------------------------------

def test_adding_the_same_member_twice_is_a_no_op(client, corpus_dir):
    """Catches: appending without a membership check.

    The UI fires add from a picker row; a double-tap or a stale list
    would otherwise produce a duplicate row that renders twice and
    needs two clicks to remove."""
    _summary(corpus_dir, "dale-2021")
    pid = _mk(client)
    for _ in range(3):
        r = client.post(f"/api/project/{pid}/members",
                        json={"kind": "paper", "id": "dale-2021", "op": "add"}).get_json()
    assert r["counts"]["paper"] == 1


def test_deleted_members_are_filtered_but_not_pruned_from_disk(client, corpus_dir):
    """Catches: rewriting the project file to drop unresolvable ids.

    A paper can be missing temporarily — the corpus dir pointed at the
    wrong folder, a PDF mid-move. Filtering on read hides it; pruning
    on read would permanently forget the membership the first time
    anyone opened the tab, with no way back."""
    _summary(corpus_dir, "ghost-1999")
    pid = _mk(client)
    client.post(f"/api/project/{pid}/members",
                json={"kind": "paper", "id": "ghost-1999", "op": "add"})
    (corpus_dir / "summaries" / "ghost-1999.md").unlink()

    got = client.get(f"/api/project/{pid}").get_json()
    assert got["resolved"]["paper"] == [], "a missing paper must not render"
    on_disk = json.loads((corpus_dir / "projects" / f"{pid}.json").read_text())
    assert on_disk["members"]["paper"] == ["ghost-1999"], "membership must survive on disk"

    # And it comes back when the paper does.
    _summary(corpus_dir, "ghost-1999", title="Returned")
    again = client.get(f"/api/project/{pid}").get_json()
    assert [r["id"] for r in again["resolved"]["paper"]] == ["ghost-1999"]


def test_a_title_edit_cannot_clobber_the_member_list(client, corpus_dir):
    """Catches: letting PUT /api/project/<id> accept a `members` key.

    The detail pane autosaves title+description on a debounce. If PUT
    also wrote members, an autosave carrying a stale in-memory copy
    would silently drop anything added since the pane loaded."""
    _summary(corpus_dir, "han-2025")
    pid = _mk(client)
    client.post(f"/api/project/{pid}/members",
                json={"kind": "paper", "id": "han-2025", "op": "add"})
    client.put(f"/api/project/{pid}",
               json={"title": "Renamed", "members": {"paper": [], "note": []}})
    got = client.get(f"/api/project/{pid}").get_json()
    assert got["title"] == "Renamed"
    assert [r["id"] for r in got["resolved"]["paper"]] == ["han-2025"]


def test_removing_a_member_leaves_the_others(client, corpus_dir):
    """Catches: a remove that clears the whole kind rather than one id."""
    for s in ("a-2001", "b-2002", "c-2003"):
        _summary(corpus_dir, s)
    pid = _mk(client)
    for s in ("a-2001", "b-2002", "c-2003"):
        client.post(f"/api/project/{pid}/members", json={"kind": "paper", "id": s, "op": "add"})
    r = client.post(f"/api/project/{pid}/members",
                    json={"kind": "paper", "id": "b-2002", "op": "remove"}).get_json()
    assert [x["id"] for x in r["resolved"]["paper"]] == ["a-2001", "c-2003"]


# ---------- Input validation ------------------------------------------

@pytest.mark.parametrize("mid", ["../../etc/passwd", "a/b", "..", ""])
def test_member_ids_that_could_escape_the_corpus_are_rejected(client, corpus_dir, mid):
    """Catches: dropping the id pattern check.

    Member ids are turned into filesystem paths when titles are
    resolved (`summaries/<id>.md`, `notes/<id>.json`). An unvalidated
    id is a path-traversal read."""
    pid = _mk(client)
    r = client.post(f"/api/project/{pid}/members",
                    json={"kind": "paper", "id": mid, "op": "add"})
    assert r.status_code == 400


def test_unknown_member_kinds_are_rejected(client, corpus_dir):
    """Catches: accepting any string as a kind.

    A kind the UI cannot render would write a member that is invisible
    and unremovable through the interface."""
    pid = _mk(client)
    r = client.post(f"/api/project/{pid}/members",
                    json={"kind": "institution", "id": "x", "op": "add"})
    assert r.status_code == 400


def test_adding_a_member_that_does_not_exist_is_refused(client, corpus_dir):
    """Catches: trusting the client's id.

    Without the existence check a typo'd or stale id becomes a
    permanently-invisible member — stored, filtered out on every read,
    and impossible to remove from the UI because it never renders."""
    pid = _mk(client)
    r = client.post(f"/api/project/{pid}/members",
                    json={"kind": "paper", "id": "never-existed", "op": "add"})
    assert r.status_code == 404


def test_a_hand_edited_project_file_degrades_instead_of_500ing(client, corpus_dir):
    """Catches: assuming `members` is well-formed.

    Project files are plain JSON in the user's corpus dir; Jack edits
    files by hand. A malformed members block must yield an empty
    folder, not take the whole Projects tab down."""
    pid = _mk(client)
    p = corpus_dir / "projects" / f"{pid}.json"
    data = json.loads(p.read_text())
    data["members"] = "not a dict"
    p.write_text(json.dumps(data), encoding="utf-8")
    got = client.get(f"/api/project/{pid}")
    assert got.status_code == 200
    assert got.get_json()["resolved"]["paper"] == []
    assert client.get("/api/projects").status_code == 200


# ---------- CRUD basics ------------------------------------------------

def test_create_rename_and_list(client, corpus_dir):
    """Catches: a rename that doesn't persist, or a list that doesn't
    reflect it. Jack asked specifically to "create new projects and
    edit the title"."""
    pid = _mk(client, "First")
    assert client.put(f"/api/project/{pid}",
                      json={"title": "Second"}).get_json()["title"] == "Second"
    rows = client.get("/api/projects").get_json()
    assert [r["title"] for r in rows] == ["Second"]


def test_a_blank_title_falls_back_instead_of_saving_empty(client, corpus_dir):
    """Catches: allowing an empty title.

    The sidebar row is the title; an empty one produces an
    unclickable-looking blank line."""
    pid = _mk(client, "Named")
    assert client.put(f"/api/project/{pid}",
                      json={"title": "   "}).get_json()["title"] == "Untitled project"


def test_missing_project_is_404_not_500(client, corpus_dir):
    """Catches: unguarded path construction on an unknown id."""
    assert client.get("/api/project/nope").status_code == 404
    assert client.put("/api/project/nope", json={"title": "x"}).status_code == 404
    assert client.delete("/api/project/nope").status_code == 404
