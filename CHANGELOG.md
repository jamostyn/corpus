# Changelog

What changed for users in each release. Downloads are on the
[Releases page](https://github.com/jamostyn/corpus/releases).

## 0.4.3 — 2026-10-28

Mac only for now; the Windows download stays 0.4.2 until a 0.4.3
Windows build is made.

- The app includes its licence and third-party notices.
- Requests to Crossref, OpenAlex and Semantic Scholar carry the real
  Corpus version.

## 0.4.2 — 2026-10-15

- Windows: the PDF viewer works. Earlier Windows builds were missing two
  pdf.js files, so the viewer never started.

## 0.4.1 — 2026-10-01

- Windows: the PDF viewer no longer shows a black page when the system
  registry maps script files to the wrong type, and says why if the
  viewer still fails to start.
- Pickers list papers added after the window opened.
- A popped-out note opens where you were reading.
- Deleting a note moved into the note's Settings menu.

## 0.4.0 — 2026-09-29

- **Documents:** read, search, highlight and annotate PDFs that are not
  papers (book chapters, handouts). No online lookups for them.
- **Note workspace:** pop a note out with a PDF panel beside it; links
  in a note can point at a single highlight.
- Link pickers sort by any field.
- Each paper's citing papers are fetched on import and stored.
- A note edited in one window can no longer be overwritten by another.
- Note revisions.

## 0.3.0 — 2026-09-18

- **Projects:** group papers and notes without moving any files.
- **Citation bridges:** papers with no direct citation between them are
  shown linked through a paper outside your library.
- Long jobs show their progress.
- Lists stay fast on large libraries.

## 0.2.0 — 2026-09-01

- Windows: first Windows build, from the same source as the Mac app.

## 0.1.1 — 2026-08-19

- Note Mode: notes anchored to highlights, beside the PDF.
- Papers can be popped out into their own window.

## 0.1.0 — 2026-08-18

- First version: add PDFs, get each paper's metadata and reference list,
  a searchable library, and a PDF reader with highlights.
