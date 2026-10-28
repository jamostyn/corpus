"""Frontend JS suite glue.

`tests/src/*.test.js` are Node-native tests (built-in `node:test`).
This wrapper delegates to `node --test` so the whole test suite still
runs with a single `pytest tests/ -q`. Skips (does NOT fail) when
node is not installed so the Python suite stays green on machines
without node — install with `brew install node` to run the JS side.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_JS_TESTS_DIR = Path(__file__).resolve().parent / "src"
_NODE = shutil.which("node")


@pytest.mark.skipif(
    _NODE is None,
    reason="node not installed — run `brew install node` to enable frontend tests",
)
def test_frontend_suite():
    """Run every `tests/src/*.test.js` under `node --test`. Fails
    (with full stdout/stderr) if any JS test fails.

    Enumerates test files explicitly rather than passing the dir —
    `node --test <dir>` treats the arg as a module path, not a
    directory to walk. `sorted()` for stable ordering.
    """
    test_files = sorted(str(p) for p in _JS_TESTS_DIR.glob("*.test.js"))
    if not test_files:
        pytest.skip("no *.test.js files under tests/src/")
    result = subprocess.run(
        [_NODE, "--test", *test_files],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(
            "Frontend test suite failed.\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
