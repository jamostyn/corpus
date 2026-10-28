# dev_only/  (frontend)

**Everything here is DEV-ONLY. NOT to be shipped to the distributed build.**

Loaded conditionally by `src/app.js` when `/api/config` reports
`dev_mode: true` — which only happens when `python/dev_only/` exists on
disk (i.e. running from the dev repo, not from a shipped build).

## Contents

- `bug-reporter.js`    — injects a "Bug report" button into the topbar,
                         opens a modal with html2canvas screenshot capture,
                         draw-highlight-boxes UI, and description textarea,
                         POSTs the result to `/api/dev/bug-report`.
- `bug-reporter.css`   — styles for the button + modal.
- `html2canvas.min.js` — vendored 1.4.1 UMD build (MIT licensed).
                         200 KB — fine here, not going to ship.
