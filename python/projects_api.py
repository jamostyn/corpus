"""Corpus — /api/projects blueprint. Added 2026-09-14.

Owns:
  * The six project endpoints (list, create, get, put, delete, members).
  * The member-kind allow-list.
  * Projects-JSON storage helpers (id generation, sidebar-row shape).

Project files live at `<corpus_dir>/projects/<id>.json` (see
_paths.projects_dir()).

WHY MEMBERSHIP LIVES ON THE PROJECT
-----------------------------------
A project is a folder of papers and notes that does not move them. The
membership fact has to be stored somewhere, and there are only two
candidates: on the project, or on each member.

On each member is disqualified, not merely disliked.
`prefill_summary.render_frontmatter` emits a FIXED list of fields; it
has no pass-through for keys it doesn't recognise. A `projects:` key
written into a summary's frontmatter is therefore deleted the next
time that paper is re-extracted — silently, with no error. The same
reasoning already put highlights, pdf_refs and notes in their own
sidecar directories; see their docstrings in `_paths.py`.

So the project file holds the IDs, and the reverse direction ("which
projects contain this paper?") is DERIVED by scanning project files.
That mirrors `citations.py`: the relation is computed from what is on
disk rather than stored twice, so there is no second copy to fall out
of sync and no repair pass when something is deleted.

DANGLING MEMBERS ARE FILTERED, NOT PRUNED
-----------------------------------------
A project can name a paper or note that no longer exists. Read paths
filter those out so the UI never shows a broken row, but nothing
rewrites the file to remove them. Pruning on read would mean a paper
that is temporarily absent — a corpus dir pointed at the wrong folder,
a PDF mid-move — permanently loses its project membership the moment
anyone opens the tab. Filtering is reversible; pruning is not.

Wired in server.py via `app.register_blueprint(projects_bp)`.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from _api_common import require_corpus_or_abort, _walk_summaries
from _paths import notes_dir, projects_dir, summaries_dir

logger = logging.getLogger("corpus.projects_api")

projects_bp = Blueprint("projects", __name__)


# ---------- Member kinds ---------------------------------------------

# What a project can contain. MUST match `window.PROJECT_MEMBER_KINDS`
# in src/app.js, which derives from the MODES entries declaring
# `memberKind`. The two lists are in different languages and nothing
# else keeps them together; parity is enforced by
# tests/test_project_member_kinds.py.
#
# Adding a kind here without adding the matching MODES field gives an
# endpoint that accepts members the UI can never display.
_PROJECT_MEMBER_KINDS = ("paper", "note", "document")

# Paper slugs and note ids only ever contain these characters. Member
# ids are used to build filesystem paths when resolving titles, so an
# unvalidated id would be a path-traversal vector ("../../etc/passwd").
#
# The lookahead requires at least one alphanumeric, which is what
# rejects "." and ".." — both match a plain [A-Za-z0-9._-]+ character
# class, since "." is a legal slug character ("10.1038" appears in
# DOIs). Neither escapes the corpus dir as written today (they land on
# literal filenames like "...md"), but storing them means a member row
# that can never resolve and never render.
_MEMBER_ID_RE = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9._-]{1,200}$")

_UNTITLED = "Untitled project"


# ---------- Storage helpers ------------------------------------------

def _project_id() -> str:
    """Time-prefixed so `ls` shows projects in creation order; UUID
    suffix guarantees uniqueness across rapid taps. Same scheme as
    notes_api._note_id()."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_members() -> dict:
    return {k: [] for k in _PROJECT_MEMBER_KINDS}


def _clean_members(raw) -> dict:
    """Coerce whatever is on disk into {kind: [id, ...]}.

    Tolerates a missing or malformed `members` block rather than
    throwing: a hand-edited project file should degrade to an empty
    folder, not take the whole tab down."""
    out = _empty_members()
    if not isinstance(raw, dict):
        return out
    for kind in _PROJECT_MEMBER_KINDS:
        vals = raw.get(kind)
        if not isinstance(vals, list):
            continue
        seen = set()
        for v in vals:
            v = str(v).strip()
            if v and _MEMBER_ID_RE.match(v) and v not in seen:
                seen.add(v)
                out[kind].append(v)
    return out


