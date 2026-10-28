"""Reading, cleaning and writing a PDF's highlights — for papers AND
documents.

Split out of papers_api.py on 2026-09-25 when the Documents tab arrived
(Jack: "just want to be able to upload this chapter and take notes on
it"). A document's highlights and anchored notes are the same data as a
paper's, drawn by the same viewer, so they must be validated by the same
rules; two copies of the sanitizer would drift, and the viewer would then
save fields one endpoint keeps and the other drops.

The caller decides WHERE a list lives; this module only knows the shape.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_highlights(path: Path) -> dict:
    """`{"highlights": [...]}` from `path`, or an empty list when the file
    is missing or unreadable — a corrupt file must not stop the PDF from
    opening."""
    if not path.exists():
        return {"highlights": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"highlights": []}
    except Exception:
        return {"highlights": []}


def clean_highlights(hls: list) -> list[dict]:
    """Drop empty entries and coerce every field's type.

    The viewer is the source of truth during a session and POSTs its whole
    list after each change; this is the only check between it and disk."""
    clean: list[dict] = []
    for h in hls:
        if not isinstance(h, dict):
            continue
        rects = h.get("rects") or []
        if not isinstance(rects, list) or not rects:
            continue
        entry = {
            "id":         str(h.get("id") or "").strip() or f"h_{len(clean)}",
            "page":       int(h.get("page") or 1),
            "color":      str(h.get("color") or "#FFEB3B").strip(),
            "text":       str(h.get("text") or "").strip(),
            "rects":      [{"x": float(r.get("x", 0)),
                            "y": float(r.get("y", 0)),
                            "width":  float(r.get("width", 0)),
                            "height": float(r.get("height", 0))}
                           for r in rects if isinstance(r, dict)],
            "created_at": str(h.get("created_at") or "").strip(),
        }
        # Optional anchored note. `note: null / missing` = no note yet
        # (right-click "Create note" hasn't been used on this highlight).
        # Empty string = note exists but is currently blank. No length
        # cap (Jack's spec), but coerced to string to keep JSON well-typed.
        if "note" in h and h.get("note") is not None:
            entry["note"] = str(h.get("note") or "")
        clean.append(entry)
    return clean


def save_highlights(path: Path, clean: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"highlights": clean}, indent=2, ensure_ascii=False),
                    encoding="utf-8")
