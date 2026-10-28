"""Golden-file test for `render_frontmatter`.

Locks the byte-for-byte output for a rich fixture metadata dict so
any behavior change during the schema-table refactor (or any future
edit) is caught immediately. If this test fails after an intentional
change, regenerate the golden with:

    python -c "$(cat <<'PY'
    import sys, datetime
    sys.path.insert(0, 'python')
    sys.path.insert(0, 'python/extract')
    sys.path.insert(0, 'tests')
    _FROZEN = datetime.datetime(2026, 8, 16, 20, 0, 0)
    class _F(datetime.datetime):
        @classmethod
        def now(cls, tz=None): return _FROZEN if tz is None else _FROZEN.replace(tzinfo=tz)
    datetime.datetime = _F
    from _render_fixture import FIXTURE_SLUG, FIXTURE_META, FIXTURE_ADDED_AT
    from prefill_summary import render_frontmatter
    out = render_frontmatter(FIXTURE_SLUG, FIXTURE_META, added_at=FIXTURE_ADDED_AT)
    open('tests/fixtures/render_frontmatter_golden.md', 'w').write(out)
    PY
    )"

The fixture at `tests/_render_fixture.py` intentionally sets every
emission-kind: scalars, lists (inline + quoted), block scalars
(tldr/abstract/bibtex/retraction_notice), JSON-block scalars
(oa_authors/topics/etc), custom shapes (authors_detailed/funder/
license/ss_only_refs/s2_fields_of_study/update_to/_ss_authors_raw),
integer-only fields, boolean fields, float fields (fwci), embedding
list, and provenance.
"""
from __future__ import annotations

import datetime
from pathlib import Path


_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "render_frontmatter_golden.md"


def _freeze_datetime(monkeypatch, iso: str = "2026-08-16T20:00:00") -> None:
    """Freeze datetime.datetime.now() to a fixed instant so the
    render output is stable across test runs. Restores automatically
    at test teardown."""
    frozen = datetime.datetime.fromisoformat(iso)

    class _F(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is None else frozen.replace(tzinfo=tz)

    monkeypatch.setattr(datetime, "datetime", _F)


def test_render_frontmatter_byte_for_byte(monkeypatch, corpus_dir):
    """render_frontmatter must produce output byte-identical to the
    committed golden file. A single-character drift fails the test."""
    _freeze_datetime(monkeypatch)
    from _render_fixture import FIXTURE_SLUG, FIXTURE_META, FIXTURE_ADDED_AT
    from prefill_summary import render_frontmatter

    got = render_frontmatter(FIXTURE_SLUG, FIXTURE_META, added_at=FIXTURE_ADDED_AT)
    want = _GOLDEN.read_text(encoding="utf-8")

    if got != want:
        # Emit a diff-friendly failure. Truncate to the first divergent
        # line so long outputs don't drown the output.
        got_lines  = got.splitlines()
        want_lines = want.splitlines()
        first_diff = next(
            (i for i, (a, b) in enumerate(zip(got_lines, want_lines)) if a != b),
            min(len(got_lines), len(want_lines)),
        )
        raise AssertionError(
            f"render_frontmatter output diverged at line {first_diff + 1}\n"
            f"  expected: {want_lines[first_diff] if first_diff < len(want_lines) else '<EOF>'!r}\n"
            f"  got:      {got_lines[first_diff]  if first_diff < len(got_lines)  else '<EOF>'!r}\n"
            f"(total: expected {len(want_lines)} lines, got {len(got_lines)})"
        )
