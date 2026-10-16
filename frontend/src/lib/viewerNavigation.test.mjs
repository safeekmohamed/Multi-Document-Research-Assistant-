import assert from "node:assert/strict";
import { test } from "node:test";
import { getViewerBackDestination } from "./viewerNavigation.js";

test("viewer Back uses valid same-origin history", () => {
  assert.deepEqual(
    getViewerBackDestination({
      origin: "http://localhost:3000",
      referrer: "http://localhost:3000/documents?selected=doc-1",
      historyLength: 2,
      search: "?returnTo=%2Fdashboard",
    }),
    { useHistory: true, fallback: "/dashboard" },
  );
});

test("viewer Back falls back to its recorded page when opened in a fresh tab", () => {
  assert.deepEqual(
    getViewerBackDestination({
      origin: "http://localhost:3000",
      referrer: "",
      historyLength: 1,
      search: "?returnTo=%2Fdocuments%3Fselected%3Ddoc-1",
    }),
    { useHistory: false, fallback: "/documents?selected=doc-1" },
  );
});

test("viewer Back rejects cross-origin return destinations", () => {
  assert.deepEqual(
    getViewerBackDestination({
      origin: "http://localhost:3000",
      historyLength: 1,
      search: "?returnTo=https%3A%2F%2Fevil.example",
    }),
    { useHistory: false, fallback: "/documents" },
  );
});
