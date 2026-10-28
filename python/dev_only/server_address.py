"""Record where the running Corpus server is listening.

WHY THIS EXISTS
---------------
Jack, 2026-09-21: "what are we waiting on? you keep getting stuck like
this. fix whatever you need to for this not to happen."

He was right, and the cause was concrete. `launcher.py` binds an
EPHEMERAL port — a different one every launch — and that number was
written down nowhere. Not in `~/.corpus/`, not in `server.log`, not on
stdout unless the pywebview path fails. So anything outside the app
window was blind: `/api/progress` exists and reports exactly which of
six phases an import is on, and it could not be reached because its
address was unknown. Every long job therefore ended with "press Scan
and tell me what happened" instead of a two-second check.

On the session that prompted this, the port was eventually found with
`lsof -nP -p <pid>`. That is a lucky guess, not a method.

DEV ONLY
--------
This lives under `python/dev_only/` deliberately: PyInstaller strips
that directory, so a shipped Corpus writes nothing here, matching the
same rule that makes `corpus.*` logging dev-only. `launcher.py` calls
it behind `srv.IS_DEV` and tolerates its absence.

THE PID IS THE POINT
--------------------
A crash or a SIGKILL skips `clear()`, leaving a file that points at a
port nothing is serving — or worse, one the OS has since handed to an
unrelated process. So the pid is recorded alongside, and `read()`
returns None when that pid is gone. A stale file corrects itself
instead of sending the next reader somewhere wrong.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_PATH = Path.home() / ".corpus" / "server.json"


def _alive(pid: int) -> bool:
    """Is this pid still running?

    `os.kill(pid, 0)` signals nothing and raises if the process is gone.
    PermissionError means it exists but belongs to someone else, which
    still counts as alive.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False
    return True


def write(port: int, path: Path | None = None) -> Path:
    """Record the live server's address. Never raises — a launcher that
    cannot write a convenience file must still start."""
    p = Path(path) if path else DEFAULT_PATH
    payload = {
        "url": f"http://127.0.0.1:{port}",
        "port": int(port),
        "pid": os.getpid(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    except Exception:
        pass
    return p


def read(path: Path | None = None) -> dict | None:
    """The running server's address, or None.

    None covers all three "do not use this" cases: no file, unreadable
    file, and a file whose process has died.
    """
    p = Path(path) if path else DEFAULT_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("url"):
        return None
    if not _alive(int(data.get("pid") or 0)):
        return None
    return data


def clear(path: Path | None = None) -> None:
    p = Path(path) if path else DEFAULT_PATH
    try:
        p.unlink()
    except Exception:
        pass
