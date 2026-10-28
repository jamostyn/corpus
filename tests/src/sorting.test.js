// The shared sort behind the Papers sidebar and the note link picker.
//
// Jack, 2026-09-28: "when i link a paper to a note, i want to be able to
// change what is being sorted by for all the options. so i can sort by
// most recent added papers for example."

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { loadInVM } = require("./harness");

const { Sorting } = loadInVM(["sorting.js"]);

const PAPER_SORTS = [
  { key: "author",   label: "Author",     value: (r) => r.author },
  { key: "year",     label: "Year",       value: (r) => r.year, numeric: true },
  { key: "added_at", label: "Date added", value: (r) => r.added_at, defaultDir: "desc" },
];
const ids = (rows) => rows.map(r => r.id);

test("date added, newest first — the case Jack asked for", () => {
  // Catches the direction being ignored or the dates compared wrongly.
  const rows = [
    { id: "old", added_at: "2026-08-01T10:00:00" },
    { id: "new", added_at: "2026-09-28T09:00:00" },
    { id: "mid", added_at: "2026-09-10T12:00:00" },
  ];
  assert.deepEqual(ids(Sorting.sortRows(PAPER_SORTS, rows, "added_at", "desc")), ["new", "mid", "old"]);
  assert.equal(Sorting.defaultDir(PAPER_SORTS, "added_at"), "desc");
});

test("years sort as numbers, not text", () => {
  // Catches string comparison: "999" > "2010" as text.
  const rows = [{ id: "a", year: "2010" }, { id: "b", year: "999" }, { id: "c", year: "2007" }];
  assert.deepEqual(ids(Sorting.sortRows(PAPER_SORTS, rows, "year", "asc")), ["b", "c", "a"]);
});

test("rows without a value go last in BOTH directions", () => {
  // Catches an undated or "unknown" paper leading a newest-first list —
  // blank strings sort before everything in a plain comparison.
  const rows = [
    { id: "blank", added_at: "" }, { id: "x", added_at: "2026-09-01" },
    { id: "unk", author: "unknown" }, { id: "y", added_at: "2026-09-02" },
  ];
  assert.deepEqual(ids(Sorting.sortRows(PAPER_SORTS, rows, "added_at", "desc")).slice(0, 2), ["y", "x"]);
  const byAuthor = [{ id: "unk", author: "unknown" }, { id: "b", author: "Bjork" }, { id: "a", author: "Ashby" }];
  assert.deepEqual(ids(Sorting.sortRows(PAPER_SORTS, byAuthor, "author", "asc")), ["a", "b", "unk"]);
  assert.deepEqual(ids(Sorting.sortRows(PAPER_SORTS, byAuthor, "author", "desc")), ["b", "a", "unk"]);
});

test("sorting never changes the list it was given", () => {
  // Catches an in-place sort reordering state.papers itself, which the
  // sidebar re-sorts from on every filter keystroke.
  const rows = [{ id: "b", author: "B" }, { id: "a", author: "A" }];
  Sorting.sortRows(PAPER_SORTS, rows, "author", "asc");
  assert.deepEqual(ids(rows), ["b", "a"]);
});
