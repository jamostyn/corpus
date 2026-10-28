"""Corpus version — single source of truth.

Bumped by hand per release. Read by:
  * config_api.py — GET /api/version (no screen displays it yet).
  * extract/_api_http.py — the User-Agent sent to Crossref / OpenAlex /
    Semantic Scholar.
  * build_ship.py — names the output zip as Corpus-v<version>.zip.

Keep this file trivially parseable (one assignment, no imports) so
the build script can `grep` it without importing the whole app.
"""
__version__ = "0.4.3"
