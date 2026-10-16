import assert from "node:assert/strict";
import { test } from "node:test";
import { parseCsv } from "./documentFormats.js";

test("CSV preview parser handles quoted commas, escaped quotes, newlines, and empty cells", () => {
  const parsed = parseCsv('\uFEFFName,Notes,Empty\r\n"Doe, Jane","line one\nline two",\r\n"A ""quoted"" value",ok,');
  assert.deepEqual(parsed.rows, [
    ["Name", "Notes", "Empty"],
    ["Doe, Jane", "line one\nline two", ""],
    ['A "quoted" value', "ok", ""],
  ]);
  assert.equal(parsed.truncated, false);
});

test("CSV preview parser caps rows for large files", () => {
  const parsed = parseCsv("a\n1\n2\n3\n", 3);
  assert.deepEqual(parsed.rows, [["a"], ["1"], ["2"]]);
  assert.equal(parsed.truncated, true);
});
