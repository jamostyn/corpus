"""Corpus — /api/notes blueprint. Split from server.py on 2026-08-15.

Owns:
  * The five note endpoints (list, create, get, put, delete).
  * The HTML sanitiser + its allow-list constants.
  * Notes-JSON storage helpers (id generation, sidebar-row shape).

Notes files live at `<corpus_dir>/notes/<id>.json` (see _paths.notes_dir()).

Wired in server.py via `app.register_blueprint(notes_bp)`.
"""
from __future__ import annotations

import html as _htmllib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from _api_common import require_corpus_or_abort
from _paths import notes_dir

logger = logging.getLogger("corpus.notes_api")

notes_bp = Blueprint("notes", __name__)


# ---------- Sanitiser allow-lists ------------------------------------

# HTML tags the notes editor can produce. Everything else gets
# stripped so pasted content / prompt-injected HTML can't ship scripts
# or event handlers into future viewer sessions. Kept in one place so
# the frontend toolbar (src/notes.js) and this sanitizer stay aligned.
_NOTE_ALLOWED_TAGS = frozenset({
    "p", "br", "div", "span",
    "strong", "b", "em", "i", "u", "s", "strike",
    "h1", "h2", "h3", "h4",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "a", "hr",
    "table", "thead", "tbody", "tr", "td", "th", "colgroup", "col",
})
# Entity types a note can deep-link to. MUST match `LINK_ATTRS` in
# src/app.js, which derives from the MODES entries that declare
# `linkAttr`. Parity is enforced by
# tests/test_note_link_attrs.py::test_js_and_python_agree_on_link_attrs
# — the two lists live in different languages and nothing else keeps
# them together.
_NOTE_LINK_ATTRS = ("paper", "author", "institution", "journal", "document")

# `data-open-highlight` is NOT in the list above on purpose. That list
# mirrors the MODES entries declaring `linkAttr` — one entry per
# navigable ENTITY — and a highlight is not one: it is a position
# inside a paper, and its link always carries `data-open-paper`
# alongside. Adding it there would break the MODES parity test and
# imply a Highlights tab that does not exist.
#
# It still has to be allowed through, though. A link the sanitizer
# strips survives until the next autosave and then vanishes, which is
# the worst shape of bug this file can produce — hence the parity test
# in tests/test_note_link_attrs.py covering this set too.
_NOTE_EXTRA_LINK_DATA_ATTRS = frozenset({"data-open-highlight"})

_NOTE_LINK_DATA_ATTRS = (frozenset(f"data-open-{t}" for t in _NOTE_LINK_ATTRS)
                         | _NOTE_EXTRA_LINK_DATA_ATTRS)

# Slugs and entity keys only ever contain these characters (see
# entities_api._author_key / _institution_key / _journal_key, and the
# canonical paper slug). Anything else in a data-open-* value is
# rejected rather than sanitised, because a partially-cleaned
# identifier would navigate somewhere unintended rather than fail.
_NOTE_LINK_VALUE_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")

_NOTE_ALLOWED_ATTRS = {
    "a":        frozenset({"href", "title", "class"}) | _NOTE_LINK_DATA_ATTRS,
    "span":     frozenset({"style"}),
    "table":    frozenset({"class", "style"}),
    "tr":       frozenset({"style"}),
    "td":       frozenset({"style", "colspan", "rowspan"}),
    "th":       frozenset({"style", "colspan", "rowspan"}),
    "col":      frozenset({"style"}),
    "colgroup": frozenset({"style"}),
    # `class="li-phantom"` marks the empty parent <li> the editor
    # creates when the user tabs the first item of a list (see
    # _indentListItem in src/notes.js). CSS hides that phantom's
    # marker. Any other class value gets stripped below.
    "li":       frozenset({"class"}),
}

# Class allow-list for <li>. Only "li-phantom" survives; anything else
# gets stripped. See `_indentListItem` in src/notes.js for the origin.
_NOTE_LI_ALLOWED_CLASSES    = frozenset({"li-phantom"})
# Class allow-list for <a>. Only the entity-link marker survives, which
# is what src/styles.css keys the link styling off. Without this the
# class is stripped on save and links render as plain text after a
# reload — visible only after a round-trip, so it is easy to miss.
_NOTE_A_ALLOWED_CLASSES     = frozenset({"note-entity-link"})

# Font-size on span accepts only integer-px values in this range —
# clamped both here and by the frontend input's min/max. Nothing else
# in the `style` attribute survives sanitisation, so an errant paste
# can't smuggle color/background/position hacks past this filter.
_NOTE_FONT_SIZE_MIN_PX = 1
_NOTE_FONT_SIZE_MAX_PX = 120
_NOTE_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(\d+)\s*px", re.IGNORECASE)

