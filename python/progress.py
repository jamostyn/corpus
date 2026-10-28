"""One progress channel for every long-running job.

Jack, 2026-09-17, after watching a 25-paper import: "can you make sure
that the loading process is incredibly transparent so you can know what
step it is on, what function is being performed, and how much is left."

He was not exaggerating the problem. The log for that import shows
`POST /api/scan` taking 26.6s and the bridge search another 21.4s —
roughly 48 seconds during which the UI said "scanning corpus…" once
and then nothing at all.

WHY ONE SHARED CHANNEL
----------------------
Scan, Add PDFs and the bridge search are three different long jobs, and
the obvious thing is to give each its own progress plumbing. That would
be three copies of the same idea, drifting — one showing a count,
another a spinner, the third nothing. Instead there is a single job
slot: whatever is running writes into it, and the frontend polls one
endpoint and renders whatever it finds.

Consequence, stated because it is a real limit: only ONE job is
tracked at a time. `start()` refuses while one is running, and the
caller must honour that refusal — `/api/scan`, `/api/extract` and both
citer endpoints answer 409. Writes go through the `Job` handle
`start()` returns, so a refused caller cannot write into the running
job's numbers.

WHY POLLING RATHER THAN STREAMING
---------------------------------
`launcher.py` runs werkzeug with `threaded=True`, so a poll is answered
while a scan is still in its request thread — verified before building
this. Server-sent events would avoid the poll, but they add a long-
lived connection and a reconnect story for a value that changes a few
times a second and is worthless once the job ends.

Thread-safe: the scan writes from its request thread and the bridge
search from a background thread.
"""
from __future__ import annotations

import logging
import threading
import time

from flask import Blueprint, jsonify

logger = logging.getLogger("corpus.progress")

progress_bp = Blueprint("progress", __name__)

_lock = threading.Lock()
_job: dict | None = None

# A finished job stays readable this long so a poll that lands just
# after completion still sees the result (and the error, if any) rather
# than an empty slot that looks like nothing ever ran.
LINGER_SECONDS = 20


def _now() -> float:
    return time.monotonic()


class Job:
    """A handle on the running job. The ONLY way to write progress.

    Jack, 2026-09-22: during a 100-paper import "it kept jumping between
    100 and 98 papers total". Two scans were running at once (server.log,
    16:49:34 added=64 and 16:49:36 added=37): each had counted the inbox
    at a different moment, and both wrote their own count into the one
    shared slot, so the total alternated.

    Writes used to be a module-level `step()` that wrote to whatever was
    in the slot, so any caller — including one whose `start()` had been
    refused — could scribble into a job it did not own. Now a write
    carries the token it was issued with and a foreign one is dropped
    and logged, which turns that class of bug from a confusing display
    into a log line naming the culprit.
    """

    __slots__ = ("token",)

    def __init__(self, token: int) -> None:
        self.token = token

    def step(self, phase: str, detail: str = "", done: int = 0, total: int = 0) -> None:
        """Report the current phase and how far through it we are.

        `done`/`total` are units WITHIN the phase (files, papers,
        requests), not across the whole job — a job's phases have
        incomparable units, and pretending otherwise produces a bar that
        jumps backwards.
        """
        with _lock:
            if _job is None or _job["done"]:
                return
            if _job["token"] != self.token:
                if not _job["foreign_logged"]:
                    _job["foreign_logged"] = True
                    logger.warning("progress_foreign_write job=%s phase=%s",
                                   _job["job"], phase)
                return
            _job["phase"] = phase
            _job["detail"] = detail
            _job["done_units"] = done
            _job["total_units"] = total

    def finish(self, error: str | None = None) -> None:
        with _lock:
            if _job is None or _job["token"] != self.token:
                return
            _job["done"] = True
            _job["ended"] = _now()
            _job["error"] = error
            name = _job["job"]
        logger.info("job_finished job=%s error=%s", name, error)


class _NullJob(Job):
    """Accepted everywhere a Job is, reports nowhere.

    For the caller that wanted the slot, was refused, and still has work
    to do (the bridge search). Before this it wrote into the other job's
    banner anyway."""

    def __init__(self) -> None:
        super().__init__(-1)

    def step(self, phase: str, detail: str = "", done: int = 0, total: int = 0) -> None:
        pass

    def finish(self, error: str | None = None) -> None:
        pass


NULL = _NullJob()
_next_token = 0


def start(job: str, phases: list[str] | None = None) -> Job | None:
    """Begin a job. Returns a Job handle, or None if one is running.

    None means REFUSED, and the caller must act on it — an import that
    ignores it and runs anyway is the 100-vs-98 bug.

    `phases` is the planned sequence, so the UI can show "step 2 of 4"
    before step 2 has started. It is advisory — `Job.step()` accepts a
    phase that was never declared.
    """
    global _job, _next_token
    with _lock:
        if _job is not None and not _job["done"]:
            return None
        _next_token += 1
        _job = {
            "job": job,
            "token": _next_token,
            "phases": list(phases or []),
            "phase": "",
            "detail": "",
            "done_units": 0,
            "total_units": 0,
            "started": _now(),
            "ended": None,
            "done": False,
            "error": None,
            "foreign_logged": False,
        }
    logger.info("job_started job=%s", job)
    return Job(_next_token)


def snapshot() -> dict:
    """Current state, or an inactive marker.

    A job that finished more than LINGER_SECONDS ago reads as inactive,
    so a stale success banner cannot sit on screen indefinitely.
    """
    with _lock:
        if _job is None:
            return {"active": False}
        j = dict(_job)
    age = (_now() - j["ended"]) if j["ended"] else 0
    if j["done"] and age > LINGER_SECONDS:
        return {"active": False}
    elapsed = (j["ended"] or _now()) - j["started"]
    phases = j["phases"]
    return {
        "active": True,
        "job": j["job"],
        "phase": j["phase"],
        "detail": j["detail"],
        "done_units": j["done_units"],
        "total_units": j["total_units"],
        "phases": phases,
        "phase_index": (phases.index(j["phase"]) + 1) if j["phase"] in phases else 0,
        "phase_count": len(phases),
        "elapsed_s": round(elapsed, 1),
        "finished": j["done"],
        "error": j["error"],
    }


def reset() -> None:
    """Drop the slot. For tests, and for a caller that needs to start a
    new job after an abandoned one."""
    global _job
    with _lock:
        _job = None


@progress_bp.route("/api/progress", methods=["GET"])
def get_progress():
    """Deliberately NOT behind `require_corpus_or_abort`.

    The frontend polls this every half second while a job runs. A 400
    here would surface as a failed request in the console on every tick
    for anyone who has not picked a corpus yet, which is noise rather
    than information — and with no corpus there is no job to report.
    """
    return jsonify(snapshot())
