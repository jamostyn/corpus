"""List filtering — one definition of "what makes a row findable".

Bug, 2026-09-14: "should be able to search by author here as well."
Filed against the Projects tab's "Add papers…" picker. Typing an
author name matched nothing, because that picker filtered the rendered
LABEL, and a paper's label is "Title (year)" — the author is not in it.

The same defect was live in the notes entity-link picker. Meanwhile
each of the four sidebars had its own richer multi-field filter. Six
copies of the same idea, two of them wrong.

Now every list filters through `modeRowMatches(mode, row, q)` and each
MODES entry declares `searchFields`. These tests EXECUTE the real
declarations: `modeRowMatches` and the `searchFields` arrows are pure,
so they are extracted from app.js and run in node rather than asserted
against as text. app.js as a whole cannot load in the vm harness (it
needs a live DOM).
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


def _matcher_src() -> str:
    """The real `modeRowMatches`, by brace matching.

    Raises rather than returning "" if it is gone — a silent empty
    string would make every assertion below vacuously pass."""
    src = _app()
    start = src.index("function modeRowMatches(")
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces in modeRowMatches")


def _search_fields() -> dict[str, str]:
    """mode id -> the literal `searchFields` arrow source.

    Scans each MODES entry from its `{ id: "` marker to the next, the
    way the other MODES tests do (brace matching is not viable — the
    entries contain arrow functions and template literals)."""
    src = _app()
    block = src[src.index("const MODES = ["):src.index("\nconst MODES_BY_ID")]
    out = {}
    for part in re.split(r'(?=\{ id: ")', block):
        if not part.strip().startswith('{ id: "'):
            continue
        mid = re.search(r'\{ id: "([a-z]+)"', part).group(1)
        fn = re.search(r"searchFields:\s*(\(r\) => \[[^\]]*\])", part)
        if fn:
            out[mid] = fn.group(1)
    return out


def _search_hints() -> dict[str, str]:
    src = _app()
    block = src[src.index("const MODES = ["):src.index("\nconst MODES_BY_ID")]
    out = {}
    for part in re.split(r'(?=\{ id: ")', block):
        if not part.strip().startswith('{ id: "'):
            continue
        mid = re.search(r'\{ id: "([a-z]+)"', part).group(1)
        h = re.search(r'searchHint:\s*"([^"]*)"', part)
        if h:
            out[mid] = h.group(1)
    return out


def _match(mode_id: str, row: dict, q: str) -> bool:
    """Run the REAL matcher against the REAL searchFields for a mode.

    `countries.js` is loaded first because the institutions
    `searchFields` calls `Countries.name(...)` — a searchable value the
    row does not itself contain. Loading the real module rather than
    stubbing it means the test covers the actual code path a user's
    keystroke takes."""
    fields = _search_fields()
    assert mode_id in fields, f"mode {mode_id!r} declares no searchFields"
    countries = (_SRC / "countries.js").read_text(encoding="utf-8")
    script = f"""
const window = globalThis;
{countries}
const Countries = window.Countries;
{_matcher_src()}
const mode = {{ id: {json.dumps(mode_id)}, searchFields: {fields[mode_id]} }};
console.log(JSON.stringify(modeRowMatches(mode, {json.dumps(row)}, {json.dumps(q)})));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


_PAPER = {"slug": "schunn-2001", "author": "Schunn, C.", "year": 2001,
          "title": "Another source of individual differences"}


# ---------- the reported bug ------------------------------------------

def test_a_paper_is_findable_by_its_author():
    """Catches: dropping author from the paper search fields.

    This was the reported bug. The author is not in the rendered label, so
    any filter that reads the label alone fails here while every
    title-based test still passes."""
    assert _match("papers", _PAPER, "schunn") is True


def test_a_paper_is_still_findable_by_title_and_year():
    """Catches: replacing the field list rather than extending it.

    Title and year search already worked in the sidebar; a fix that
    swapped author in for one of them would trade one complaint for
    another."""
    assert _match("papers", _PAPER, "individual differences") is True
    assert _match("papers", _PAPER, "2001") is True