# Table sizing style properties. Only width/height/min-width in px or
# % survive; nothing else on the `style` attribute of table/tr/td/th/col.
_NOTE_TABLE_ALLOWED_CLASSES = frozenset({"note-table"})
_NOTE_TABLE_DIM_RE = re.compile(
    r"(width|height|min-width)\s*:\s*(\d+(?:\.\d+)?)(px|%)", re.IGNORECASE,
)
_NOTE_TABLE_MAX_PX = 4000   # sanity cap on any single dim
_NOTE_TABLE_MAX_PCT = 100.0


def _sanitize_table_style(v: str) -> str:
    """Extract only width/height/min-width in px or %, clamp values,
    reserialise. Everything else in the style attribute is dropped."""
    out = []
    seen = set()
    for m in _NOTE_TABLE_DIM_RE.finditer(v or ""):
        prop = m.group(1).lower()
        if prop in seen:
            continue
        seen.add(prop)
        num = float(m.group(2))
        unit = m.group(3)
        if unit == "px":
            num = max(1.0, min(float(_NOTE_TABLE_MAX_PX), num))
            out.append(f"{prop}: {int(round(num))}px")
        else:  # %
            num = max(1.0, min(_NOTE_TABLE_MAX_PCT, num))
            out.append(f"{prop}: {num:g}%")
    return "; ".join(out)


