# Corpus Roadmap

Single home for planned-but-unbuilt Corpus work. Every deferred /
decided-pending / expansion-point item lives here. When an item ships,
its entry is updated or removed in the same commit as the code. When
an idea is dropped, delete the entry.

Order within each section: highest-impact first.

Seeded 2026-08-24 from `CODE_MAP.md` "Known refactor candidates" +
`SHIP_PLAN.md` progress tracker + `CHANGELOG.md` deferrals. Items
carrying a "was Wave N" tag are refactor candidates surfaced by the
2026-08-16 audit; the ones already resolved are not repeated here.

---

## Committed

Work explicitly agreed and pending scheduling.

### macOS asks for Local Network access on launch — cause unknown

- **Status.** Open investigation. No code change made.
- **Origin.** 2026-10-01, Jack after opening v0.4.1: "why when it was
  opened did it ask to see local devices?"
- **Ruled out (checked 2026-10-01).** The Flask server binds only
  `127.0.0.1` (`launcher.py` free-port probe and `make_server`); no
  mDNS/Bonjour/zeroconf package is bundled (`pip list`); pywebview's own
  HTTP server is not started (`webview.start()` without `http_server`);
  nothing in `python/` or `src/app.js` uses `0.0.0.0`, `gethostname` or
  multicast. Werkzeug's `server_bind` calls `socket.getfqdn("127.0.0.1")`,
  but on this machine that resolves via `/etc/hosts` in ~10 ms.
