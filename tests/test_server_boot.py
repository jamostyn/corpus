"""Server module boots cleanly and registers the expected routes.

If a refactor breaks an import or drops a route, this fails immediately.
"""


def test_server_imports():
    import server                                # noqa: F401


# Every route a SHIPPED build must serve. Dev-only routes (/api/dev/*,
# /dev_only/<path>) are deliberately absent — they exist only while
# python/dev_only/ and src/dev_only/ are on disk, and are asserted
# separately below. Flask's static handler (/<path:filename>) is also
# excluded: it is framework-provided, not ours.
SHIPPED_ROUTES = {
    "/",
    "/api/config",
    "/api/version",
    "/api/pick-corpus",
    "/api/papers",
    "/api/paper/<slug>",
    "/api/citations",
    "/api/authors",
    "/api/author/<key>",
    "/api/institutions",
    "/api/institution/<key>",
    "/api/journals",
    "/api/journal/<key>",
    "/api/extract",
    "/api/scan",
    "/api/tooltips",
    "/api/paper/<slug>/highlights",
    "/api/paper/<slug>/reveal",
    "/api/paper/<slug>/reveal/<kind>",
    "/api/paper/<slug>/re-extract",
    "/api/notes",
    "/api/note/<nid>",
    "/api/projects",
    "/api/project/<pid>",
    "/api/project/<pid>/members",
    "/api/member-projects/<kind>/<mid>",
    "/api/bridges",
    "/api/bridges/compute",
    "/api/paper/<slug>/citers",
    "/api/paper/<slug>/citers/fetch",
    "/api/citers/fetch-all",
    "/api/documents",
    "/api/document/<doc_id>",
    "/api/document/<doc_id>/highlights",
    "/document/<doc_id>/pdf",
    "/api/progress",
    "/pdf/<slug>",
}


def test_all_expected_routes_registered():
    """Catches: a blueprint failing to register, or a route being
    renamed during a refactor. Every entry here is called by the
    frontend; losing one is a dead button."""
    import server
    rules = {r.rule for r in server.app.url_map.iter_rules()}
    missing = SHIPPED_ROUTES - rules
    assert not missing, f"routes missing after refactor: {sorted(missing)}"


def test_no_unlisted_shipped_routes():
    """Catches: a new user-facing endpoint being added without being
    recorded here.

    This is the half the old test lacked — it only checked for MISSING
    routes, so /api/version and /api/pick-corpus both existed unlisted
    for the whole v0.1 series. An unlisted route is one nobody has
    decided is safe to ship, and it also won't appear in CODE_MAP's
    user-action table."""
    import server
    rules = {r.rule for r in server.app.url_map.iter_rules()}
    dev_or_framework = {r for r in rules
                        if r.startswith("/api/dev/")
                        or r.startswith("/dev_only/")
                        or r == "/<path:filename>"}
    unlisted = rules - SHIPPED_ROUTES - dev_or_framework
    assert not unlisted, (
        f"new routes not recorded in SHIPPED_ROUTES: {sorted(unlisted)}. "
        f"Add them here and to CODE_MAP.md's user-action table.")


def test_paths_helpers_exist():
    import _paths
    for name in ("papers_dir", "summaries_dir", "inbox_dir",
                 "highlights_dir", "notes_dir", "ensure_corpus_layout",
                 "set_corpus_root", "corpus_root"):
        assert hasattr(_paths, name), f"_paths missing: {name}"
