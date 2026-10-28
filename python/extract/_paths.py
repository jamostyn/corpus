"""Corpus path resolver.

Every extraction script imports paths from here rather than computing
them from __file__. Two ways to set the corpus root:

    # 1. Env var (used by CLI + typical dev)
    CORPUS_DIR=~/mycorpus python3 rename_pdfs.py

    # 2. Programmatic (used by the desktop shell / HTTP server)
    from _paths import set_corpus_root
    set_corpus_root("/path/to/user/corpus")

A corpus directory has this shape:

    <corpus>/
        papers/       ← user's PDFs
        summaries/    ← extracted MDs written here
        inbox/        ← optional drop zone; rename_pdfs moves confidently
                        identified PDFs from here into papers/
"""
from __future__ import annotations

import os
from pathlib import Path

_CORPUS_ROOT: Path | None = None


def set_corpus_root(path: str | Path) -> None:
    """Explicitly set the corpus root. Overrides any env var."""
    global _CORPUS_ROOT
    _CORPUS_ROOT = Path(path).expanduser().resolve()


def _resolve_from_env() -> Path | None:
    val = os.environ.get("CORPUS_DIR")
    if not val:
        return None
    return Path(val).expanduser().resolve()


def corpus_root() -> Path:
    """Return the corpus root, resolving env if not explicitly set."""
    global _CORPUS_ROOT
    if _CORPUS_ROOT is None:
        env = _resolve_from_env()
        if env is None:
            raise RuntimeError(
                "Corpus root not set. Either pass CORPUS_DIR env var or "
                "call _paths.set_corpus_root(<path>)."
            )
        _CORPUS_ROOT = env
    return _CORPUS_ROOT


def papers_dir() -> Path:
    return corpus_root() / "papers"


def summaries_dir() -> Path:
    return corpus_root() / "summaries"


def inbox_dir() -> Path:
    return corpus_root() / "inbox"


def highlights_dir() -> Path:
    """Sidecar dir for per-paper highlight annotations. Kept OUT of
    summaries/ so re-extracting a paper (which overwrites the .md)
    doesn't wipe user-drawn highlights."""
    d = corpus_root() / "highlights"
    d.mkdir(exist_ok=True)
    return d


def pdf_refs_dir() -> Path:
    """Cache of references read out of each PDF's own text.

    Pure derived data — safe to delete at any time; it is rebuilt from
    the PDF on next view. Kept OUT of summaries/ for the same reason
    highlights are: a re-extract overwrites the .md, and this must
    survive that. Also keeps PDF-read references visibly separate from
    the API-deposited ones stored in the summary."""
    d = corpus_root() / "pdf_refs"
    d.mkdir(exist_ok=True)
    return d


def notes_dir() -> Path:
    """User-authored notes — free-form rich-text scratchpad. Independent
    of papers/summaries so re-extracts don't touch them."""
    d = corpus_root() / "notes"
    d.mkdir(exist_ok=True)
    return d


def projects_dir() -> Path:
    """User-authored project folders — organizational overlay only.

    A project stores the IDs of the papers and notes it contains; the
    papers and notes themselves never move, and one can belong to any
    number of projects.

    Kept OUT of summaries/ for the same reason highlights and notes
    are: `prefill_summary.render_frontmatter` emits a FIXED field list,
    so a re-extract rewrites the .md and drops anything it doesn't know
    about. A `projects:` key in the frontmatter would be silently
    destroyed the next time the user hit Re-extract. Verified by
    tests/test_projects.py::test_membership_survives_a_summary_rewrite."""
    d = corpus_root() / "projects"
    d.mkdir(exist_ok=True)
    return d


# Files that mark the Corpus SOURCE TREE. Both must be present in the
# same directory — either alone is too generic.
_SOURCE_TREE_MARKERS = ("launcher.py", "pyinstaller_corpus.spec")


