"""Highlight + anchored-note round-trip through the papers API.

The v0.1.1 headline feature (PDF Note Mode) stores its notes as an
optional `note` field on each highlight, saved via
POST /api/paper/<slug>/highlights. Before these tests, only the
EXISTENCE of that route was asserted (tests/test_server_boot.py) —
nothing checked that a note survives a save/load cycle.
"""


def _hl(**over):
    """A minimally-valid highlight. `rects` must be non-empty or
    save_highlights drops the entry entirely."""
    h = {
        "id": "h1",
        "page": 3,
        "color": "#FFEB3B",
        "text": "encoding specificity",
        "rects": [{"x": 1.5, "y": 2.5, "width": 10.0, "height": 4.0}],
        "created_at": "2026-08-24T10:00:00Z",
    }
    h.update(over)
    return h


def test_highlight_round_trip_preserves_all_fields(client, corpus_dir):
    """Catches: a field being dropped or renamed in save_highlights'
    sanitization block. Every key the frontend sends for a plain
    highlight must come back byte-identical after a save/load cycle."""
    r = client.post("/api/paper/smith-2023/highlights",
                    json={"highlights": [_hl()]})
    assert r.status_code == 200
    assert r.get_json()["count"] == 1

    got = client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]
    assert len(got) == 1
    h = got[0]
    assert h["id"] == "h1"
    assert h["page"] == 3
    assert h["color"] == "#FFEB3B"
    assert h["text"] == "encoding specificity"
    assert h["created_at"] == "2026-08-24T10:00:00Z"
    assert h["rects"] == [{"x": 1.5, "y": 2.5, "width": 10.0, "height": 4.0}]


def test_anchored_note_survives_round_trip(client, corpus_dir):
    """Catches: `note` being dropped from the sanitization block.

    save_highlights rebuilds each entry field-by-field into a fresh
    dict, so any field not explicitly copied is silently discarded.
    If the `note` copy were removed, Note Mode would appear to work
    in-session (state is client-side) and lose every note on reload —
    a data-loss bug invisible to any test that only checks the route
    exists."""
    note = "Tulving's claim only holds when retrieval cues overlap encoding."
    client.post("/api/paper/smith-2023/highlights",
                json={"highlights": [_hl(note=note)]})
    got = client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]
    assert got[0]["note"] == note


def test_note_absent_vs_empty_stays_distinguishable(client, corpus_dir):
    """Catches: collapsing the note tri-state, e.g. "simplifying"
    the conditional copy to an unconditional
    `entry["note"] = str(h.get("note") or "")`.

    The three states are NOT interchangeable:
      * key absent  -> no note has ever been created on this highlight
      * ""          -> a note exists but is currently blank
      * "text"      -> a note with content
    The gutter uses absent-vs-present to decide whether to render a
    card at all, so collapsing absent into "" would spawn an empty
    card beside every highlight the user never annotated."""
    client.post("/api/paper/smith-2023/highlights", json={"highlights": [
        _hl(id="none"),                  # no note key at all
        _hl(id="blank", note=""),        # explicit empty note
        _hl(id="filled", note="real"),   # note with content
    ]})
    by_id = {h["id"]: h for h in
             client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]}

    assert "note" not in by_id["none"], "absent note must stay absent"
    assert by_id["blank"]["note"] == "", "empty note must stay an empty string"
    assert by_id["filled"]["note"] == "real"


def test_explicit_null_note_is_treated_as_absent(client, corpus_dir):
    """Catches: `note: null` leaking through as the string "None".

    The guard is `if "note" in h and h.get("note") is not None`. Drop
    the None check and `str(None)` writes the literal text "None" into
    the note, which then renders as a note card reading "None"."""
    client.post("/api/paper/smith-2023/highlights",
                json={"highlights": [_hl(note=None)]})
    got = client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]
    assert "note" not in got[0]


def test_long_note_is_not_truncated(client, corpus_dir):
    """Catches: someone adding a length cap to notes.

    Anchored notes have no length
    limit by specification (one note per highlight, unbounded). A cap added for
    "safety" would silently truncate a user's longest notes."""
    long_note = "x" * 50_000
    client.post("/api/paper/smith-2023/highlights",
                json={"highlights": [_hl(note=long_note)]})
    got = client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]
    assert len(got[0]["note"]) == 50_000


def test_highlight_without_rects_is_rejected(client, corpus_dir):
    """Catches: dropping the non-empty-rects guard.

    A highlight with no rectangles cannot be drawn or hit-tested, so
    it would become an invisible, unclickable, undeletable entry that
    still occupies a gutter slot. save_highlights drops these."""
    r = client.post("/api/paper/smith-2023/highlights",
                    json={"highlights": [_hl(rects=[]), _hl(id="ok")]})
    assert r.get_json()["count"] == 1
    got = client.get("/api/paper/smith-2023/highlights").get_json()["highlights"]
    assert [h["id"] for h in got] == ["ok"]


def test_non_list_highlights_payload_is_a_400(client, corpus_dir):
    """Catches: the isinstance guard being removed, which would turn a
    malformed payload into a 500 from iterating a non-list."""
    r = client.post("/api/paper/smith-2023/highlights",
                    json={"highlights": {"not": "a list"}})
    assert r.status_code == 400


def test_missing_highlights_file_returns_empty_not_404(client, corpus_dir):
    """Catches: get_highlights raising or 404-ing for a paper that has
    never been highlighted. The viewer calls this on every PDF open;
    a 404 there would surface as an error toast on every unannotated
    paper."""
    r = client.get("/api/paper/never-touched-2020/highlights")
    assert r.status_code == 200
    assert r.get_json() == {"highlights": []}
