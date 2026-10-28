"""The running server's address file.

The defect these cover: `launcher.py` binds an ephemeral port and, before
2026-09-21, recorded it nowhere. `/api/progress` reports exactly which of
six phases a long import is on, and was unreachable in practice because
nothing knew where to send the request — so every long job ended in
"press Scan and tell me what happened".
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from dev_only import server_address  # noqa: E402

_LAUNCHER = (Path(__file__).resolve().parents[1] / "launcher.py").read_text()


def test_write_records_url_port_and_pid(tmp_path):
    """Catches dropping the pid from the payload.

    Without it a reader cannot tell a live server from a crashed one,
    and `read()` has nothing to validate against."""
    p = server_address.write(54321, tmp_path / "server.json")
    data = json.loads(p.read_text())
    assert data["url"] == "http://127.0.0.1:54321"
    assert data["port"] == 54321
    assert data["pid"] == os.getpid()


def test_read_returns_none_for_a_dead_process(tmp_path):
    """Catches trusting the file without checking the pid.

    A crash or SIGKILL skips `clear()`. The stale file then points at a
    port nothing serves — or one the OS has since reassigned to an
    unrelated process, which is the dangerous case: the next reader
    would POST a scan request at a stranger.
    """
    f = tmp_path / "server.json"
    f.write_text(json.dumps({"url": "http://127.0.0.1:1", "port": 1,
                             "pid": 999999999, "started": "x"}))
    assert server_address.read(f) is None


def test_read_returns_the_address_while_the_process_lives(tmp_path):
    """Catches a staleness check so strict nothing is ever readable."""
    f = server_address.write(54321, tmp_path / "server.json")
    got = server_address.read(f)
    assert got and got["port"] == 54321


def test_read_and_write_never_raise_on_a_bad_path(tmp_path):
    """Catches letting a convenience file abort the launcher.

    `write()` runs during startup. An unwritable `~/.corpus` must not
    stop Corpus from opening."""
    bad = tmp_path / "nope" / "\0" / "server.json"
    server_address.write(1234, bad)          # must not raise
    assert server_address.read(bad) is None
    server_address.clear(bad)                # must not raise


def test_read_rejects_a_file_that_is_not_an_address(tmp_path):
    """Catches returning junk for a truncated or half-written file."""
    f = tmp_path / "server.json"
    f.write_text("[]")
    assert server_address.read(f) is None
    f.write_text("{}")
    assert server_address.read(f) is None


def test_clear_removes_the_file(tmp_path):
    """Catches leaving the address behind after a clean shutdown, which
    makes every later read depend on the pid check alone."""
    f = server_address.write(54321, tmp_path / "server.json")
    server_address.clear(f)
    assert not f.exists()


def test_launcher_guards_the_recorder_behind_is_dev():
    """Catches importing `dev_only` unconditionally.

    PyInstaller strips `python/dev_only/`, so an unguarded import is an
    ImportError on launch for every shipped user — the app would not
    start at all.
    """
    assert 'if not getattr(srv, "IS_DEV", False):' in _LAUNCHER
    assert "from dev_only import server_address" in _LAUNCHER


def test_launcher_clears_the_address_on_every_shutdown_path():
    """Catches clearing on one exit path only.

    `main()` returns from two places — the pywebview window closing and
    Ctrl-C in the browser-fallback path. A file left behind by the path
    nobody tested points at a dead port.
    """
    assert _LAUNCHER.count("_addr.clear()") == 2
    assert _LAUNCHER.count("ws.shutdown()") == 2
