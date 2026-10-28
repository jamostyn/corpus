"""The corpus directory cannot be pointed at Corpus's own source tree.

This has happened twice.

  * 2026-09-09 — `corpus_dir` pointed at a Paper Machine folder of 4288
    unrelated files. The app showed nothing and said nothing.
  * 2026-09-17 — `corpus_dir` pointed at `corpus/dev` itself. Three
    empty directories (`papers/`, `summaries/`, `inbox/`) sat inside
    the repo until someone went looking.

The second one is the nastier shape: git does not track empty
directories, so `git status` stays clean and the pollution is invisible
to every normal check. The 2026-09-09 fix only made the symptom legible
— the empty state now names the configured path — which is why there
was a 2026-09-17.

Two independent guards, because they fail at different moments:
`config_api.set_config` refuses when the user PICKS the folder, and
`_paths.ensure_corpus_layout` refuses to scaffold even from a config
saved before the first guard existed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_DEV_ROOT = Path(__file__).resolve().parent.parent


# ---------- The predicate ---------------------------------------------

def test_the_real_dev_tree_is_recognised():
    """Catches: marker filenames drifting away from what is on disk.

    The predicate looks for `launcher.py` + `pyinstaller_corpus.spec`.
    Rename or move either and the guard silently stops guarding — it
    would return False for everything and no test that only checks
    rejection of fake trees would notice."""
    from _paths import is_corpus_source_tree
    assert is_corpus_source_tree(_DEV_ROOT) is True, (
        "the guard no longer recognises Corpus's own source tree — did "
        "launcher.py or pyinstaller_corpus.spec move?")


def test_a_subdirectory_of_the_source_tree_is_recognised():
    """Catches: checking only the given path and not its ancestors.

    `corpus/dev/papers` is just as wrong a corpus root as `corpus/dev`,
    and is the likelier misclick in a folder picker that starts inside
    the repo."""
    from _paths import is_corpus_source_tree
    assert is_corpus_source_tree(_DEV_ROOT / "src") is True


def test_an_ordinary_corpus_directory_is_allowed(tmp_path):
    """Catches: a guard so broad it blocks real corpora.

    A false positive here is worse than the bug — it would stop the
    user configuring the app at all."""
    from _paths import is_corpus_source_tree
    (tmp_path / "papers").mkdir()
    assert is_corpus_source_tree(tmp_path) is False


def test_a_git_repository_is_not_rejected_merely_for_being_one(tmp_path):
    """Catches: widening the check to "any git repo".

    Keeping a corpus under version control is a reasonable thing for a
    researcher to do, and Jack's own corpora sit inside a git tree.
    Only the Corpus SOURCE markers may trigger the guard."""
    from _paths import is_corpus_source_tree
    (tmp_path / ".git").mkdir()
    assert is_corpus_source_tree(tmp_path) is False


def test_one_marker_alone_is_not_enough(tmp_path):
    """Catches: relaxing the check to match either marker.

    `launcher.py` is a plausible filename in a user's own folder.
    Requiring both markers together is what keeps the guard specific."""
    from _paths import is_corpus_source_tree
    (tmp_path / "launcher.py").write_text("", encoding="utf-8")
    assert is_corpus_source_tree(tmp_path) is False


def test_a_nonexistent_path_does_not_raise(tmp_path):
    """Catches: the predicate throwing on a path that isn't there.

    It runs inside `set_config`, which must be able to reject a typo'd
    path with a 400 rather than a 500."""
    from _paths import is_corpus_source_tree
    assert is_corpus_source_tree(tmp_path / "nope" / "deeper") is False


# ---------- Guard 1: the config endpoint ------------------------------

def test_setting_corpus_dir_to_the_source_tree_is_refused(client, corpus_dir):
    """Catches: removing the check from set_config.

    Without it the path is saved, `_apply_env` scaffolds into the repo,
    and the only feedback is an app that looks empty."""
    r = client.post("/api/config", json={"corpus_dir": str(_DEV_ROOT)})
    assert r.status_code == 400
    assert r.get_json()["error"] == "corpus_dir_is_source_tree"


def test_no_test_can_write_the_real_user_config():
    """Catches: the autouse `scratch_config` fixture being removed.

    This test file POSTs real paths to /api/config. Without the
    redirect that is harmless only while the guard works — and on
    2026-09-17, mutating the guard away made the POST succeed and
    overwrite Jack's actual `~/.corpus/config.json`. A test suite must
    not be able to damage the user's configuration when the code under
    test is broken, because broken code is exactly when it runs."""
    import config_api
    real = Path.home() / ".corpus" / "config.json"
    assert config_api.CONFIG_PATH != real, (
        "config_api.CONFIG_PATH points at the real user config during "
        "tests — the scratch_config fixture is not active")


def test_a_refused_path_is_not_written_to_the_config_file(client, corpus_dir,
                                                          scratch_config):
    """Catches: rejecting the request but saving the value anyway.

    A 400 that still persisted the path would be the worst of both:
    the user sees an error and the broken config is live on next boot."""
    scratch_config.write_text(json.dumps({"corpus_dir": "/somewhere/good"}),
                              encoding="utf-8")
    client.post("/api/config", json={"corpus_dir": str(_DEV_ROOT)})
    assert json.loads(scratch_config.read_text())["corpus_dir"] == "/somewhere/good", (
        "the rejected path was written to config.json anyway")


def test_an_ordinary_directory_is_still_accepted(client, corpus_dir,
                                                 scratch_config, tmp_path):
    """Catches: the guard rejecting everything.

    The happy path has to keep working, and a guard that 400s on valid
    input would be caught only here."""
    scratch_config.write_text("{}", encoding="utf-8")
    good = tmp_path / "MyCorpus"
    good.mkdir()
    r = client.post("/api/config", json={"corpus_dir": str(good)})
    assert r.status_code == 200
    assert json.loads(scratch_config.read_text())["corpus_dir"] == str(good.resolve())


# ---------- Guard 2: the scaffolder -----------------------------------

def test_scaffolding_into_the_source_tree_raises(tmp_path):
    """Catches: relying on set_config alone.

    A `corpus_dir` saved before the endpoint guard existed is still on
    disk. Boot reads it and calls ensure_corpus_layout directly, so the
    scaffolder needs its own refusal or the old bad config still
    pollutes.

    Runs against a FAKE source tree in tmp_path, not the real repo. An
    earlier version pointed at `_DEV_ROOT`, and when the guard was
    mutated away to check this test's own value, the test did exactly
    what it was written to prevent: it scaffolded three directories
    into the repo. A test for a destructive behaviour must not be
    destructive when the guard it tests is absent."""
    import _paths
    fake = tmp_path / "fake_source_tree"
    fake.mkdir()
    for marker in ("launcher.py", "pyinstaller_corpus.spec"):
        (fake / marker).write_text("", encoding="utf-8")
    assert _paths.is_corpus_source_tree(fake) is True

    original = _paths._CORPUS_ROOT
    try:
        _paths.set_corpus_root(fake)
        with pytest.raises(RuntimeError, match="source tree"):
            _paths.ensure_corpus_layout()
        assert not (fake / "papers").exists(), (
            "ensure_corpus_layout scaffolded before raising")
    finally:
        _paths._CORPUS_ROOT = original


def test_scaffolding_a_normal_directory_still_works(tmp_path):
    """Catches: the scaffolder guard firing on valid roots.

    First-run setup depends on this creating the three directories."""
    import _paths
    original = _paths._CORPUS_ROOT
    try:
        _paths.set_corpus_root(tmp_path)
        _paths.ensure_corpus_layout()
        for sub in ("papers", "summaries", "inbox"):
            assert (tmp_path / sub).is_dir()
    finally:
        _paths._CORPUS_ROOT = original


def test_the_repo_has_no_scaffolded_corpus_directories():
    """Catches: the pollution itself, recurring.

    `papers/`, `summaries/` and `inbox/` are not part of the dev tree.
    They appear only when corpus_dir has been aimed at the repo. git
    cannot catch this — empty directories are untracked, so the working
    tree reads as clean — which is exactly why it needs a test."""
    strays = [d for d in ("papers", "summaries", "inbox", "notes",
                          "highlights", "pdf_refs", "projects")
              if (_DEV_ROOT / d).exists()]
    assert not strays, (
        f"corpus directories scaffolded into the repo: {strays}. "
        "corpus_dir has been pointed at the source tree.")
