# dev_only/  (python)

**Everything here is DEV-ONLY. NOT to be shipped to the distributed build.**

The eventual `scripts/sync-to-ship.sh` will exclude any `dev_only/` path
from what it copies into `../../ship/`. Same convention as `src/dev_only/`.

## Contents

- `bug_reports.py` — Flask blueprint exposing `POST /api/dev/bug-report`.
  Saves a screenshot + description under `~/.corpus/bug-reports/<timestamp>/`.

## Wiring

`python/server.py` checks for `dev_only/` at boot. If it exists, the
blueprint is registered and `/api/config` reports `dev_mode: true`. In
the shipped build (where `dev_only/` won't exist), the endpoint is
absent, `dev_mode: false`, and the frontend's `dev_only/` bundle isn't
loaded.
