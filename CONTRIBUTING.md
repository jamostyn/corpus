# Contributing to Corpus

Rules to keep the code, docs, and logs in sync so that "click a
button and check the log" always works as a diagnostic.

## The contract

If a user clicks a thing:
1. **The documentation** should predict what code runs and what log
   lines fire.
2. **The log** should confirm it actually ran — **in dev builds only**.

Any change that adds or moves a user-facing action MUST maintain
this contract.

## Logging is dev-only

The entire `corpus.*` logger tree is disabled in shipped builds
(`_configure_logging` sets `logger.disabled = True` when `IS_DEV`
is False, and the access-log Flask hooks are not registered at all).
Shipped users produce zero log output — no `~/.corpus/logs/server.log`
file, no per-request access line, no event logs. This is a privacy
guarantee.

You still write `logger.info(...)` calls the same way. They just
short-circuit at the emitter in ship mode. Cost in ship: near-zero.

If you're adding a feature that needs to be visible in a shipped
build (e.g. a first-run diagnostic banner), use a different
mechanism — a toast, a UI badge, an `~/.corpus/errors/` sidecar
file — NOT the logger.

## Checklist — every endpoint or flow change

Applies to: new `@app.route` / `@blueprint.route`, new user-visible
button, new script that touches disk, new background task.

- [ ] **Module logger present** — `logger = logging.getLogger("corpus.<module>")`
      at the top of the file. Every module that produces observable
      side effects has one.
- [ ] **Access log covered** — every `/api/*`, `/pdf/*`, `/dev/*` route
      is automatically covered by `server.py`'s
      `_access_log_finish` hook. You don't add this; you inherit it.
- [ ] **Event log at every state change** — writing a file, mutating
      an aggregate, hitting an external API, spawning a thread. Format:
      `<verb>_<noun> key=val key=val` (snake_case verb, prefer
      terse structured k=v pairs, not free prose). Examples:
      `note_created id=…`, `inbox_processed src=… slug=…`,
      `highlights_saved slug=… count=…`.
- [ ] **Failure logs** — every `except` that swallows or converts an
      error emits `logger.warning(..., exc_info=True)`. If it's an
      expected-error condition (e.g. bad user input), `logger.info`
      is fine.
- [ ] **CODE_MAP row updated** — add a row in the
      "User action → log signature" table (`CODE_MAP.md`) whenever
      you add a new user-facing action. Include: what the user
      clicks, which endpoints get hit, which event log lines fire.
- [ ] **Feature-to-files map updated** — if the new code creates a
      new file or moves a symbol, update the feature-to-files map
      + directory tree in `CODE_MAP.md`.
- [ ] **CHANGELOG entry** — one section per session or per commit
      cluster. What changed and why.
- [ ] **Test coverage** — endpoint test if reasonable (see
      `tests/test_scan_endpoint.py` for the "empty happy path"
      shape). Pure functions get a fixture-based unit test.

## No CLI scripts in Corpus

Corpus is a desktop app. Every user-facing feature is a button or
menu item, not a `python3 script.py` invocation. If a workflow
needs "run script X", it needs a button first. Existing library
modules (`prefill_summary.py`, `extract_metadata.py`, `oa_enrichment.py`,
etc.) do NOT have `if __name__ == "__main__":` blocks — they're
libraries called from the Flask endpoints.

If you need a debug helper that a developer runs manually, put it
under `python/dev_only/` where it's stripped from shipped builds.

## Naming conventions for log lines

Terse structured event names, `snake_case`. Examples of the shape:

- Success: `note_created id=abc123 title="Prelims plan"`
- Failure: `note_save_failed id=abc123 reason=disk_full` (with `exc_info=True`)
- External: `api_get_json failed url=https://api.crossref.org/… reason=timeout`
- Aggregate: `author_dedupe_merged survivor=yi-han dropped=[yi-han-gyol]`

Two grep patterns that stay stable across changes:
```
grep 'FAIL\|failed'      # anything that broke
grep '<endpoint-path>'   # specific endpoint history
```

## The one-sentence self-check

"If Jack tells me exactly what he clicked, can I look at
`~/.corpus/logs/server.log` and reconstruct what happened?" If not,
add the log line before landing the change.