def test_year_matches_even_though_it_is_a_number():
    """Catches: dropping the String() coercion in the matcher.

    `year` arrives from the API as a JSON number. `.toLowerCase()` on a
    number throws, which would take out the whole filter — every
    keystroke erroring instead of just missing the year."""
    assert _match("papers", {"author": "X", "year": 2001, "title": "T"}, "200") is True


def test_a_missing_field_does_not_throw():
    """Catches: assuming every field is present.

    Papers without a resolved author carry `author: undefined` in the
    list payload. A null-unsafe matcher would throw on the first
    keystroke for the whole corpus."""
    assert _match("papers", {"title": "Only a title"}, "only") is True
    assert _match("papers", {"title": "Only a title"}, "zzz") is False


# ---------- semantics that must NOT change ----------------------------

def test_fields_are_matched_separately_not_as_one_joined_string():
    """Catches: `searchFields(row).join(" ").includes(q)`.

    Joining is the obvious shortcut and it silently WIDENS every filter
    in the app: a query could straddle a field boundary and match text
    that appears nowhere in the data. Here "c. 2001" spans the end of
    the author and the start of the year — it must not match, because
    the sidebars never behaved that way."""
    assert _match("papers", _PAPER, "c. 2001") is False


def test_an_empty_query_matches_everything():
    """Catches: an empty filter box hiding every row.

    Clearing the box must restore the full list; an unguarded
    `.includes("")` happens to work, but a length check or a regex
    build could easily not."""
    assert _match("papers", _PAPER, "") is True


def test_search_is_case_insensitive():
    """Catches: lowercasing the query but not the field (or neither).

    Titles are title-cased and authors are capitalised, so a
    case-sensitive filter matches almost nothing the user types."""
    assert _match("papers", _PAPER, "SCHUNN") is True


# ---------- the other modes -------------------------------------------

def test_authors_are_findable_by_given_name_and_institution():
    """Catches: narrowing the authors filter during the consolidation.

    The sidebar searched family, given AND primary_institution before
    this change. Rewriting it to go through the shared matcher must
    preserve all three, and only a test on the non-obvious two
    (given name, institution) would notice."""
    row = {"family": "Reber", "given": "Paul", "primary_institution": "Northwestern"}
    assert _match("authors", row, "paul") is True
    assert _match("authors", row, "northwestern") is True


def test_journals_are_findable_by_issn_and_publisher():
    """Catches: the same narrowing on journals, whose field list is the
    longest (name, host_organization, venue_type, issn) and so the
    easiest to trim by accident."""
    row = {"name": "Journal of Intelligence", "host_organization": "MDPI",
           "venue_type": "journal", "issn": "2079-3200"}
    assert _match("journals", row, "mdpi") is True
    assert _match("journals", row, "2079") is True


def test_institutions_are_findable_by_country():
    """Catches: narrowing institutions to name-only."""
    row = {"name": "Northwestern University", "country_code": "US", "type": "education"}
    assert _match("institutions", row, "us") is True


def test_institutions_are_findable_by_the_country_name_that_is_displayed():
    """Catches: showing the country NAME but searching only the CODE.

    From 2026-09-17 the institutions list renders "Netherlands", not
    "NL". A filter that still matched only the raw code would be the
    exact defect fixed three days earlier in the Add-papers picker:
    text visible on screen that the search box cannot find. The row
    itself has no "Netherlands" in it — the searchable value is derived
    by `Countries.name`."""
    row = {"name": "Delft University of Technology",
           "country_code": "NL", "type": "education"}
    assert _match("institutions", row, "netherlands") is True
    assert _match("institutions", row, "Netherlands") is True
    # …and the raw code must keep working for anyone who types it.
    assert _match("institutions", row, "nl") is True


def test_notes_are_findable_by_their_snippet():
    """Catches: notes searching title only.

    The notes sidebar searched title AND snippet (the body preview)
    before the consolidation. Losing the snippet makes note search much
    weaker without any visible error."""
    assert _match("notes", {"title": "Reading", "snippet": "interleaving helps"},
                  "interleaving") is True


# ---------- the wiring ------------------------------------------------

