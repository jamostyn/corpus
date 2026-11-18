# Changelog

What changed for users in each release. Downloads are on the
[Releases page](https://github.com/jamostyn/corpus/releases).

## 0.4.5 — 2026-11-18

Mac only for now; the Windows download stays 0.4.2.

- Notes: linking a paper inserts its slug (e.g. `pan-2025-1`) instead of
  its title; the picker still lists papers by title.
- Notes: a highlight link says the paper's slug and the highlight's page
  (`pan-2025-1, p. 4`) instead of the highlighted text.
- Note tables can be wider than the note: drag the right edge past the
  edge and the note scrolls along.
- Back now goes back on the first press after opening a tab or following
  a link (it used to need two).
- Notes (experimental): `Shared citers` lists works citing two or more
  of the papers a note links — in your library or not — from the
  citer lists already stored, each with its citation count (OpenAlex).
- Import picks the paper's own DOI when the first page also prints the
  DOI of a paper it cites.
- SSRN papers are identified from the SSRN link printed on them.
- A title broken across lines at a hyphen is read as one title.

## 0.4.4 — 2026-10-30

Mac only for now; the Windows download stays 0.4.2 until a 0.4.4
Windows build is made.

- Dark mode: Settings → Appearance (Match system, Light or Dark).
- Cite: each paper shows its citation in APA 7, MLA 9, Chicago
  (author-date), Harvard, Vancouver or IEEE, with Copy buttons; a project
  can export all its references.
- The top tabs are grouped, and never wrap.
- Paper info sections start collapsed; the abstract stays open.
- Lists open sorted by date added, newest first.
- "Pop out" is now "Open in new window"; on macOS these are always
  separate windows, never tabs.
- In a note opened in its own window, drag the divider between the note
  and the PDF.
- Note tables: dragging the right edge resizes the last column.
- Settings explain what each setting does.
- Windows: if Corpus cannot open its own window and opens in the browser
  instead, the page says why, with a link to install WebView2 when that
  is the cause. Corpus also clears Windows' "downloaded from the
  internet" block on its own files, a common reason the window fails.
- Title search checks that the paper it finds is by an author printed on
  the PDF, so it no longer imports a different paper with a similar
  title.
- arXiv preprints are found by the arXiv id printed on them.
- Authors listed as "Surname, Given" keep their surname (one arXiv
  paper had been filed under its first author's given name).
- Older Elsevier papers that print only a PII are identified by it.

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
