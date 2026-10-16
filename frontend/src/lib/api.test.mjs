import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, test } from "node:test";

const apiSource = readFileSync(new URL("./api.js", import.meta.url), "utf8");
const authSource = readFileSync(new URL("./auth.js", import.meta.url), "utf8");
const authModuleUrl = `data:text/javascript;base64,${Buffer.from(authSource).toString("base64")}`;
const testableApiSource = apiSource.replace(
  /^import \{ getToken, removeToken \} from "\.\/auth\.js";\r?\n/m,
  `const { getToken, removeToken } = await import("${authModuleUrl}");
`,
);
assert.notEqual(testableApiSource, apiSource, "auth helper import should be replaced for the test harness");
const { apiRequest, openDocument, getDocumentFile } = await import(
  `data:text/javascript;base64,${Buffer.from(testableApiSource).toString("base64")}`
);

let openedTab;
let alerts;
let storedToken;
let originalCreateObjectURL;
let saveToken;
let openedUrl;
let openedFeatures;

({ saveToken } = await import(authModuleUrl));

beforeEach(() => {
  alerts = [];
  storedToken = null;
  openedTab = {
    close() {
      this.closed = true;
    },
    location: { href: "about:blank" },
  };
  openedUrl = "";
  openedFeatures = "";

  globalThis.window = {
    open: (url, _target, features) => { openedUrl = url; openedFeatures = features; return openedTab; },
    alert: (message) => alerts.push(message),
    setTimeout: () => 1,
    location: { href: "/dashboard", origin: "http://localhost:3000", pathname: "/dashboard", search: "", hash: "" },
  };
  globalThis.localStorage = {
    getItem: (key) => key === "access_token" ? storedToken : null,
    setItem: (key, value) => {
      if (key === "access_token") storedToken = value;
    },
    removeItem: (key) => {
      if (key === "access_token") storedToken = null;
    },
  };
  originalCreateObjectURL = URL.createObjectURL;
  URL.createObjectURL = () => "blob:researchai-test";
});

afterEach(() => {
  delete globalThis.window;
  delete globalThis.localStorage;
  delete globalThis.fetch;
  URL.createObjectURL = originalCreateObjectURL;
});

test("missing session reports the problem without redirecting before fetch", async () => {
  let requestCount = 0;
  globalThis.fetch = async () => {
    requestCount += 1;
    throw new Error("fetch should not run without a session");
  };

  await openDocument("document-id");

  assert.equal(requestCount, 0);
  assert.equal(window.location.href, "/dashboard");
  assert.equal(openedUrl, "");
  assert.match(alerts[0], /no active ResearchAI sign-in session/i);
});

test("signed-in document open sends the existing Bearer token to the view route", async () => {
  saveToken("test-session-token");
  await openDocument("document-id");

  assert.equal(
    openedUrl,
    "/viewer/document-id?returnTo=%2Fdashboard",
  );
  assert.match(openedFeatures, /noopener/);
  assert.equal(window.location.href, "/dashboard");
  assert.deepEqual(alerts, []);
});

test("viewer URL preserves its same-site return page and selection context", async () => {
  saveToken("valid-session-token");
  window.location.pathname = "/documents";
  window.location.search = "?selected=owned-document";
  await openDocument("owned-document");

  assert.equal(
    openedUrl,
    "/viewer/owned-document?returnTo=%2Fdocuments%3Fselected%3Downed-document",
  );
});

test("login token stored by the shared helper is sent by document View", async () => {
  saveToken("login-issued-token");
  let authorization;
  globalThis.fetch = async (_url, options) => {
    authorization = options.headers.get("Authorization");
    return { status: 200, ok: true, headers: new Headers({"content-type":"application/pdf", "x-document-file-type":"pdf", "x-document-filename":"report.pdf"}), blob: async () => new Blob(["%PDF-1.7 test bytes"]) };
  };

  const file = await getDocumentFile("owned-pdf-id");

  assert.equal(authorization, "Bearer login-issued-token");
  assert.equal(file.fileType, "pdf");
  assert.equal(file.filename, "report.pdf");
  assert.match(await file.blob.text(), /^%PDF-/);
});

test("document fetch rejects a successful HTML response instead of treating it as a file", async () => {
  saveToken("valid-session-token");
  globalThis.fetch = async () => ({
    ok: true,
    redirected: false,
    headers: new Headers({ "content-type": "text/html" }),
    blob: async () => new Blob(["<html>storage error</html>"]),
  });

  await assert.rejects(getDocumentFile("document-id"), /error page instead of the original file/i);
});

test("document fetch rejects invalid PDF bytes before viewer or download actions appear", async () => {
  saveToken("valid-session-token");
  globalThis.fetch = async () => ({
    ok: true,
    redirected: false,
    headers: new Headers({ "content-type": "application/pdf", "x-document-file-type": "pdf" }),
    blob: async () => new Blob(["not a PDF"]),
  });

  await assert.rejects(getDocumentFile("document-id"), /not a valid PDF/i);
});

test("document View and working API requests use the same Bearer session", async () => {
  saveToken("shared-session-token");
  const authorizations = [];
  globalThis.fetch = async (url, options) => {
    authorizations.push(options.headers.get("Authorization"));
    if (url.includes("/documents/view/")) {
      return {
        status: 200,
        ok: true,
        headers: new Headers({
          "content-type": "application/pdf",
          "x-document-file-type": "pdf",
        }),
        blob: async () => new Blob(["%PDF-1.7 test bytes"]),
      };
    }
    return {
      status: 200,
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ documents: [] }),
      blob: async () => new Blob(["pdf"]),
    };
  };

  await apiRequest("/documents/");
  await getDocumentFile("owned-pdf-id");

  assert.deepEqual(authorizations, [
    "Bearer shared-session-token",
    "Bearer shared-session-token",
  ]);
});

test("unexpected API redirect is rejected by document fetch", async () => {
  saveToken("valid-session-token");
  globalThis.fetch = async () => ({
    status: 200,
    ok: true,
    redirected: true,
    url: "http://127.0.0.1:8001/login",
    blob: async () => new Blob(["login page"]),
  });

  await assert.rejects(getDocumentFile("document-id"), /API redirected the request/i);
});

test("fetch TypeError reports network and CORS failures", async () => {
  saveToken("valid-session-token");
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };

  await assert.rejects(getDocumentFile("document-id"), /backend connection and CORS settings/i);
});

test("401 document response clears expired session without redirecting", async () => {
  saveToken("expired-session-token");
  globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => ({ detail: "Invalid or expired token" }) });
  await assert.rejects(getDocumentFile("document-id"), /Invalid or expired token/);
  assert.equal(storedToken, null);
  assert.equal(window.location.href, "/dashboard");
});

test("document fetch distinguishes backend storage errors without redirecting to login", async () => {
  saveToken("valid-session-token");
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "http://127.0.0.1:8001/documents/view/doc%2Fid");
    assert.equal(options.headers.get("Authorization"), "Bearer valid-session-token");
    return { ok: false, status: 502, json: async () => ({ detail: "Unable to retrieve the stored document" }) };
  };
  await assert.rejects(getDocumentFile("doc/id"), /Unable to retrieve the stored document/);
  assert.equal(window.location.href, "/dashboard");
});

test("login 401 keeps the API detail instead of treating bad credentials as an expired session", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 401,
    headers: { get: () => "application/json" },
    json: async () => ({ detail: "Invalid email or password" }),
  });

  await assert.rejects(apiRequest("/auth/login", { method: "POST" }), /Invalid email or password/);
  assert.equal(window.location.href, "/dashboard");
});
