# Ship-Readiness Audit — 2026-08-16

Read-only audit run before packaging Corpus v0.1 as a macOS `.app`.
Referenced from `SHIP_PLAN.md` Step 1.

**Result: 6/6 checks PASS. No fixes required before packaging.**

Bundle-excluded dirs (assumed): `python/dev_only/`, `src/dev_only/`,
`tests/`, `scripts/`, `.venv/`, `Corpus.command`, `requirements.txt`,
`.git/`, `__pycache__/`.

---

## Check 1 — Dev-only import leaks: PASS

No import/reference to `dev_only` names outside `python/dev_only/` or
`src/dev_only/`.

- `server.py:120-139` guards every `from dev_only import ...` behind
  `if IS_DEV:` and wraps `bug_reports` / `tooltips` / `planning`
  imports in `try/except` (server.py:121-135). If a `dev_only` dir is
  half-present the import failure is swallowed; a `bug_reports`
  failure also force-resets `IS_DEV=False` at `server.py:125`.
- `src/app.js:236-254` only fetches `/dev_only/*` assets inside
  `_loadDevOnly()`, which is only called when `state.config.dev_mode`
  is true (`app.js:226-229`) — driven by `config_api.py:150`, itself
  sourced from `app.config["CORPUS_IS_DEV"]`.

## Check 2 — `IS_DEV` branches complete: PASS

`IS_DEV = (_HERE/"dev_only").is_dir() and (_SRC/"dev_only").is_dir()`
(server.py:64) — a filesystem-presence check, not an env var. Self-
resolves to `False` once both dirs are stripped from the bundle.

`False` branch is fully defined, not an early return:
- `_configure_logging()` disables the `corpus` logger tree and returns
  (server.py:174-179) rather than leaving handlers unset.
- Access-log hooks aren't registered (server.py:84-99).
- Dev-only blueprints + `/dev_only/*` static route aren't registered
  (server.py:120-139).

No half-initialized state.

## Check 3 — Dev-environment path assumptions: PASS

Only hits for `.venv` / `.git` / `Organized Files` / `requirements.txt`
/ `Corpus.command` / `pytest` / `venv/bin/` / `/Users/` / `scratchpad`
across `python/` and `src/` (excluding `dev_only/`) are benign:
"scratchpad" appears only in comments / UI copy describing the notes
feature as a metaphorical scratchpad
(`python/extract/oa_enrichment.py:41`, `python/extract/_paths.py:78`,
`src/notes.js:94`). No dev-machine paths.

## Check 4 — Hard-coded ports / URLs: PASS

`5051` only appears inside `if __name__ == "__main__":`
(`server.py:227-231`), never executed by `launcher.py`, which imports
`server` as a module and calls `make_server("127.0.0.1", <ephemeral
port>, srv.app, ...)` (`launcher.py:65-66`) before any `__main__`
guard could fire.

`src/tooltips.default.js:108`'s "5051" is inside an OpenAlex ID
example string (`A5051345729`), unrelated.

## Check 5 — `sys.argv` / CLI dependencies: PASS

Only `if __name__ == "__main__":` at `server.py:227`. No `argparse`,
no `sys.argv` anywhere in shipped `python/` or `src/`. Confirms Jack's
"no CLI surface" cleanup is complete.

## Check 6 — Runtime file writes: PASS

All `Path.home()` / `expanduser()` writes resolve to `~/.corpus/...`:
- `config_api.py:44` — `CONFIG_PATH = Path.home()/".corpus"/"config.json"`
- `config_api.py:64` — writes `CONFIG_PATH`
- `server.py:190-198` — log dir under `CONFIG_DIR`, only when `IS_DEV`
- `oa_enrichment.py:46,86-91` — `oa_cache` under `~/.corpus` or override

Other writes (`notes_api.py:255-283`, `papers_api.py:204`,
`extract_api.py:164,200,268,290,304`, `extract/_paths.py:73,81,90`)
target `corpus_root()`-derived paths (`extract/_paths.py:42-90`) —
i.e. the user's chosen corpus directory. No writes to CWD or to a
Resources / bundle path.

---

## Not blocking

- The `try/except: pass` swallow around dev-only `tooltips` /
  `planning` imports (`server.py:126-135`) is fine for shipped builds
  (branch never taken) but masks real dev-time import errors.
  Pre-existing dev-only concern, out of scope for ship-readiness.

## Verdict

Nothing to fix. Step 2 in `SHIP_PLAN.md` is a no-op. Proceed to
Step 3 (version stamp).
