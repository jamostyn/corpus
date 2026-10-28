"""Corpus version — single source of truth.

Bumped by hand per release. Read by:
  * config_api.py — surfaces via GET /api/version so the frontend
    (and future bug reports) can include it in error contexts.
  * build_ship.py — names the output zip as Corpus-v<version>.zip.

Keep this file trivially parseable (one assignment, no imports) so
the build script can `grep` it without importing the whole app.
"""
__version__ = "0.4.2"
