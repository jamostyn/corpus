// app.js defaultSort: newest-added first wherever a list can sort.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { loadInVM } = require("./harness");

const APP = fs.readFileSync(path.join(__dirname, "..", "..", "src", "app.js"), "utf8");
const start = APP.indexOf("const DEFAULT_SORT_KEY");
const end = APP.indexOf("state.papersSort = ", start);

function load() {
  const sb = loadInVM(["sorting.js"]);
  vm.runInContext(APP.slice(start, end) + "\nthis.defaultSort = defaultSort;", sb);
  return sb.defaultSort;
}

test("a list with Date added opens newest first", () => {
  // Catches the default falling back to the first sort (Author A→Z).
  const d = load();
  const sorts = [{ key: "author" }, { key: "added_at", defaultDir: "desc" }];
  assert.deepEqual({ ...d({ sorts }) }, { key: "added_at", dir: "desc" });
});

test("a list without Date added keeps its first sort", () => {
  // Catches an undefined sort key for lists that have no date.
  const d = load();
  assert.equal(d({ sorts: [{ key: "name" }] }).key, "name");
  assert.equal(d({}).key, undefined);
});
