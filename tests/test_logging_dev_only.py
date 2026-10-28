"""Logging must not touch shipped builds.

Requirement (2026-08-16): the entire `corpus.*` logger tree is
dev-only. In shipped builds it's fully disabled — no log file, no
event logs, no per-request access log — regardless of what code
calls `logger.info(...)`. Tests here verify both branches.
"""
from __future__ import annotations

import logging


def test_configure_logging_disables_tree_when_not_dev(monkeypatch, corpus_dir):
    """When IS_DEV is False (a shipped build), `_configure_logging`
    disables the entire corpus.* tree and adds NO handlers. Any
    logger.info/warning call is a no-op."""
    import server

    # Simulate a shipped build.
    monkeypatch.setattr(server, "IS_DEV", False)

    root = logging.getLogger("corpus")
    # Reset any prior state from other tests.
    root.disabled = False
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.NOTSET)

    server._configure_logging()

    assert root.disabled is True, "corpus.* tree must be disabled in ship mode"
    assert root.handlers == [], (
        f"no handlers should be attached in ship mode; got {root.handlers}"
    )
    assert root.level > logging.CRITICAL, (
        "level must be above CRITICAL so isEnabledFor(WARNING) returns False"
    )

    # Child loggers inherit the disabled state (Logger.disabled
    # short-circuits at the emitter).
    child = logging.getLogger("corpus.server")
    assert not child.isEnabledFor(logging.WARNING)
    assert not child.isEnabledFor(logging.INFO)


def test_configure_logging_enables_tree_in_dev(monkeypatch, corpus_dir):
    """When IS_DEV is True, a real handler chain is set up so log
    calls actually reach ~/.corpus/logs/server.log."""
    import server

    monkeypatch.setattr(server, "IS_DEV", True)

    root = logging.getLogger("corpus")
    root.disabled = False
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.NOTSET)

    server._configure_logging()

    assert root.disabled is False, "corpus.* tree must be live in dev mode"
    assert len(root.handlers) >= 1, "at least one handler (file or stderr) should attach"
    # INFO should now be enabled.
    assert logging.getLogger("corpus.server").isEnabledFor(logging.INFO)

    # Cleanup so we don't leak handlers into other tests.
    for h in list(root.handlers):
        root.removeHandler(h)


def test_access_hooks_not_registered_when_not_dev(client, corpus_dir):
    """Ship-mode Flask app must not have the before/after_request
    access-log hooks attached. Presence would imply per-request
    logger call attempts even if handlers were disabled."""
    import server

    # We can't easily monkeypatch IS_DEV RETROACTIVELY (the hooks
    # register at module import time). Instead, verify by function
    # name — if a `_access_log_finish` hook is registered, its
    # __name__ shows up in Flask's `after_request_funcs`.
    if server.IS_DEV:
        # Dev mode: hooks SHOULD be present. Verify.
        funcs = server.app.after_request_funcs.get(None, [])
        names = [f.__name__ for f in funcs]
        assert "_access_log_finish" in names, (
            "_access_log_finish must be registered in dev mode"
        )
    else:
        # Ship mode: hooks must NOT be present.
        funcs = server.app.after_request_funcs.get(None, [])
        names = [f.__name__ for f in funcs]
        assert "_access_log_finish" not in names, (
            "_access_log_finish must NOT be registered in ship mode"
        )
