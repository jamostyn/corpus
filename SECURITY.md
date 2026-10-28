# Security

## Reporting a problem

Please report security problems privately, not in a public issue: on
this repository go to **Security → Report a vulnerability**. Include
what you did, what happened, and the Corpus version (it is in the name
of the file you downloaded).

## What Corpus exposes

- Corpus runs a local web server for its own window. It listens on
  `127.0.0.1` only, on a port chosen at start-up, and is not reachable
  from other computers.
- It reads and writes only the library folder you choose, plus its
  settings in `~/.corpus/`.
- API keys you enter (e.g. Semantic Scholar) are kept in the operating
  system's keychain, not in files.
- It contacts Crossref, OpenAlex and Semantic Scholar to look up
  papers. Nothing else is sent anywhere; there is no account and no
  telemetry.

Only the latest release receives fixes.
