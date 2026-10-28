# Corpus

A desktop app for keeping a library of research papers. You add PDFs;
Corpus reads each one, finds its metadata and reference list, and gives
you a searchable library with a PDF reader, highlights, notes, and the
citation links between your papers. It runs on your own computer: no
account, no cloud service, no AI-written summaries.

Corpus © 2026 Jack Mostyn. Licensed under the GNU Affero General Public
License v3.0 — see [LICENSE](LICENSE). Third-party components and their
licences are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## What it does

- **Reads your PDFs**: DOI, title, authors, year, journal, pages,
  affiliations where printed, and the full reference list.
- **Fills gaps from public databases** when online: Crossref (no key
  needed), OpenAlex and Semantic Scholar (optional keys, in Settings).
- **A library**: papers, authors, institutions and journals, with sort
  and filter.
- **Reading**: a PDF viewer with highlights and notes anchored to them,
  a rich-text Notes tab, and a pop-out reading window.
- **Connections**: which of your papers cite each other, and who else
  cites them.

Your library is a folder you choose: the PDFs, plus one Markdown file
per paper.

## Download

Get the latest version from the [Releases](../../releases) page.

**Mac** — download `Corpus-v<version>.zip`, unzip it, and drag
`Corpus.app` into Applications. The first time you open it, macOS will
block it because it is not signed by Apple: open **System Settings →
Privacy & Security**, scroll to the message about Corpus, and click
**Open Anyway**. After that it opens normally. On first launch Corpus
asks where to keep your papers.

**Windows** — download `Corpus-v<version>-windows.zip` and unzip it.
Open the `Corpus` folder and run `Corpus.exe`. Keep the whole folder
together: the `.exe` needs the `_internal` folder next to it. Windows
may warn that the app is unrecognised because it is not signed: click
**More info → Run anyway**. On first launch Corpus asks where to keep
your papers.

## Run from source

Needs Python 3.11+.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python launcher.py
```

Tests: `.venv/bin/python -m pytest tests/ -q` (and
`node --test tests/src/*.test.js` for the frontend).

To build the Windows app yourself, run `build_windows.bat` on Windows
(it needs Python 3.11+ from python.org); the app appears in
`dist\Corpus\`.

## Reporting problems

Open an issue on this repository with what you did, what you expected,
and what happened instead. Screenshots help.

## For developers

The code is plain Python (Flask) behind a native window (pywebview), and
a vanilla-JavaScript frontend with no build step. `CODE_MAP.md` maps
every feature to its files; `CONTRIBUTING.md` lists what a change must
update; `TESTING.md` says what each test covers.
