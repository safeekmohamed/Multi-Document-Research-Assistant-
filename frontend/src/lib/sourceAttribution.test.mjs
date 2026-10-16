import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const {
  deduplicateCitations,
  deduplicateSearchedFiles,
  filterRelevantCitations,
} = await import("./citations.js");

test("searched documents deduplicate searched files while only cited evidence is shown as used", () => {
  const files = deduplicateSearchedFiles([
    { source_id: "safeek", filename: "Safeek Resume.pdf" },
    { source_id: "safeek", filename: "Safeek Resume.pdf" },
    { source_id: "anil", filename: "Anil Resume.pdf" },
  ]);
  assert.deepEqual(files.map((file) => file.filename), [
    "Safeek Resume.pdf",
    "Anil Resume.pdf",
  ]);

  const citations = filterRelevantCitations([{
    source_id: "safeek",
    filename: "Safeek Resume.pdf",
    source_type: "file",
    page: 2,
  }]);
  assert.deepEqual(citations.map(({ filename }) => filename), ["Safeek Resume.pdf"]);
});

test("answer citation display retains every backend-selected source and its page", () => {
  const citations = filterRelevantCitations([
    {
      source_id: "safeek",
      filename: "Safeek Resume.pdf",
      source_type: "file",
      relevance: 0.35,
      pages: [2],
    },
    {
      source_id: "anil",
      filename: "Anil Resume.pdf",
      source_type: "file",
      relevance: 0.72,
      pages: [5],
    },
  ]);
  assert.deepEqual(citations.map(({ source_id, pages }) => [source_id, pages]), [
    ["safeek", [2]],
    ["anil", [5]],
  ]);
});

test("selected source without a relevance score is not hidden", () => {
  const citations = filterRelevantCitations([{
    source_id: "selected-source",
    filename: "Selected.pdf",
    source_type: "file",
    pages: [7],
  }]);
  assert.equal(citations.length, 1);
  assert.equal(citations[0].source_id, "selected-source");
});

test("source restriction keeps unrelated searched files out of answer sources", () => {
  const allowed = [{ source_id: "safeek", filename: "Safeek Resume.pdf" }];
  const searched = deduplicateSearchedFiles(allowed);
  const citations = filterRelevantCitations([{
    source_id: "safeek",
    filename: "Safeek Resume.pdf",
    source_type: "file",
    pages: [2],
  }]);
  assert.deepEqual(searched.map(({ source_id }) => source_id), ["safeek"]);
  assert.deepEqual(citations.map(({ source_id }) => source_id), ["safeek"]);
});

test("no evidence yields no source cards", () => {
  assert.deepEqual(filterRelevantCitations([]), []);
  assert.deepEqual(filterRelevantCitations([{
    filename: "No matching source",
    source_type: "none",
  }]), []);
});

test("duplicate document citations merge pages and preserve distinct scored snippets", () => {
  const sources = deduplicateCitations([
    {
      source_id: "safeek",
      filename: "Safeek Resume.pdf",
      source_type: "file",
      page: 2,
      pages: [2],
      snippets: [{ page: 2, text: "Java experience", relevance_percentage: 48 }],
    },
    {
      source_id: "safeek",
      filename: "Safeek Resume.pdf",
      source_type: "file",
      page: 4,
      pages: [4],
      snippets: [{ page: 4, text: "Java project", relevance_percentage: 42 }],
    },
  ]);
  assert.equal(sources.length, 1);
  assert.deepEqual(sources[0].pages, [2, 4]);
  assert.deepEqual(sources[0].snippets.map(({ relevance_percentage }) => relevance_percentage), [48, 42]);
});

test("chat renders source metadata for new and saved messages without requiring an attribution version", () => {
  const chatSource = readFileSync(new URL("../app/chat/page.js", import.meta.url), "utf8");
  assert.match(chatSource, /Sources \(\{sources\.length\}\)/);
  assert.match(chatSource, /message\.sources\.length > 0[\s\S]*?message\.citations/);
  assert.doesNotMatch(chatSource, /message\.source_attribution_version !== 1/);
  assert.match(chatSource, /No source metadata is available for this answer/);
  assert.match(chatSource, /<CitationCard/);
  assert.match(chatSource, /data\.sources \|\| data\.citations \|\| \[\]/);

  const historySource = readFileSync(new URL("../app/history/page.js", import.meta.url), "utf8");
  assert.match(historySource, /message\.sources\.length > 0[\s\S]*?message\.citations/);
  assert.match(historySource, /<CitationCard/);
  assert.match(historySource, /Sources \(\{sources\.length\}\)/);
});