- **Not ruled out.** WKWebView (pywebview's Cocoa backend) or another
  macOS-side behavior. Info.plist has no `NSLocalNetworkUsageDescription`,
  so macOS shows its generic wording.
- **Next probe.** On a launch that shows the prompt, filter Console.app
  for "Corpus" at that moment to see which subsystem requested it. The
  prompt does not repeat for an identity that already answered, so this
  needs a new build (ad-hoc signing may give each build a new identity —
  unverified) or a fresh account.
- **Do not** add `NSLocalNetworkUsageDescription` as a "fix": it only
  changes the prompt's text, not whether it appears.

### Verify the Windows build actually works

- **Origin.** Built 2026-09-01 with the v0.2.0 Windows source zip. Jack
  asked for a shippable Windows path; the build recipe exists and is
  tested as far as macOS allows, but the end product has never run.
  Still true at v0.4.0 (2026-09-29): three releases have carried an
  unrun Windows source zip.
- **First real run, 2026-09-29 (v0.4.0).** The .bat finished and the app
  opened, but the PDF viewer was black: toolbar, no pages. Fixed in dev
  as a probable Windows-registry content-type problem (CHANGELOG
  2026-09-29), with an on-screen readout if the viewer still fails. NOT
  yet re-tested on Windows — the fix ships in the v0.4.1 Windows source
  zip (2026-10-01); rebuild from that and open a paper. The rest
  of the first-run checklist below is still unanswered.
- **Second run, 2026-10-15 (v0.4.1).** Viewer still dead; its readout
  said `pdf.mjs: HTTP 404`, `viewer.mjs: text/javascript` — the
  content-type fix worked, but pdf.js itself was never in any Windows
  zip (a `build` prune rule matched `src/vendor/pdfjs/build/`). Fixed in
  v0.4.2. NOT yet re-tested on Windows: rebuild from the v0.4.2 zip and
  open a paper.
- **What is verified here.** The spec evaluates correctly in its
  `IS_WINDOWS` branch when extracted from the built zip (`.ico` icon,
  `BUNDLE` skipped, edgechromium + `keyring.backends.Windows` selected);
  every build input is present in the zip; nothing dev-only, `.venv`,
  `.git` or test-related leaks into it.
- **What is NOT verified, and cannot be from macOS.** That
  `build_windows.bat` completes, that `Corpus.exe` launches, that the
  pywebview window opens (Edge WebView2 runtime is present on current
  Windows 10/11 but not guaranteed on older builds), that keyring picks
  the Windows Credential Locker, and that the PDF viewer iframe behaves.
- **First run should check, in order.** Does the .bat finish; does the
  .exe open a window at all; does the folder picker work; does adding a
  PDF extract; do API keys persist across a restart; does the PDF
  viewer render and highlight.
- **Known risk, unmeasured.** `pythonnet` is installed by the .bat
  rather than `requirements.txt` because it is Windows-only and would
  fail to install on macOS. If pywebview's edgechromium backend does
  not need it on a given machine, the install is harmless noise; if a
  machine lacks the Edge WebView2 runtime entirely, pywebview should
  fall back to opening a browser tab (`launcher.py` has that path), but
  that fallback is untested on Windows.
- **Touch-list sketch.** Whatever the first real run turns up —
  likely `build_windows.bat` (missing dep, path quoting) or the spec's
  `hiddenimports`.

### Ship-plan Steps 10 + 11 + 13 — fresh-account smoke test + ship commit tag

- **Origin.** `SHIP_PLAN.md` Phase 3 (steps 10-13). v0.1.0 and v0.1.1
  both shipped without Steps 10/11/13 (Jack: "i already gave the zip to
  someone and it worked"). Step 12 (README-in-zip) is done — `build_ship.py`
  writes it every build.
- **Still outstanding as of v0.4.1 (2026-10-01).** SIX releases have now
  gone out without the fresh-account walkthrough, not the two this entry
  originally named. 0.3.0 added Projects, bridges, caching and a
  progress channel; 0.4.0 adds the Documents tab, the note workspace,
  stored citers and note revisions — the untested surface keeps growing.
- **What.** Delete `~/.corpus/config.json` to simulate fresh user; walk
  through Step 10's checklist (folder picker → add PDF → scan → paper
  detail → note → author/institution/journal panes). Repeat under a
  macOS Guest account (Step 11). Then `git tag v<version>` in both
  `dev/` and `ship/` (Step 13).
- **Blocked on.** Nothing. Just requires ~15 min of manual testing.
- **Touch-list sketch.** No code. Update `SHIP_PLAN.md` progress
  tracker + this entry when done.
- **Why it matters.** Verified 2026-08-24: the test suite never runs
  against `dist/Corpus.app`, only the source tree. Bundle-only
  failures — a missing data file, a wrong `sys._MEIPASS` path, a
  missing hidden import — are invisible to CI-style checks. Manual
  launch is the only detector Corpus has. See `TESTING.md` § Known gaps.

### Retroactive git tags for v0.1.0, v0.1.1 and v0.2.0

- **Origin.** `SHIP_PLAN.md` Step 13 lists tagging as optional; it was
  skipped for the first three releases. Confirmed 2026-08-24 and again
  2026-09-18: `git tag` returns empty in both `dev/` and `ship/`.
- **v0.3.0 IS tagged** — `../ship/CLAUDE.md`'s recipe now includes
  `git tag v<version>`, so this entry covers only the backlog.
- **What.** `git tag v0.1.0 14a42cf`, `git tag v0.1.1 c8e3e66` and
  `git tag v0.2.0 a3a10b1` in `dev/`; matching tags in `ship/` against
  `413c675` (which carried both early zips) and `31e0603`. Dev commits
  are recorded in `../ship/SHIPS.md`.
- **Blocked on.** Nothing. Two commands per repo.
- **Touch-list sketch.** No files. Tags only. `../ship/CLAUDE.md`'s
  release recipe already includes tagging for future releases.

### PDF references are not in the citation index

- **Origin.** Built 2026-08-25 alongside PDF reference extraction, and
  deliberately left out of scope in the same change.
- **What.** `citations.resolve_references` folds PDF-read references
  into the DISPLAY list, but `build_index` reads only the API
  references stored in summaries. PDF references live in a
  `<corpus>/pdf_refs/` cache populated lazily when a paper is viewed,
  so indexing them today would make the citation graph depend on which
  papers happen to have been opened — links appearing after a click are
  worse than links consistently absent.
- **Measured cost.** 3 edges on the 57-paper reference corpus: 22 with
  API references only, 25 including PDF-derived DOIs and exact-title
  matches. Two of the three come from `yang-2026`, one of the papers
  with no deposited references at all.
- **What it needs.** A pass that reads every PDF so the cache is
  complete before the index runs. Per the no-CLI rule that is a button,
  not a script — probably alongside Scan. Then `build_index` can read
  the cache without the determinism problem.
- **Also decided.** Title matching for linking should use a 0.90
  similarity floor with a ±1 year window. Measured 2026-08-25:
  thresholds of 0.80, 0.85 and 0.90 produce IDENTICAL results on this
  corpus because every real match scores 1.00. There is no fuzzy
  middle ground to tune, so the conservative floor costs nothing.
- **Touch-list sketch.** `citations.build_index` (read the cache),
  a warm-all endpoint + button, `CODE_MAP.md` citation section,
  `tests/test_citations.py`.

### Documents tab — what is still left out

- **Status.** Idea. Linking from notes, rename, pop-out and projects
  SHIPPED 2026-09-25 (second round, Jack's request) — see CHANGELOG.
- **No delete.** A mistaken upload stays until its folder
  (`<corpus>/documents/<id>/`) is removed by hand. Touch-list:
  `DELETE /api/document/<id>` (refuse or warn while notes link to it or
  projects hold it), a button in `documents.js`, CODE_MAP user-action
  row.
- **Promote a document to a paper — offered, Jack said "leave it for
  now" (2026-09-26).** Probed live: the one document (Jenkins, "Four
  Points to Remember: A Tetrahedral Model of Memory Experiments") is a
  registered `book-chapter` in all three services — DOI
  10.4324/9781315796192-33, OpenAlex W3002298642 (190 cites), S2 (97).
  Caveat: every service dates it 2014 (Psychology Press reissue), not
  1979, so it would file as `jenkins-2014` and "Jenkins 1979" citations
  would rarely link. Touch-list if built: a Promote button in
  `documents.js`, an endpoint that moves the PDF into the inbox path and
  carries `highlights.json` over to `highlights/<slug>.json`.
- ~~Link picker lists documents only once the tab has loaded~~ — WRONG, removed
  2026-09-28: the picker's `selectType` already loads an empty list on first
  use.

### Recover papers whose DOI resolution failed (title lookup)

- **Origin.** Jack, 2026-08-26: do OpenAlex / S2 hold DOI-less papers
  and assign their own ids, and is title search the way in? Both
  questions answered by live probing.
- **Coverage, established by probe:**
  * **Crossref** — its identifier IS the DOI; it cannot represent a
    DOI-less work.
  * **OpenAlex** — own `W…` ids; **101,993,756 works with
    `has_doi:false`**, sampled as books (*Using multivariate
    statistics*, *Case Study Research*).
  * **Semantic Scholar** — own `paperId` + `corpusId`, plus MAG /
    PubMed ids.
  * NOT established, deliberately unclaimed: whether either service
    runs its own PDF extraction. Not tested.

- **VERIFIED QUERY METHOD.** This is the part that matters; the naive
  approach measured badly.

  **OpenAlex — use `filter=title.search:`, never `search=`.**

      https://api.openalex.org/works?filter=title.search:<title>,publication_year:<year>

  Measured on one known title:

  | query form | right title | wrong title |
  |---|---|---|
  | `search=` (free text) | count 48,494, top hit correct | count 6,341, **returns the target anyway** |
  | `filter=title.search:` | **count 1** | **count 0** |

  Free-text `search=` ranks over the whole record, so it returns a
  confident-looking hit for a title that is not in the index — a false
  positive generator. With `title.search` the count itself becomes the
  confidence signal.

  Also measured: appending the author to a free-text query makes it
  WORSE (top hit similarity fell to 0.34). Use the structured
  `publication_year` filter to narrow, not extra query tokens.

  **Semantic Scholar — use `/paper/search/match`, not `/paper/search`.**

      https://api.semanticscholar.org/graph/v1/paper/search/match?query=<title>&fields=title,corpusId,externalIds

  Purpose-built title -> single best match. Returns `matchScore`, and
  a clean **404 "Title match not found"** when there is no match.
  Verified keyless. (`/paper/search` returned 429 on every keyless
  attempt — an earlier note here said S2 needs a key for any title
  search; that was too broad, it applies to `/search`, not `/match`.)

- **Still verify the hit.** Both endpoints can return a near-miss.
  Compare the returned title to the query with
  `_api_http.title_similarity` and require >= 0.90, the same floor
  already settled for citation title matching.

- **Known failure mode.** An OCR-garbled title returns 0 results from
  OpenAlex — no false positive, but no recovery either. Papers whose
  title cannot be read at all stay unresolvable by this route.

- **Open decision for Jack.** When a work genuinely has no DOI, storing
  the OpenAlex `W…` id or S2 `corpusId` would make it linkable — but
  `citations.py` matches on DOI exclusively today. Admitting a second
  identifier space changes that contract, and every link and dedupe
  rule keyed on DOI would need to understand it.
- **Touch-list sketch.** `openalex_client` + `semanticscholar_client`
  (add title lookup; only Crossref has one today), `extract_metadata`
  resolver chain, `citations` matching if alternate ids are admitted,
  `tests/test_metadata.py`.

- **Re-probed 2026-09-24 on the 1,080-paper corpus** (probe script in the
  session scratchpad, read-only). 11 papers have `doi: unknown`, and ALL
  11 also have no title — extraction failed wholesale, not just the DOI.
  Each was looked up twice: with the title Corpus's own first-page
  font-size extractor produces, and with the known-correct title (the
  ceiling).

  | | OpenAlex | S2 | Crossref |
  |---|---|---|---|
  | correct title | 10/11 | 9/11 (1 rate-limited) | 8/11 |
  | Corpus-extracted title | 2/11 | 2/11 | 2/11 |

  * **8 of 11 have a DOI** the services hand back — resolution
    failures, not DOI-less works: bjork-2020, cronbach-1957,
    guadagnoli-2004 (sitting as slug `download`), karni-1991,
    knowlton-1993, knowlton-1994, lehmann-2015, snow-1996.
  * **2 are genuinely DOI-less but indexed under their own ids:**
    bjork-1992 (OpenAlex W2595422523, S2 82d8e57aaf…, 450 citations),
    snow-1980 (W1274516310, a 1980 technical report). These are the
    case the "open decision" above is about.
  * **1 unfindable:** catrambone-1995 — a pure scan with no title
    anywhere; needs OCR first.
  * **More information available: yes.** Every found paper carries a
    citation count (Corpus: `unknown`), a reference list (20–76 refs),
    and 6 have abstracts.
  * **The bottleneck is title extraction, not lookup.** 3 papers
    produced no candidate at all; 6 produced garbled ones — words
    dropped mid-title ("A New Theory of Disuse and an Old Theory of
    Stimulus Fluctuation" → "Theory Disuse Theory and Stimulus
    Fluctuation"; "The Learning of Categories: …" → "Learning
    Categories:"), consistent with title words split across font-size
    buckets.
  * **Separate DOI-extraction miss:** lehmann-2015 prints "DOI
    10.1007/s11409-015-9149-z" on page 1 and still resolved to nothing.
  * **Probe gotchas, for whoever builds this:** OpenAlex needs the key
    that `server.init_app()` loads (a bare process gets `None` back);
    S2 keyless throttles bursts (back off 1–10 s); never pass the author
    `"unknown"` to Crossref's `query.author` — it filters results out.

- **BUILT 2026-09-25** (CHANGELOG same date): line-based title
  extraction with gap-aware word breaks, OpenAlex + S2 title lookup
  after Crossref (`_resolve_by_title`), DOI-less works recorded from
  their OpenAlex / S2 records, /Info and page-1 seeds both tried, and a
  front-matter guard on every exit. Re-extracting the 11: **6 recovered,
  none mis-identified** — DOI found for guadagnoli-2004 (was `download`),
  karni-1991, knowlton-1993, lehmann-2016 (was lehmann-2015); identified
  WITHOUT a DOI for bjork-1992 (W2595422523) and snow-1980
  (W1274516310).

- **Still open, from that run:**
  * **3 scans need OCR** — catrambone-1995, cronbach-1957,
    knowlton-1994 yield no text at all. Same blocker as the OCR entry
    further down; title lookup cannot help until there is text.
  * **2 titles not in the largest type** — bjork-2020 (a JARMAC
    commentary; the author block is the largest text) and snow-1996
    (page 1 is the journal masthead). Their candidates are author and
    masthead lines. Needs a title detector that looks past the top size
    tier, e.g. the first tier that follows the masthead and precedes the
    author line. Both services have them (probe: correct title found).
  * **DOI-less works are identified but not linked.** bjork-1992 and
    snow-1980 now carry `oa_paper_id` / `ss_paper_id`, but
    `citations.py` matches on DOI only, so no corpus paper links to
    them. The open decision above stands; the bridge search already
    keys on OpenAlex ids, so it is the natural first consumer.
  * **S2 ids are flaky keyless.** Across three runs the same two
    DOI-less papers got `ss_paper_id` twice and missed it once — S2
    throttling. A Semantic Scholar key in Settings removes it.

### Recover the two unresolved papers — tested end to end 2026-08-26

Both of the corpus's fully-unknown papers were run through the title
lookup. One is fully recoverable, one is not. Results below are probe
output, not estimates.

**knowlton-1993 — FULLY RECOVERABLE, and the fix is mechanical.**

The title was recovered from the PDF by FONT SIZE, which is the piece
that unblocks everything: page 1 of this file is the tail of a
different article's reference list, so position-based extraction reads
bacteriology. The two largest text runs on page 0 (17.1pt, 16.6pt) are
the title lines; the next (12.5pt) is the author line.

    title   : The Learning of Categories: Parallel Brain Systems for
              Item Memory and Category Knowledge
    authors : Barbara J. Knowlton and Larry R. Squire

Fed to both services:

    OpenAlex  count=1  W2038221682  doi 10.1126/science.8259522
              Science, 1993, both authors, 487 citations,
              40 referenced_works
    S2        corpusId 6713914, PubMed 8259522, 35 refs, 513 cites

So this paper is not DOI-less at all — it is a resolution failure, and
font-size title extraction plus `filter=title.search` fixes it.

**Its reference list is recoverable too**, which matters because PDF
extraction produces garbage for this slug (entries belonging to the
neighbouring article). OpenAlex's 40 `referenced_works` resolve to DOIs
in ONE batched call:

    https://api.openalex.org/works?filter=openalex_id:W1|W2|W3&select=id,doi,title

That is a better reference source than the PDF for any paper whose
layout defeats the parser.

**catrambone-1995 — recoverable via OCR. Identified 2026-08-26.**

The file is a pure scan: 13 pages, ZERO embedded fonts, one image per
page, 0 characters from every PyMuPDF extraction mode. (`get_text("html")`
returns 3.7M characters, but stripping the `<img>` tags leaves exactly
0 — it is base64 PNG, not text.) Jack can read it because his eyes
decode the picture; there is no text layer for software to read. The
give-away test in the app: the text cannot be selected or highlighted.

**macOS Vision OCR reads it, with NO new dependency.** `pyobjc-core`
is already installed via pywebview, and Vision.framework loads
dynamically:

    objc.loadBundle("Vision", globals(),
        bundle_path="/System/Library/Frameworks/Vision.framework")
    # render page with pymupdf -> PNG -> VNImageRequestHandler
    # -> VNRecognizeTextRequest(recognitionLevel=1)

Measured: 96 lines from page 0 in **0.67 s** (~9 s for all 13 pages),
entirely offline — no cloud OCR, so no privacy cost.

The paper is now IDENTIFIED, not guessed:

    OCR'd title : "Aiding Subgoal Learning: Effects on Transfer"
    OCR'd line 2: "1995, Vol. 87, 1, 5-17"
    OCR'd author: "Richard Catrambone"
    -> OpenAlex title.search count=2, top hit
       doi 10.1037/0022-0663.87.1.5
       vol 87, iss 1, pp 5-17, Richard Catrambone
    title similarity OCR vs OpenAlex = 1.00

Volume, issue, page range and author all corroborate independently.
This supersedes the earlier note that it needed Jack's confirmation —
that was written when the identification rested on author+year+page
count alone.

Character-level OCR quality on this old scan is mediocre ("Joumal of
Edu¢alioJJal Psychology"). Good enough for identification and title
matching; NOT tested for reference-list extraction, and the error rate
suggests that would be noisy. Do not assume it.

**UNVERIFIED and important:** whether `objc.loadBundle` on
Vision.framework works inside the PyInstaller `.app`. It reads from
/System/Library so it should, but the bundle has its own import rules
and this was only tested in the dev venv. Must be checked before
shipping any OCR feature.

**CORRECTION — the font-size extractor already exists.** An earlier
version of this entry proposed building one. `extract_metadata.
_title_candidates_from_pdf_text` has done font-cluster ranking since
before this work started, and `crossref_search_by_title` is already
wired into the resolver chain. The gap is a bug in the existing code,
not a missing feature.

**The bug: exact-size bucketing shatters the title.** Line ~503 does
`buckets.setdefault(round(size, 1), ...)`, keying on the rounded font
size. In knowlton-1993 the title's words are measured at 17.1, 16.6,
16.5 and 15.9pt — a scanned/reflowed PDF gives near-identical words
slightly different sizes. So one title lands in four buckets holding
"Memory", "Systems", "The | Knowledge", "Category", and the extractor
returns the fragment `'Learning Categories:'`. Fed to Crossref that
matches nothing, and the paper falls through to `needs_doi: true`.

**A size TOLERANCE was proposed as the fix. It was tested and it does
NOT work.** Recorded here so nobody spends the afternoon rediscovering
that.

What was tried, in order, all against knowlton-1993:

  1. Group sizes within 5-15% of the cluster's largest. Pulls in more
     words but the order scrambles, because the existing code sorts
     spans by `y` alone and this title's words sit at slightly
     different `y` within each line.
  2. Add reading-order sorting (group into lines by y, then left to
     right by x). Still wrong: `'The Systems Learning of Categories:
     Brain Memory Item and Category Knowledge'`.
  3. Cluster by RELATIVE GAP between adjacent distinct sizes instead
     of a fixed tolerance. This one fails catastrophically — it
     swallows the entire page as the "title".

Why (3) fails, and why any pure size rule will: page 0 has **70
distinct font sizes** running 4.6 -> 17.1 in a near-continuum. The
title spans 13.8-17.1pt. The largest adjacent ratio anywhere in the
run is 1.163 (5.7 -> 4.9, down in the footnotes); the title's own
boundary at 13.8 -> 12.5 is only 1.104. There is no gap to cut on.

An earlier note here claimed the sizes separated cleanly. That was an
artifact of having sampled only the title's y-band; across the whole
page they do not.

The words are also individually placed with per-word size jitter
("Parallel" 13.8, "Memory" 17.1 within one title), which is what a
scanned-then-reflowed PDF produces.

**So this is NOT a small fix, and the direction is probably wrong.**
Position is the stronger signal than size here — the title is a
contiguous block near the top of the article's own first page, and the
real difficulty is that page 0 of this file is the PREVIOUS article's
end matter, so "top of page 0" is not the title. Any future attempt
should start from locating the article's first page (the one bearing
the abstract / author affiliation block), not from font size.

Cheaper alternatives that are already proven to work on this file:
OCR (page renders, then Vision) and the OpenAlex/S2 title lookup once
any usable title exists.

- **Touch-list sketch.** `extract_metadata._title_candidates_from_pdf_text`
  (needs a position-based rethink, NOT the tolerance tweak that was
  tried and failed); `openalex_client`
  + `semanticscholar_client` title lookup (neither has one; only
  Crossref does); optional OpenAlex reference-list import for papers
  the PDF parser fails; OCR fallback for scans; `tests/test_metadata.py`
  with knowlton-1993's span sizes as a fixture.

### PDF title extraction is wrong on ~10% of entries

- **Origin.** Found 2026-08-25 while answering "what worked, what
  didn't" — a quality check the original validation did NOT perform.
  The first pass measured "structurally malformed" entries (missing
  author or year) at 0.1%, which is true and misleading: these entries
  have a correct author and a correct year, so they pass that check
  while carrying a wrong title.
- **What.** 320 of 3066 extracted entries (10.4%) have a title that is
  a parse fragment rather than a title: `'2'`, `'pp'`, `'907-915'`,
  `'), pp. 65-77; R'`, `'[4] J.A. Mollick, H'`.
- **Cause, verified by reading the raw entries.** `_title()` assumes
  the year comes directly after the authors (APA: "Smith, J. (2001).
  Title here."). In styles where the year sits at the END of the
  citation, everything "after the year" is trailing junk — a page
  range, or the next entry's number. The author, year, and raw text
  are all CORRECT in these cases; only the title slice is wrong.
- **Why it matters more than the percentage suggests.** These titles
  are displayed to the user as fact in the reference list. A blank is
  honest; a confident wrong title is not.
- **Worst offenders.** kay-2024 (158 of 163 entries), pisupati-2024
  (33), raab-2022 (18), franklin-2018 (16), hu-2025 (14).
- **Fix sketch.** Detect where the year sits within the entry. If it
  is in the last ~25% of the string, take the title from BEFORE it
  instead of after. Fall back to returning "" when neither slice looks
  like a title (length, capitalisation, no leading punctuation) —
  blank beats wrong.
- **Touch-list sketch.** `extract_references_pdf._title`, new cases in
  `tests/test_pdf_refs.py` covering year-last styles, re-run the
  57-paper measurement to confirm the fragment rate drops.

### knowlton-1993 bundles several citations per entry

- **Origin.** Same 2026-08-25 quality check.
- **What.** Science 1993 numbered notes put several semicolon-separated
  citations inside one numbered item. The extractor returns 20 entries
  where each is a bundle, so authors and years attach to the wrong
  citation and one entry produced `author='Exp'` (from "J. Exp.
  Psychol."). Journal-abbreviation-as-author is rare overall — 2 of
  3066 entries — and concentrated here.
- **Severity: low, but do not trust this paper's references.** It is
  one of the 8 papers with no deposited references, so there is nothing
  to fall back on.
- **Fix sketch.** Split bundled entries on `;` when the following
  fragment starts with an initials-first author shape. Guard against
  splitting a title that contains a semicolon.
- **Touch-list sketch.** `extract_references_pdf.split_entries`,
  `tests/test_pdf_refs.py`.

### 726 bare-DOI references still need a title lookup

- **Origin.** Measured while building PDF extraction, 2026-08-25.
- **What.** Publishers frequently deposit a reference as a DOI and
  nothing else. PDF extraction cut these from 726 to 579 (of 4426
  references shown), but the rest sit in papers whose PDFs print no
  DOIs, so there is no key to join on. They render as a bare DOI.
- **Options.** A Crossref lookup per unresolved DOI would give exact
  author/title. ~579 calls at ~1/s, cacheable and one-time per
  reference. Positional alignment between the Crossref list and the
  PDF list was considered and rejected as too fragile to risk showing
  a wrong title as fact.
- **Blocked on.** Nothing technical; it is a question of whether Jack
  wants Corpus making that many background API calls.
- **Touch-list sketch.** A resolver keyed by DOI with an on-disk cache;
  `pdf_refs_merge` gains it as a third fill source after PDF;
  `CODE_MAP.md`.

### Reference extraction fails on 7 papers with unusual layouts

- **Origin.** Measured 2026-08-25 across all 57 PDFs.
- **What.** `extract_references_pdf` returns "no_section" for
  abir-2026, eckstein-2020, gershman-2015, kim-2023, stachenfeld-2017,
  yang-2020 and yi-2016 — Nature/Science layouts that omit a
  "References" heading entirely, or place it where the content-based
  fallback does not find it.
- **Severity: low.** All 7 already have complete Crossref reference
  lists, so nothing is currently lost. It would matter if one of them
  were re-imported without a DOI.
- **Also.** catrambone-1995 returns "unreadable" — a scanned image
  with a 12-character text layer. That needs OCR, which is a much
  larger dependency, and is correctly reported rather than guessed at.
- **Touch-list sketch.** `extract_references_pdf._find_by_content`
  (loosen), `tests/test_pdf_refs.py`.

### `import fitz` is deprecated — extraction breaks when PyMuPDF removes it

- **Origin.** Surfaced 2026-08-24 during the onboarding smoke test.
  Running `POST /api/scan` printed: *"The `fitz` API is deprecated and
  will be removed in future. Use `import pymupdf` instead."*
- **What.** `python/extract/extract_metadata.py:38` does `import fitz`.
  That is the only `fitz` import in the codebase. Installed PyMuPDF is
  1.28.2; `requirements.txt` pins `PyMuPDF>=1.24` with no upper bound,
  so a fresh `pip install -r requirements.txt` after PyMuPDF drops the
  alias would install a version where this import fails.
- **Severity.** Not a boot failure — verified 2026-08-24 that neither
  `extract_metadata` nor `fitz` is imported at server boot (both absent
  from `sys.modules` after `import server`). It would fire the first
  time a user adds a PDF or hits Scan, i.e. the app opens fine and then
  cannot ingest anything.
- **Blocked on.** Nothing, but it wants care: swap to `import pymupdf`
  (optionally `import pymupdf as fitz` to avoid touching call sites),
  then re-run extraction against a real PDF and diff the output
  frontmatter to confirm the swap is behaviour-identical. Not done
  during onboarding because it is a runtime code change and the
  before/after comparison needs a real PDF fixture the repo doesn't
  have.
- **Touch-list sketch.** `python/extract/extract_metadata.py` (import),
  `requirements.txt` (consider an upper bound or a floor at the version
  that introduced `pymupdf`), new extraction smoke test if a fixture
  PDF gets added.

### `sys.exit()` inside a library module

- **Origin.** Found 2026-08-24 while investigating the `fitz` import.
- **What.** `python/extract/extract_metadata.py:37-39` wraps the import
  in `except ImportError: sys.exit("PyMuPDF not found. Run: ...")`.
  That is CLI behaviour in a module that `CONTRIBUTING.md` explicitly
  classifies as a library called from Flask endpoints ("No CLI scripts
  in Corpus"). It also prints a `pip install` instruction to a user who
  has no terminal — shipped users run a `.app`.
- **Severity.** UNKNOWN — not probed. `SystemExit` raised inside a
  Flask request thread was not tested, so how it surfaces to the user
  is unverified. Do not assume it degrades gracefully.
- **Blocked on.** Nothing. Should be resolved together with the `fitz`
  item above since it is the same three lines.
- **Touch-list sketch.** `python/extract/extract_metadata.py` — raise a
  normal exception (or let the ImportError propagate) so the endpoint's
  error handling reports it as a failed extraction instead of killing
  the thread.

---

### Add-to-project from the NOTE pane

- **Origin.** 2026-09-14, shipping the Projects tab. Membership was
  built project-side only. Jack asked for the paper half on 2026-09-21
  ("can you add a button somewhere in the paper view up here to add a
  paper to a project") and it shipped that day.
- **What is left.** The same entry point on the note detail pane. The
  work is a button plus one call — `window.ProjectMembership.openFor`
  already takes a kind, and `"note"` is already in
  `_PROJECT_MEMBER_KINDS`, so nothing new is needed on either side of
  the wire.
- **Why it is not done.** Jack asked for the paper pane specifically.
  Adding the note one unasked is scope he did not request; it is a
  two-line change whenever he wants it.
- **Touch-list sketch.** Wherever the note detail renders its header
  actions (`src/notes.js`), plus a row in `CODE_MAP.md`'s feature and
  log-signature tables. `tests/test_add_to_project_entry.py` is written
  against the paper pane and would want a sibling.

### Extract a shared picker shell

- **Origin.** 2026-09-14. `projects.js::_openMemberPicker` and
  `notes.js::_openEntityLinkPicker` are both "modal + filter box +
  scrollable list of rows from a MODES-backed list, returns a
  selection".
- **What is NOT duplicated.** How a row is labelled and identified —
  both call the same MODES `linkLabel` / `linkId` / `memberLabel`, held
  in place by `tests/test_project_member_kinds.py::
  test_the_picker_reuses_mode_labels_rather_than_copying_them`. The
  duplication is modal markup and filter wiring, roughly 40 lines.
- **Why it was not done inline.** The notes picker inserts into a saved
  DOM Range inside a contenteditable; the project picker calls an API.
  Unifying them means refactoring working entity-link code during a
  feature build, for a duplication that is markup rather than fact.
- **Blocked on.** Nothing. Do it when a third picker appears — that is
  the point at which the shared shape is actually known.
- **Touch-list sketch.** New `src/picker.js` (`Picker.open({title,
  rows, onPick})`), `src/notes.js`, `src/projects.js`, `index.html`
  script order, `CODE_MAP.md` shared-module list.

- **Partly done, 2026-09-21.** `src/projects.js` now has
  `_pickerShell` — overlay, filter box, list and dismissal — shared
  by both pickers inside that file. It was extracted when the
  paper-side project picker arrived, rather than writing a third
  copy of the modal markup. What REMAINS is `notes.js`'s entity-link
  picker, which is the awkward one: it takes a saved DOM Range and
  writes an `<a>` into a contenteditable body, so folding it in means
  the shell has to grow a concept of what a pick DOES beyond calling
  back. `tests/test_add_to_project_entry.py::test_both_pickers_go_through_one_shell`
  holds the projects.js half in place.

### Projects as note link targets

- **Origin.** 2026-09-14. Notes can deep-link to papers, authors,
  institutions and journals (MODES entries declaring `linkAttr`).
  Projects deliberately does NOT declare one.
- **Why not.** Adding `linkAttr: "project"` widens
  `window.LINK_ATTRS`, which must match `notes_api._NOTE_LINK_ATTRS`,
  which changes what the note HTML sanitizer preserves. That is a
  sanitizer change, and it was not asked for.
- **If done.** One MODES field, one entry in `_NOTE_LINK_ATTRS`, and
  `tests/test_note_link_attrs.py` keeps the two honest automatically.
  Note that project member rows do NOT use the `data-open-*`
  delegation (see `projects.js::_wireProjectDetail`) — that is about
  notes not being link targets, and is independent of this item.

### Oversized modules — measured, not split

- **Status.** Decided-pending-choice. Deliberately NOT done 2026-09-17.
- **Origin.** Jack, 2026-09-17: "can you do a refactor to future proof
  the code and optimize efficiency?" The efficiency half was measured
  and acted on (see CHANGELOG). This is the structural half.
- **What was measured.** Files over the 400-line smell threshold:

  | File | Lines |
  |---|---|
  | `src/app.js` | 1375 |
  | `src/notes.js` | 1352 |
  | `src/paper-detail.js` | 972 |
  | `python/extract/extract_metadata.py` | 919 |
  | `python/entities_api.py` | 662 |
  | `python/extract/prefill_summary.py` | 603 |
  | `python/extract/semanticscholar_client.py` | 425 |

- **Why it was not done.** The protocol allows a split only along a
  REAL responsibility boundary — each half's job stateable in one
  sentence without "and", a narrow one-directional interface, and the
  seam where change pressure diverges. Three of these have a plausible
  seam already recorded as expansion points 2, 3 and 4 below
  (`renderDetail` per-section renderers; the resolver ladder; the
  Source contract). The rest do not obviously have one, and splitting
  a file because it is long — with no next feature pushing on it — is
  how you get two incoherent halves and a week of merge pain for no
  behaviour change.
- **The honest position.** "Future-proof" is only meaningful against a
  concrete next change. Jack should name the next feature; the right
  seam usually follows from it. Until then these are recorded, not
  acted on.
- **What WAS done structurally.** The three independent ways of reading
  a summary (`list_papers`' own glob, `paper_detail`'s raw
  `read_text` + `parse_frontmatter`, and `_walk_summaries`) were
  consolidated into `summary_paths()` + `_read_summary()`. That one had
  a real boundary and a measured cost, and it is what made the caching
  possible at all.

### Citation bridges — depth 3, and background refresh

- **Status.** Expansion point. Depth 2 SHIPPED 2026-09-17 (see
  CHANGELOG); these are the pieces deliberately left out.
- **Origin.** Jack, 2026-09-17. He picked "depth 2, on-demand button"
  from four options after seeing the measured costs.
- **Depth 3.** Would catch chains depth 2 misses, via citers-of-citers
  (~65 more requests for a 56-paper corpus, so ~140 total). NOT built
  because a 3-hop chain links almost anything to anything — the signal
  gets weak fast, and 71 two-hop bridges against 22 direct links is
  already a lot of new surface to read. Revisit if depth 2 turns out
  to be too sparse in practice.
  * This is where Jack's year-pruning rule finally earns its keep. At
    depth 2 it is redundant (everything in `backward(B)` cites B, so it
    is newer by construction). At depth 3 the frontier must be pruned
    or it explodes: measured effective branching is 4.0 for a 2020
    target but 36.0 for a 2001 one.
- **Recompute on add.** SHIPPED 2026-09-17, reversing the 2026-09-14
  decision. It was declined because a silent ~43s network call hanging
  off Add PDFs is a bad trade — and Jack's follow-up asked for
  auto-search *and* visible progress in the same sentence, which
  removes the "silent" half. It now runs once per batch in a background
  thread, reporting into the import's own progress job. The `stale`
  flag is still there for corpora changed by other means.
- **Not surfaced yet.** The corpus-wide bridge list. `/api/bridges`
  returns all 71 rows but only the per-paper view is rendered. A
  "Connections" tab showing the whole bridge graph is the obvious next
  step, and pairs with the existing "Citation graph has no
  visualization" item below.
- **Touch-list sketch.** `python/bridges.py` (a `depth` parameter on
  `find_bridges`), `python/bridges_api.py` (fetch citers-of-citers,
  bump `BRIDGE_CACHE_VERSION`), `src/corpus-links.js` (group rows by
  hop count).

### `normalize_doi` does not collapse a double slash

- **Status.** Known limitation, deliberately NOT fixed 2026-09-17.
- **Origin.** Found while probing slug-collision handling for Jack. The
  import resolver now uses `normalize_doi`, which fixed same-paper
  detection for url-form and mixed-case DOIs — but
  `10.1037//0096-3445.130.1.59` and `10.1037/0096-3445.130.1.59` still
  compare unequal, so a re-import across those two forms forks a
  duplicate.
- **Why it was left alone.** Measured first: 8 DOIs across BOTH corpora
  contain `//` (1 in Corpus — `schunn-2001`; 7 in Paper Machine), and
  **none clash with a single-slash twin**. Theoretical today.
- **Why it is not a trivial fix.** `normalize_doi` is the single source
  of truth for the citation index, the reference matcher, bridges, and
  now import identity. A DOI suffix may legitimately contain slashes,
  so a general collapse risks merging two genuinely different DOIs
  across every one of those consumers — a worse failure than the
  duplicate it prevents.
- **If it becomes real.** Narrow it to the legacy APA pattern
  (`10.1037//` → `10.1037/`) rather than collapsing slashes generally,
  and add a test that two different DOIs differing only in slashes
  still compare unequal.
- **Touch-list sketch.** `python/extract/_api_http.py::normalize_doi`,
  `tests/test_citations.py`, `tests/test_slug_collision.py`.

### Bulk scans degrade PDF reading — loudly AND silently

- **Status.** Observed once, cause NOT established. Not fixed.
- **Origin.** 2026-09-18, importing 100 PDFs in one `/api/scan`. Three
  files failed with `pymupdf.FileDataError: Failed to open file ... as
  type pdf` (`mcloughlin-2024`, `meliss-2024`, `murphy-2024`), at
  11:04:30, 11:06:48 and 11:10:24 — spread through the run, not
  clustered.
- **Why it is not a bad-PDF problem.** All three open fine before and
  after (66, 27 and 21 pages, unencrypted), from both the source and
  the inbox copy, and the copies are byte-identical to the originals
  (same MD5). All three imported on an immediate retry with no change.
- **What is NOT known.** Why `fitz.open` failed at that moment. The
  spread-out timing argues against progressive resource exhaustion.
  One untested hypothesis: MuPDF thread-safety, since
  `_kick_enrichment` spawns a background thread after every paper —
  but nothing has been measured, and guessing at a fix here would be
  acting on a partially-understood problem.
- **Why it matters.** 39 batches remain. At 3-per-100 this is roughly
  30 more spurious failures across the migration.
- **Mitigation that already works for the LOUD case.** Per-file error
  handling is correct: the other 97 imported, the three stayed in the
  inbox, and re-running Scan picked them up.

- **THE SILENT CASE IS WORSE, and was missed in the first write-up of
  this entry (2026-09-18).** Three OTHER papers from the same scan —
  `mayer-2024`, `mccoy-2024`, `mooraj-2024`, written at 11:02:40,
  11:04:17 and 11:07:48, interleaved with the three hard failures —
  imported "successfully" with EVERY field `unknown`: no author, year,
  title, publisher, DOI or source_url. `status: prefilled`. They were
  reported as `extracted` and are indistinguishable from a real import
  in the scan response.
- **Same evidence pattern as the loud case.** All three PDFs yield
  their correct DOI when read in isolation afterwards (9083, 18654 and
  13292 characters of text; expected DOI present in every one). All
  three repaired cleanly via `/api/paper/<slug>/re-extract`. The files
  are fine; the bulk-scan conditions were not.
- **So the real rate is 6 in 100, not 3.** Three fail loudly and stay
  in the inbox for retry; three fail silently and land as empty
  records that look imported. Across the remaining 975 papers that is
  roughly 30 loud and 30 silent.
- **Why the silent one matters more.** A paper with no title, year or
  DOI cannot be found by search, cannot be linked by the citation
  index, cannot be bridged, and shows in the sidebar as "unknown". It
  is invisible damage — the count of imported papers is right.
- **Detection, until the cause is found.** `corpus_migration/
  stage_batch.py --audit` lists papers whose metadata is entirely
  unknown. Run it after every batch. A paper with a text layer that
  produced nothing is anomalous; a scanned image (`catrambone-1995`)
  legitimately produces nothing, so the check reports rather than
  assumes.
- **To investigate.** Re-run a 100-file scan with `_kick_enrichment`
  disabled and see whether both symptoms vanish. That isolates the
  thread hypothesis without changing behaviour. Both symptoms should
  be measured together — they appeared in the same window and are
  probably one fault.

### Preprint DOIs win over the published version

- **Status.** Known behaviour, no decision yet.
- **Origin.** 2026-09-18, in the same 100-paper import. Two papers
  resolved to their preprint record rather than the journal one:
  `geerts-2024` landed as `geerts-2022` with the bioRxiv DOI
  `10.1101/2022.06.03.494671` (Paper Machine has
  `10.1037/rev0000414`, APA 2024), and `holroyd-2023` took the
  PsyArXiv DOI `10.31234/osf.io/2qmhg` over `10.1037/rev0000467`.
- **Why it happens.** The DOI printed on a preprint PDF is the
  preprint's. Corpus extracts what the document says, which is
  correct behaviour for the document it was given — the user simply
  has the preprint file.
- **Why it matters.** Preprint and published versions have different
  DOIs, so citations to the published version do not link to a corpus
  holding the preprint. It silently weakens the citation graph and
  bridges.
- **Possible directions, none chosen.** Crossref's `relation`
  /`is-preprint-of` field can map preprint to published DOI; OpenAlex
  groups both under one work. Either could surface "this is the
  preprint; the published version is X" rather than silently
  preferring one.
- **Scale, measured.** 2 of 100 in this batch. Unknown across the
  remaining 1008.

### Stored citers → bridge search — SHIPPED 2026-09-23

- Read stored citers first, fall back to `openalex_citers_of` only for
  papers with nothing complete stored. See CHANGELOG 2026-09-23 and
  CODE_MAP "Citation bridges".
- Two consequences worth remembering: the bridge search is now as fresh
  as the citer store (a paper cited since its fetch is invisible until
  refetched), and papers with more than 2,000 citers are no longer
  truncated — the old fetch capped there, the store does not, so bridge
  counts went UP as well as getting faster.
- Still open from this item: **no button for the corpus-wide citer
  fetch.** `POST /api/citers/fetch-all` exists and is resumable, but
  nothing in the UI calls it. It is now also the way to refresh bridge
  freshness, which makes the button more useful than when it was first
  deferred. Touch-list: `src/settings.js` (or wherever Settings actions
  live), `CODE_MAP.md` user-action table.

### `/api/papers` reads 5.4 MB to show a list that needs 0.5 MB

- **Status.** Measured, NOT done. Recorded 2026-09-20. **Worse now:**
  2026-09-21, ~620 summaries, a cold `/api/papers` after a restart took
  218-251s (three concurrent requests, each reading every file). The
  concurrency part is fixed — misses now share one read via
  `_api_common._READ_LOCK` — so a single cold load is the remaining cost.
- **Likely root cause, verified in part.** `~/Documents` carries a
  `com.apple.file-provider-domain-id` xattr — it is iCloud-synced
  ("Desktop & Documents"). Files there can be evicted to dataless stubs
  and are fetched on first read, which matches the ~95ms/file cold read
  measured 2026-09-20 and the restart-only slowness. NOT verified: that
  individual summaries are actually dataless at the time. The cheapest
  test is Jack's call, not a code change: move the corpus out of
  Documents (e.g. `~/Corpus`) via Settings and time a cold start.
- **Origin.** Diagnosing "it forgot my corpus location". Boot on a cold
  209-summary corpus took ~20s; the message was the reported bug and is
  fixed, but the 20s is real.
- **Measured.** 209 summaries, 5.4 MB total. Warm: read 0.04s, parse
  0.08s. COLD: 19.86s — about 95ms per file, which is per-file latency
  rather than bandwidth. Parsing is not the cost (0.9ms typical, 4.6ms
  on the 255 KB outlier); the cost is the first read of each file.
- **The waste.** `/api/papers` uses `_fm_dict`, which needs ONLY the
  frontmatter — the first few KB. The References section is the bulk of
  every file (mean 27 KB, largest 255 KB) and is read, decoded and
  discarded on every cold boot.
- **The shape of the fix.** A frontmatter-only read that stops at the
  closing `---`. Roughly 5.4 MB -> 0.5 MB, which on this machine's cold
  behaviour is the difference between ~20s and ~2s.
- **Why it was not done now.** `_read_summary` caches `(fm, body)` as
  one unit, and a head-only read means either a second cache shape or
  a re-read when the body is later wanted. That is real surgery on a
  cache with 13 tests and careful invalidation, for a path that is
  slow only on the first request after a cold start. The reported bug
  did not require it.
- **Environmental caveat, unexplained.** 95ms per first-read is very
  slow for an internal SSD. Not iCloud (checked: `~/Documents` is a
  real local dir, no placeholders, no dataless flags). The disk is 96%
  full (19 GB free of 460 GB), which may or may not be related — not
  established, and not something Corpus can fix.
- **Touch-list sketch.** `python/_api_common.py` (`_read_summary`
  gains a `need_body` path plus a cache entry that records which it
  holds), `tests/test_caching.py` (a head-only entry must be upgraded,
  not served, when the body is wanted).

### Fullscreen note workspace — follow-ups

- **Status.** All four parts SHIPPED 2026-09-21 (see CHANGELOG). These
  are the edges left open.
- **The panel's Info view is the full paper view — SHIPPED 2026-09-25**
  after Jack's bug report ("i should be able to see all the paper info
  here"). `renderPaperInto(host, d, opts)` is the one renderer; see
  CHANGELOG. Left out of the panel on purpose: Re-extract and Add to
  project (both re-select the paper in the main pane, which a note
  window does not show). If Jack wants them there, they need a
  panel-aware refresh like `opts.reload`.
- **The paper lock is pywebview-only.** In the browser dev fallback there
  is no launcher to arbitrate, so `_claim` answers "ok". Harmless for
  users (they always run under pywebview) but worth knowing when testing
  in a browser tab.
- **Panel width is fixed at 50/50.** No drag-to-resize. A `#nw-split`
  element exists in the markup as the handle's future home; nothing is
  wired to it yet.
- **One paper at a time in the panel.** Jack's wording was "the pdfs
  (if any) tagged in this note", plural — a list or tab strip of every
  paper the note links to would match that better than
  click-a-link-to-swap. Swapping was built first because it is what the
  rest of the sentence describes ("when you click on a link to a paper
  … it makes that paper be in view for the panel").
- **No ready message on the viewer bridge.** Both scroll paths retry
  for a few hundred ms while PDF.js opens the document. A real
  `viewer-ready` message would be cleaner, but it is a new contract on
  a bridge shared by the docked pane, and retrying is cheap.
- **Highlight links are not listed anywhere.** There is no "which notes
  point at this highlight" view; deleting a highlight leaves the link
  degrading to a plain paper link, silently.
- **Untested in a real window.** Every assertion is source-level or
  sanitizer-level — no browser here. The split layout, the pick
  interaction and the scroll have not been seen working.

## Decided-pending-choice

Items where the direction is agreed but a design choice is still open.

*(none currently — all Wave 3 items below are structural, no open choice)*

---

### Replace the text sidecar with the `paperclean` extractor

- **Status.** In evaluation (updated 2026-09-21, later the same day).
  Jack asked for it inside Corpus as a DEV-ONLY testing feature, not as
  the production sidecar. It now lives at `python/dev_only/paperclean/`
  (stripped from ship) behind the dev Testing tab, which shows live
  extracted text beside each test-set PDF. Production still uses the
  old sidecar — the swap below remains blocked.
- **Earlier status.** Blocked, by Jack's own instruction (2026-09-21):
  "dont integrate this into corpus yet. we need to make sure it works
  first." Parked the same day.
- **Origin.** Jack, 2026-09-21: "i want you to work on using the python
  tools that exist to make a custom text extractor specifically for
  research papers … the goal is to have cleanly formatted text that can
  be read in order to get through the paper." Built and tested OUTSIDE
  this repo on purpose, so Corpus was never touched.
- **Where it is.** `python/dev_only/paperclean/` — package, `README.md`
  (design), `metrics.py` (retention / mid-paragraph, one definition
  shared with the Testing tab), `test_set.json` (the evaluated papers,
  each with a note on what it tests). Tests: `tests/test_paperclean.py`.
  The original prototype in `../../text_extractor/` (Paper Machine) is
  now a stale copy and should be deleted once Jack confirms; its
  `ROADMAP.md` handoff notes are superseded by this entry.
- **What it does that `get_text()` does not.** Two-column reading order
  with a document-level gutter, running heads and download stamps
  removed, figure axis labels and panel letters separated from prose by
  a typographic + function-word test, evidence-based de-hyphenation,
  drop caps, captions, equations, reference lists, and paragraphs
  stitched across columns, pages and captions. Measured 76–100%
  retention on 13 papers from Jack's corpus; the low end is a review
  whose four data tables are dropped deliberately.
- **Blocked on.** Two things, in order: (1) the tables decision
  (reconstruct rows, or keep the current `[N blocks … omitted]`
  marker); (2) Jack's go-ahead that it works well enough to swap in.
- **Touch-list sketch.** The sidecar is written by
  `python/extract/prefill_summary.py` — that is the call site, and the
  only one. The package imports no Flask and no Corpus module, so
  graduating it means moving `python/dev_only/paperclean/` to
  `python/extract/paperclean/` and updating the test imports.
  `requirements.txt` needs nothing new (PyMuPDF is already a
  dependency). `CODE_MAP.md` needs a feature row; `TESTING.md`
  needs the new test file. Note this CHANGES STORED DATA for every
  paper already in the corpus — a re-extract of 259 summaries — so it
  wants a CHANGELOG entry saying so.

### 65 Paper Machine papers fell out of the migration manifest

- **Status.** Decided-pending-choice. Recorded 2026-09-21, not fixed.
- **Origin.** Found while checking whether fifteen phase-structured
  learning papers were already in Corpus: four of them
  (`ackerman-1988`, `cohen-1980`, `karni-1991`, `knowlton-1994`) were
  in neither `batches.json` nor `DEFERRED.md`, so nothing would ever
  have imported them and nothing recorded why.
- **Cause.** The manifest builder kept `article`/`preprint`/
  `proceedings` and dropped `book`/`chapter`/`report`/`thesis`. As a
  KEEP-list, a summary with no `kind:` line matched neither side and
  was dropped as non-standard. Of the 216 reported dropped at that
  step, 154 were genuinely non-standard and 62 were never classified.
- **Blocked on.** Triage. The 65 are a MIXTURE — mostly journal
  articles, but at least `vygotsky-1978` is a book and out of scope
  under the original rule. Batching them wholesale would import books
  Jack explicitly excluded.
- **Where the list is.** `../../corpus_migration/DEFERRED.md`, last
  section, one row per paper with its DOI and its (missing) kind.
  `../../corpus_migration/README.md` carries the correction in its
  selection table so the row counts are not read as accurate.
- **Touch-list sketch.** Triage the 65 by hand into article vs book;
  append the articles to `batches.json` as batches 46+ (append only —
  renumbering would break `--status` against work already done); leave
  the rest in DEFERRED with a reason.

### OpenAlex rate-limits every bulk import — 355 failures in one hour

- **Status.** Mostly FIXED 2026-09-22; one item left (429 backoff).
- **Evidence.** `~/.corpus/logs/server.log` carries 355
  `api_get_json failed … reason=Too Many Requests` lines against
  `api.openalex.org` between 12:59 and 13:56 on 2026-09-21, spanning a
  100-paper and a 107-paper import. 373 in the log overall.
- **Why it matters.** These are silent. A 429 costs a paper its
  OpenAlex metadata and drops it from the bridge graph, and the import
  still reports success.
- **Fixed 2026-09-22.** Two causes, both closed: the saved OpenAlex API
  key was never sent (exported as `CORPUS_OPENALEX_KEY`, read by
  nothing), and `mailto` only reached the User-Agent — while Jack's
  config had none set at all, and `oa_enrichment.py` hard-coded a fake
  `mailto=x`. `_api_http.with_openalex_auth` now adds `api_key` and
  `mailto` to every OpenAlex request, in the single function all six
  call sites pass through; logs name the un-keyed URL. Jack set a mailto
  the same day. Pinned by `tests/test_openalex_auth.py`.
- **Not yet verified live.** Whether 429s actually stop needs an import
  run on the restarted app: `grep -c "Too Many Requests"` on server.log
  before and after.
- **Left.** A retry with backoff on 429 specifically — distinct from the
  one blind retry `openalex_works_by` does per chunk. Only worth building
  if the live check still shows 429s.

### Duplicate-DOI cleanup surface

- **Origin.** Surfaced by the citation index, 2026-08-25. Jack's corpus
  has one case: `865.full` and `ashby-2022` both carry
  `10.1523/jneurosci.1396-21.2021` — the same paper imported twice, once
  under a publisher's raw download name.
- **What.** `/api/citations` reports `duplicate_dois`, but no UI shows
  it and nothing offers to merge or delete. Duplicates inflate link
  counts (both slugs get their own edges) and will distort any
  centrality measure computed from the graph later.
- **Blocked on.** A decision from Jack about what "resolve" means —
  delete one summary, merge highlights/notes across them, or just flag.
  Deleting a summary is destructive, so this should not be built on an
  assumption.
- **Touch-list sketch.** Somewhere in the UI to surface
  `duplicate_dois` (a Warnings surface does not exist yet); whatever
  merge/delete action is decided; `citations.py` is already correct and
  needs no change.

### Citation graph has no visualization

- **Origin.** Implied by Jack's 2026-08-25 framing: "that connection
  can be accessed later for connection analysis purposes." Part 1
  built the data substrate only.
- **What.** `/api/citations` returns nodes + directed edges + degree
  counts, which is what a force-directed graph needs. Nothing renders
  it. Per-paper links are visible in the paper detail pane; the
  corpus-wide picture is API-only.
- **Blocked on.** Nothing technical. Awaiting Jack — he has not asked
  for a visualization yet, and building an unrequested one is
  speculation.
- **Touch-list sketch.** A new tab or a view in the papers pane; a
  force-directed renderer; `index.html` + `app.js` MODES entry if it
  becomes a tab. The endpoint needs no change.

---

## Expansion points

Places the codebase should be reshaped so the next feature is one-file
work instead of many-file work. Ranked roughly by "how much would this
hurt the next feature I add" (per `CODE_MAP.md` audit rationale).

### 1. Coverage rows shape — enable adding a 4th enrichment source cheaply

- **Origin.** `CODE_MAP.md` "Wave 2" refactor candidate. Still open
  2026-08-24 (verified: `provenance.js` still uses positional-tuple
  `inSource` helpers).
- **What.** Coverage rows in the detail modules are positional 5-tuples
  `[label, cr, ss, oa, ttKey]` — assumes exactly 3 sources. Switch to
  `{label, tt, sources: {C, SS, OA}}` + separate `COVERAGE_COLUMNS`
  list. Adding Scopus / PubMed / arXiv becomes one entry.
- **Blocked on.** Nothing. Just needs Jack's go.
- **Touch-list sketch.** `src/provenance.js` (rewrite rows structure),
  `src/author-detail.js` / `institution-detail.js` / `journal-detail.js`
  (change rows literal), `src/paper-detail.js` (same), `tests/src/provenance.test.js`
  (rewrite assertions). Behavior-preserving; snapshot output unchanged.

### 2. Resolver ladder — extract-metadata orchestrator as a list

- **Origin.** `CODE_MAP.md` "Wave 3". Blocks any new metadata source
  (arXiv, OpenReview, DataCite).
- **What.** `python/extract/extract_metadata.py::extract_metadata` hardcodes
  4 stages (PDF-info DOI → text-scan DOI → title-search → slug) with
  `if not api_hit:` gates. Rewrite as
  `[PdfInfoDoiResolver(), TextScanDoiResolver(), CrossrefTitleSearchResolver(), ...]`.
  Adding a source = appending one entry.
- **Blocked on.** Item 3 below (Source contract) is a prerequisite for
  extracting the resolver interface cleanly.
- **Touch-list sketch.** `python/extract/extract_metadata.py` (rewrite
  orchestrator), each `*_client.py` (implement common interface), new
  `tests/test_resolver_ladder.py` asserting each resolver runs in
  isolation.

### 3. Source contract — Source dataclass with authoritative_for / verifies

- **Origin.** `CODE_MAP.md` "Wave 3". Same trigger as item 2.
- **What.** Clients (`crossref_client`, `openalex_client`,
  `semanticscholar_client`) currently return flat dicts; precedence is
  hardcoded in `_merge_api_meta`; `PROVENANCE_FIELDS` is a hand-maintained
  55-entry tuple. Introduce a `Source` dataclass with `authoritative_for` /
  `verifies` sets. Precedence becomes derived, not hardcoded.
- **Blocked on.** Waiting until a 4th source is actually being added —
  refactoring three sources into a shape that assumes N is guessing at
  where the seams should be.
- **Touch-list sketch.** New `python/extract/_source.py` (dataclass),
  each `*_client.py` (return `Source` instances), rewrite
  `extract_metadata::merge_with_provenance`, delete `PROVENANCE_FIELDS`
  hand-list, extend `tests/test_metadata.py`.

### 4. `renderDetail` split — per-section renderers

- **Origin.** `CODE_MAP.md` "Wave 2". Verified 2026-08-24: `renderDetail`
  starts at `src/paper-detail.js:30` in a 981-line file — the function
  itself is the file.
- **What.** Break into per-section renderers (header, meta grid, authors
  block, TL;DR, abstract, sources coverage, references). Composes well
  with `EntityDetail.render` skeleton already used by author / institution
  / journal panes.
- **Blocked on.** Nothing. Purely for maintainability; user-visible
  behavior stays identical.
- **Touch-list sketch.** `src/paper-detail.js` (split file), possibly
  new `src/paper-detail-sections.js`, no server-side changes,
  `tests/test_script_load_order.py` if load order changes.

### Dormant URL-link path in the notes toolbar

- **Origin.** Found 2026-08-27 while adding entity links.
- **What.** `src/notes.js` has a `data-link` toolbar branch that
  prompts for a URL and runs `execCommand("createLink")`, but no
  `_NOTE_TOOLBAR` entry sets `isLink`, so no button reaches it. It is
  one array entry away from working.
- **Decision needed.** Either surface it (a plain-URL link button
  beside the new entity-link button) or delete it. It was deliberately
  left untouched when entity links landed — silently shipping an
  unrequested feature and silently deleting a latent one are both
  worse than asking.
- **Note.** `<a href>` already survives the sanitiser, and the
  javascript:/data: guard already covers it, so surfacing it needs no
  sanitiser work.
- **Touch-list sketch.** `src/notes.js` (`_NOTE_TOOLBAR` entry, or
  remove the branch), `tests/test_note_sanitizer.py` if surfaced.

### 5. Vanilla-JS module contract — `window.Corpus` namespace

- **Origin.** `CODE_MAP.md` "Wave 3". Verified 2026-08-24: `src/app.js`
  writes 6 raw `window.X` globals; zero `window.Corpus` uses.
- **What.** Modules communicate via implicit `window` globals; the
  script-load-order test is the only thing enforcing correctness.
  Adopt `window.Corpus = {}` namespace with
  `Corpus.PaperDetail.render()` etc. Makes cross-module dependencies
  explicit + greppable.
- **Blocked on.** Nothing. Mechanical rewrite.
- **Touch-list sketch.** Every `src/*.js` (assign to `Corpus.<Ns>` +
  read from `Corpus.<Ns>`), `tests/src/harness.js` (populate
  `Corpus` namespace stub), `tests/src/*.test.js` (adjust imports),
  `tests/test_script_load_order.py` (assertions may relax).

---

## Ideas

Lightly-scoped, not yet committed. Fair game to drop.

*(none currently — Jack's ideas typically land as bug reports first
and get promoted here after triage)*

---

## Roadmap policy

- Add entries the moment work is deferred / descoped / planned in
  discussion — never wait for a follow-up prompt.
- Every entry: status heading + origin + what + blocked-on + touch-list
  sketch. If any of these is empty, say so explicitly.
- On "how is Corpus looking?"-type questions, report from this file
  AND reconcile against the code (anything mentioned in conversation
  but missing from both is a tracking failure to fix on the spot).
- Delete entries when Jack drops the idea. A roadmap full of dead
  items stops being read.