def test_every_mode_that_declares_search_fields_also_declares_a_hint():
    """Catches: adding searchFields without searchHint.

    The hint is what the filter placeholder promises the user. A mode
    with fields but no hint silently falls back to the generic
    "Filter <things>…" — which is exactly the uninformative label that
    produced this bug report."""
    fields, hints = _search_fields(), _search_hints()
    missing = sorted(set(fields) - set(hints))
    assert not missing, f"modes with searchFields but no searchHint: {missing}"


def test_the_papers_hint_actually_promises_author_search():
    """Catches: fixing the behaviour but leaving the placeholder
    saying something else — or vice versa.

    The hint and the field list sit next to each other in the MODES
    entry precisely so they stay true to one another; this asserts it
    for the field this bug was about."""
    assert "author" in _search_hints()["papers"].lower()
    assert "r.author" in _search_fields()["papers"]


def test_both_pickers_filter_through_the_shared_matcher():
    """Catches: a picker going back to filtering its rendered label.

    That is the original defect. Both pickers must filter the ROW, so
    fields the label does not display (a paper's author) still match."""
    for name in ("projects.js", "notes.js"):
        src = (_SRC / name).read_text(encoding="utf-8")
        body = "\n".join(re.sub(r"//.*$", "", ln) for ln in src.split("\n"))
        assert "modeRowMatches(" in body, f"{name} does not use the shared matcher"
        assert ".label.toLowerCase().includes(" not in body, (
            f"{name} still filters on the rendered label")


def test_no_sidebar_keeps_its_own_inline_filter():
    """Catches: one sidebar being left behind in the consolidation.

    A leftover inline `state.X.filter(...)` chain would keep working,
    so nothing would break — it would just quietly stop tracking the
    mode's declared fields when those change."""
    src = "\n".join(re.sub(r"//.*$", "", ln) for ln in _app().split("\n"))
    for state_key in ("papers", "authors", "institutions", "journals"):
        m = re.search(r"state\." + state_key + r"\.filter\(([^)]*)\)", src)
        assert m, f"no filter call found for state.{state_key}"
        assert "modeRowMatches" in m.group(1), (
            f"state.{state_key} still filters inline instead of via the "
            f"shared matcher: {m.group(1)[:60]}")


def test_missing_fields_do_not_match_the_words_null_or_undefined():
    """Catches: dropping the `v != null` guard in the matcher.

    The guard looks like crash protection, but `String(null)` does not
    throw — it returns the literal "null". Without the guard, every row
    with a missing field carries invisible searchable text, so typing
    "nu" (the start of "Nature", "neuro", "number"…) matches every
    paper whose author failed to resolve. The false positives look like
    the filter is simply broken.

    This mutation survived the first pass of this file: the existing
    missing-field test asserted only that nothing THREW."""
    row = {"author": None, "year": None, "title": "Zebra"}
    assert _match("papers", row, "nu") is False
    assert _match("papers", row, "null") is False
    assert _match("papers", {"title": "Zebra"}, "undefined") is False
    # …and the field that IS present still matches.
    assert _match("papers", row, "zebra") is True


def test_every_filter_box_shares_one_style_rule():
    """Catches: a filter input styled ad-hoc instead of with the rest.

    The two modal pickers' filter boxes originally declared only width
    and margin, missing the `padding` and `font: inherit` the sidebar
    boxes get. The result is a placeholder in the browser's default
    search font pressed against the border — legible enough to ship and
    wrong enough to notice, which is how it survived until a
    screenshot showed it clipped."""
    css = (_SRC / "styles.css").read_text(encoding="utf-8")
    m = re.search(r"((?:^\.[a-z-]+(?: input)?,\n)*^\.[a-z-]+(?: input)?) \{\n"
                  r"  width: 100%;\n  padding: 5px 8px;", css, re.M)
    assert m, "the shared filter-input rule is gone or was reshaped"
    selector = m.group(1)
    for cls in (".sidebar-header input", ".pj-picker-filter", ".note-link-filter"):
        assert cls in selector, f"{cls} no longer shares the filter-input styling"