def _read_project(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("project_unreadable path=%s", path.name, exc_info=True)
        return None
    if not isinstance(data, dict):
        return None
    data["id"] = data.get("id") or path.stem
    data["title"] = (data.get("title") or "").strip() or _UNTITLED
    data["description"] = (data.get("description") or "").strip()
    data["members"] = _clean_members(data.get("members"))
    return data


def _write_project(data: dict) -> None:
    p = projects_dir() / f"{data['id']}.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _project_path_or_404(pid: str) -> Path:
    if not _MEMBER_ID_RE.match(pid or ""):
        abort(404, description="project_missing")
    p = projects_dir() / f"{pid}.json"
    if not p.exists():
        abort(404, description="project_missing")
    return p


# ---------- Existence + title resolution ------------------------------

def _member_exists(kind: str, mid: str) -> bool:
    """Cheap existence check — no parsing. Used by the list endpoint so
    showing N projects doesn't mean parsing every summary in the
    corpus."""
    if not _MEMBER_ID_RE.match(mid):
        return False
    if kind == "paper":
        return (summaries_dir() / f"{mid}.md").exists()
    if kind == "note":
        return (notes_dir() / f"{mid}.json").exists()
    if kind == "document":
        from documents_api import document_exists
        return document_exists(mid)
    return False


def _paper_titles() -> dict:
    """slug -> display fields, for resolving a project's paper members."""
    out = {}
    for slug, fm, _body in _walk_summaries():
        out[slug] = {
            "id": slug,
            "title": (fm.get("title") or "").strip() or slug,
            "year": str(fm.get("year") or "").strip(),
            "author": (fm.get("author") or "").strip(),
        }
    return out


def _note_titles() -> dict:
    """note id -> display fields."""
    out = {}
    for p in notes_dir().glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        nid = data.get("id") or p.stem
        out[nid] = {
            "id": nid,
            "title": (data.get("title") or "").strip() or "Untitled note",
            "updated_at": data.get("updated_at") or "",
        }
    return out


def _resolve_members(members: dict) -> dict:
    """Expand stored IDs into display rows, dropping ids that no longer
    resolve. Order follows the stored list so the UI is stable."""
    papers = _paper_titles()
    notes = _note_titles()
    from documents_api import document_titles   # documents: 2026-09-25
    lookup = {"paper": papers, "note": notes, "document": document_titles()}
    out = {}
    for kind in _PROJECT_MEMBER_KINDS:
        table = lookup.get(kind, {})
        out[kind] = [table[mid] for mid in members.get(kind, []) if mid in table]
    return out


def _counts(members: dict) -> dict:
    """Existing-member counts for the sidebar row."""
    return {k: sum(1 for mid in members.get(k, []) if _member_exists(k, mid))
            for k in _PROJECT_MEMBER_KINDS}


def _project_row(data: dict) -> dict:
    return {
        "id": data["id"],
        "title": data["title"],
        "description": data["description"],
        "counts": _counts(data["members"]),
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or data.get("created_at") or "",
    }


# ---------- Endpoints -------------------------------------------------

@projects_bp.route("/api/projects", methods=["GET"])
def list_projects():
    require_corpus_or_abort()
    rows = []
    for p in projects_dir().glob("*.json"):
        data = _read_project(p)
        if data:
            rows.append(_project_row(data))
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return jsonify(rows)


@projects_bp.route("/api/projects", methods=["POST"])
def create_project():
    require_corpus_or_abort()
    payload = request.get_json(silent=True) or {}
    pid = _project_id()
    now = _iso_now()
    data = {
        "id": pid,
        "title": (payload.get("title") or "").strip() or _UNTITLED,
        "description": (payload.get("description") or "").strip(),
        "members": _clean_members(payload.get("members")),
        "created_at": now,
        "updated_at": now,
    }
    _write_project(data)
    logger.info("project_created id=%s title=%r", pid, data["title"])
    return jsonify(data)


@projects_bp.route("/api/project/<pid>", methods=["GET"])
def get_project(pid):
    require_corpus_or_abort()
    data = _read_project(_project_path_or_404(pid))
    if data is None:
        abort(404, description="project_missing")
    out = dict(data)
    out["resolved"] = _resolve_members(data["members"])
    out["counts"] = {k: len(v) for k, v in out["resolved"].items()}
    return jsonify(out)


@projects_bp.route("/api/project/<pid>", methods=["PUT"])
def update_project(pid):
    """Title / description only. Membership goes through /members so a
    title edit can never clobber the member list — the note editor's
    autosave PUTs the whole object, and a project pane doing the same
    would drop members added in another pane since load."""
    require_corpus_or_abort()
    p = _project_path_or_404(pid)
    data = _read_project(p)
    if data is None:
        abort(404, description="project_missing")
    payload = request.get_json(silent=True) or {}
    if "title" in payload:
        data["title"] = (payload["title"] or "").strip() or _UNTITLED
    if "description" in payload:
        data["description"] = (payload["description"] or "").strip()
    data["updated_at"] = _iso_now()
    _write_project(data)
    logger.info("project_updated id=%s title=%r", pid, data["title"])
    return jsonify(data)


@projects_bp.route("/api/project/<pid>", methods=["DELETE"])
def delete_project(pid):
    """Deletes the folder, never its contents. Papers and notes are not
    stored here and are unaffected."""
    require_corpus_or_abort()
    p = _project_path_or_404(pid)
    p.unlink()
    logger.info("project_deleted id=%s", pid)
    return jsonify({"ok": True, "id": pid})


@projects_bp.route("/api/project/<pid>/members", methods=["POST"])
def edit_members(pid):
    """Add or remove ONE member. Body: {kind, id, op}.

    `op` is "add" or "remove". Adding an id already present is a no-op
    rather than an error — the UI can fire it from a checkbox without
    tracking prior state.
    """
    require_corpus_or_abort()
    p = _project_path_or_404(pid)
    data = _read_project(p)
    if data is None:
        abort(404, description="project_missing")

    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("kind") or "").strip()
    mid = str(payload.get("id") or "").strip()
    op = str(payload.get("op") or "add").strip()

    if kind not in _PROJECT_MEMBER_KINDS:
        abort(400, description="bad_member_kind")
    if not _MEMBER_ID_RE.match(mid):
        abort(400, description="bad_member_id")
    if op not in ("add", "remove"):
        abort(400, description="bad_member_op")
    if op == "add" and not _member_exists(kind, mid):
        abort(404, description="member_missing")

    lst = data["members"].setdefault(kind, [])
    if op == "add":
        if mid not in lst:
            lst.append(mid)
    else:
        data["members"][kind] = [x for x in lst if x != mid]

    data["updated_at"] = _iso_now()
    _write_project(data)
    logger.info("project_member_%s id=%s kind=%s member=%s count=%d",
                op, pid, kind, mid, len(data["members"][kind]))

    out = dict(data)
    out["resolved"] = _resolve_members(data["members"])
    out["counts"] = {k: len(v) for k, v in out["resolved"].items()}
    return jsonify(out)


@projects_bp.route("/api/member-projects/<kind>/<mid>", methods=["GET"])
def member_projects(kind, mid):
    """Which projects contain this paper / note.

    Derived by scanning project files — the reverse index is never
    stored. See the module docstring for why."""
    require_corpus_or_abort()
    if kind not in _PROJECT_MEMBER_KINDS:
        abort(400, description="bad_member_kind")
    if not _MEMBER_ID_RE.match(mid or ""):
        abort(400, description="bad_member_id")
    rows = []
    for p in projects_dir().glob("*.json"):
        data = _read_project(p)
        if data and mid in data["members"].get(kind, []):
            rows.append({"id": data["id"], "title": data["title"]})
    rows.sort(key=lambda r: r["title"].lower())
    return jsonify(rows)
