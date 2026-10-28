# Contributing

Bug reports and suggestions are welcome as issues. For a code change,
please open an issue first so we can agree on the approach before you
spend time on it.

## Set up

Needs Python 3.11+ and, for the frontend tests, Node 18+.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python launcher.py          # run the app
.venv/bin/python -m pytest tests/ -q  # Python tests
node --test tests/src/*.test.js       # frontend tests
```

Tests never touch your own library: every test works in a temporary
folder, and none contacts Crossref, OpenAlex or Semantic Scholar.

## Where things are

| Path | What it is |
|---|---|
| `launcher.py` | Starts the local server and opens the window (pywebview) |
| `python/server.py` | The Flask app; each `*_api.py` beside it is one group of routes |
| `python/extract/` | Reading a PDF: metadata, references, the summary file format |
| `python/citations.py`, `bridges.py`, `citers.py` | Citation links between papers |
| `src/` | The frontend: plain JavaScript, no build step; `index.html` loads it |
| `src/vendor/pdfjs/` | Mozilla's PDF.js (only `web/corpus-highlights.*` is ours) |
| `tests/` | pytest suite; `tests/src/` holds the Node frontend tests |
| `pyinstaller_corpus.spec`, `build_ship.py`, `build_windows.bat` | Building the Mac and Windows apps |

Each paper is one Markdown file with YAML frontmatter in the library's
`summaries/` folder. The writer is
`python/extract/prefill_summary.py::render_frontmatter`; the reader is
`python/extract/_fm.py::parse_frontmatter`. Change both together.

## What a change should include

- **A test** for the behaviour, whose docstring names the mistake it
  catches. When two files must agree (a field list, a key format), add a
  test that checks they do.
- **No second copy of a fact.** If a label, list or constant already
  lives somewhere, use it from there.
- **Features are buttons.** Corpus is a desktop app; nothing a user
  needs should require running a script.

The development history of this project is kept in a separate private
repository; this repository receives the source of each release and
updates between releases.