def _sanitize_note_html(html: str) -> str:
    """Strip anything not on the allow-list. Uses stdlib html.parser so
    we don't add a bs4/bleach dependency for what's ultimately a small,
    single-user editor. Not a full XSS scrubber — sufficient because
    the content originates from a contenteditable div under the user's
    own fingers and never crosses a real trust boundary."""
    class _Cleaner(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out: list[str] = []

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag not in _NOTE_ALLOWED_TAGS:
                return
            keep = _NOTE_ALLOWED_ATTRS.get(tag, frozenset())
            safe = []
            for k, v in attrs:
                k = (k or "").lower()
                if k not in keep or v is None:
                    continue
                # Reject javascript:/data: URLs on href to close the
                # obvious script-injection vector.
                if k == "href" and re.match(r"^\s*(javascript|data)\s*:", v, re.IGNORECASE):
                    continue
                # data-open-* carries a slug or entity key straight into
                # a navigation call. Anything outside the identifier
                # charset is dropped whole — see _NOTE_LINK_VALUE_RE.
                if k in _NOTE_LINK_DATA_ATTRS and not _NOTE_LINK_VALUE_RE.match(v):
                    continue
                # Filter <span style="..."> to just font-size:Npx with
                # N clamped into the allowed range. Everything else in
                # the style attribute gets dropped — no color, no
                # background, no positioning, no url() smuggling.
                if tag == "span" and k == "style":
                    m = _NOTE_FONT_SIZE_RE.search(v)
                    if not m:
                        continue
                    px = int(m.group(1))
                    if px < _NOTE_FONT_SIZE_MIN_PX: px = _NOTE_FONT_SIZE_MIN_PX
                    if px > _NOTE_FONT_SIZE_MAX_PX: px = _NOTE_FONT_SIZE_MAX_PX
                    v = f"font-size: {px}px"
                # Filter <table|tr|td|th|col> style attrs down to just
                # width/height/min-width in px or %. Everything else
                # dropped for the same defense-in-depth reason.
                if tag in ("table", "tr", "td", "th", "col", "colgroup") and k == "style":
                    v = _sanitize_table_style(v)
                    if not v:
                        continue
                # Table CSS class allow-list — the JS attaches
                # `.note-table` for consistent styling; anything else
                # gets dropped so pasted tables can't smuggle classes.
                if tag == "table" and k == "class":
                    kept = [c for c in v.split() if c in _NOTE_TABLE_ALLOWED_CLASSES]
                    if not kept:
                        continue
                    v = " ".join(kept)
                # Same treatment for <li class="li-phantom"> — the only
                # class the editor legitimately sets on an <li>.
                if tag == "li" and k == "class":
                    kept = [c for c in v.split() if c in _NOTE_LI_ALLOWED_CLASSES]
                    if not kept:
                        continue
                    v = " ".join(kept)
                # Same for <a class="note-entity-link">.
                if tag == "a" and k == "class":
                    kept = [c for c in v.split() if c in _NOTE_A_ALLOWED_CLASSES]
                    if not kept:
                        continue
                    v = " ".join(kept)
                # colspan/rowspan on td/th — integer, capped to 100.
                if tag in ("td", "th") and k in ("colspan", "rowspan"):
                    try:
                        n = max(1, min(100, int(v)))
                    except (TypeError, ValueError):
                        continue
                    v = str(n)
                safe.append((k, v))
            attr_str = "".join(f' {k}="{_htmllib.escape(v, quote=True)}"' for k, v in safe)
            self.out.append(f"<{tag}{attr_str}>")

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in _NOTE_ALLOWED_TAGS:
                self.out.append(f"</{tag}>")

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_data(self, data):
            self.out.append(_htmllib.escape(data))

    c = _Cleaner()
    c.feed(html or "")
    c.close()
    return "".join(c.out)


# ---------- Storage helpers -----------------------------------------

def _note_id() -> str:
    """Time-prefixed so `ls` shows notes in creation order (helpful
    for debugging). UUID suffix guarantees uniqueness across rapid
    taps."""
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _note_row(path: Path) -> dict:
    """Shape the sidebar list needs — id, title, updated_at, snippet.
    Snippet is the first ~120 chars of visible text stripped from the
    body HTML, for the sidebar's meta line."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    body = data.get("body_html") or ""
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "id":         data.get("id") or path.stem,
        "title":      (data.get("title") or "").strip() or "Untitled note",
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or data.get("created_at") or "",
        "snippet":    text[:120],
    }


# ---------- Endpoints -----------------------------------------------

@notes_bp.route("/api/notes", methods=["GET"])
def list_notes():
    require_corpus_or_abort()
    rows = []
    for p in notes_dir().glob("*.json"):
        row = _note_row(p)
        if row:
            rows.append(row)
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return jsonify(rows)


@notes_bp.route("/api/notes", methods=["POST"])
def create_note():
    require_corpus_or_abort()
    payload = request.get_json(silent=True) or {}
    nid = _note_id()
    now = _iso_now()
    data = {
        "id":         nid,
        "title":      (payload.get("title") or "").strip() or "Untitled note",
        "body_html":  _sanitize_note_html(payload.get("body_html") or ""),
        "created_at": now,
        "updated_at": now,
    }
    (notes_dir() / f"{nid}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("note_created id=%s title=%r", nid, data["title"])
    return jsonify(data)


@notes_bp.route("/api/note/<nid>", methods=["GET"])
def get_note(nid):
    require_corpus_or_abort()
    p = notes_dir() / f"{nid}.json"
    if not p.exists():
        abort(404, description="note_missing")
    return jsonify(json.loads(p.read_text(encoding="utf-8")))


@notes_bp.route("/api/note/<nid>", methods=["PUT"])
def update_note(nid):
    require_corpus_or_abort()
    p = notes_dir() / f"{nid}.json"
    if not p.exists():
        abort(404, description="note_missing")
    existing = json.loads(p.read_text(encoding="utf-8"))
    payload = request.get_json(silent=True) or {}
    # Stale-write guard. Jack, 2026-09-28: "when i am editing a note in the
    # popped out form, it doesnt save it." It did save — then the main
    # window, re-showing the note from its copy of 30 minutes earlier,
    # saved that copy over it (server.log: 11385 chars from the pop-out,
    # then 11374, the exact pre-pop-out length). A save now names the
    # revision it was edited from; if the note has moved on, refuse
    # rather than overwrite. `force` is the editor's explicit "keep mine".
    # A counter, not updated_at: that has one-second resolution, and two
    # windows can both save inside one second.
    current = int(existing.get("revision") or 0)
    base = payload.get("base_revision")
    if base is not None and not payload.get("force") and int(base) != current:
        logger.warning("note_update_refused_stale id=%s base=%s current=%d", nid, base, current)
        return jsonify({"error": "stale",
                        "description": "This note changed in another window since it was opened here.",
                        "current": existing}), 409
    if "title" in payload:
        existing["title"] = (payload["title"] or "").strip() or "Untitled note"
    if "body_html" in payload:
        existing["body_html"] = _sanitize_note_html(payload["body_html"] or "")
    existing["updated_at"] = _iso_now()
    existing["revision"] = current + 1
    p.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("note_updated id=%s title=%r body_len=%d rev=%d",
                nid, existing["title"], len(existing["body_html"]), existing["revision"])
    return jsonify(existing)


@notes_bp.route("/api/note/<nid>", methods=["DELETE"])
def delete_note(nid):
    require_corpus_or_abort()
    p = notes_dir() / f"{nid}.json"
    if not p.exists():
        abort(404, description="note_missing")
    p.unlink()
    logger.info("note_deleted id=%s", nid)
    return jsonify({"ok": True, "id": nid})