def is_corpus_source_tree(path: str | Path) -> bool:
    """Is `path` the Corpus dev repo, or somewhere inside it?

    A corpus directory is user data. The source tree is not, and
    scaffolding `papers/ summaries/ inbox/` into it drops empty
    directories into the repo where git cannot see them — git does not
    track empty directories, so `git status` stays clean and nothing
    reports the mistake. The app meanwhile shows an empty corpus.

    This has happened twice. On 2026-09-09 `corpus_dir` pointed at a
    Paper Machine folder of 4288 unrelated files; on 2026-09-17 it
    pointed at `corpus/dev` itself, and three empty directories sat in
    the repo until someone looked for them. The first fix only made the
    symptom legible (the empty state now names the configured path) —
    it never stopped the scaffolding, which is why there was a second
    time.

    Ancestors are checked too, so `corpus/dev/anything` is caught, not
    just the root. Deliberately narrow: it does NOT reject any git
    repo, because keeping a corpus under version control is a
    reasonable thing for a researcher to do."""
    try:
        p = Path(path).expanduser().resolve()
    except Exception:
        return False
    for candidate in (p, *p.parents):
        if all((candidate / m).is_file() for m in _SOURCE_TREE_MARKERS):
            return True
    return False


def bridges_dir() -> Path:
    """Computed citation bridges — indirect connections between corpus
    papers, discovered via OpenAlex.

    Expensive to compute (~70 network requests for the whole corpus) and
    derived from data that lives outside the corpus, so it is cached
    rather than recomputed per request.

    Kept OUT of summaries/ for the reason every sidecar here is:
    `prefill_summary.render_frontmatter` emits a fixed field list, so a
    re-extract rewrites the .md and silently drops anything it does not
    know about."""
    d = corpus_root() / "bridges"
    d.mkdir(exist_ok=True)
    return d


def citers_dir() -> Path:
    """Every known citer of each paper, fetched from OpenAlex on demand.

    One file per paper (`<slug>.json`). Sized 2026-09-22: the most-cited
    paper in Jack's corpus (PRISMA 2020) has ~105k citers; DOIs alone are
    ~3 MB and the stored rows carry titles too.

    A sidecar, never frontmatter, for two reasons: re-extract drops
    frontmatter keys it does not know, and anything in a summary lengthens
    every cold `/api/papers` read — already the slow path on an
    iCloud-synced corpus. Slug-keyed, so `slug_migration` moves it."""
    d = corpus_root() / "citers"
    d.mkdir(exist_ok=True)
    return d


def documents_dir() -> Path:
    """Documents that are not papers — a book chapter, for now.

    One folder per document: `<id>/document.pdf`, `meta.json`,
    `highlights.json`. Deliberately NOT under papers/ or summaries/:
    everything there is swept by Scan's backfill, the citation index,
    citers and the bridge search, and a document gets none of that
    (Jack, 2026-09-25: "none of the api stuff"). A folder per document
    keeps each one self-contained, so removing one later is one delete.
    Not created by `ensure_corpus_layout` — it appears on first upload."""
    d = corpus_root() / "documents"
    d.mkdir(exist_ok=True)
    return d


def ensure_corpus_layout() -> None:
    """Create `papers/`, `summaries/` and `inbox/` under the corpus root.

    Idempotent, and UNCONDITIONAL — it does not check whether the root
    is empty first. An earlier version of this docstring claimed it
    did, which mattered on 2026-09-09: the corpus dir was pointed at a
    folder of 4288 unrelated files and this quietly scattered three
    empty directories into it, while the app showed nothing and said
    nothing.

    The scaffolding itself is kept (pointing at a fresh folder and
    having it work is the common case). What changed is that the UI now
    names the corpus path when a corpus is set but holds no papers, so
    a mis-pointed folder is visible instead of looking like an empty
    one — see `showEmptyState("empty-corpus")` in src/app.js."""
    root = corpus_root()
    if is_corpus_source_tree(root):
        # Belt and braces with the check in config_api.set_config: a
        # config saved BEFORE that guard existed is still on disk, and
        # boot would otherwise scaffold from it.
        raise RuntimeError(
            f"refusing to scaffold a corpus into the Corpus source tree: {root}")
    for sub in ("papers", "summaries", "inbox"):
        (root / sub).mkdir(parents=True, exist_ok=True)
