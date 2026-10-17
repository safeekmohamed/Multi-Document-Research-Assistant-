import { getToken, removeToken } from "./auth.js";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

export function authenticatedFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(url, { ...options, headers });
}

export async function getDocumentFile(documentId) {
  let response;
  try {
    response = await authenticatedFetch(
      `${API_BASE_URL}/documents/view/${encodeURIComponent(documentId)}`,
    );
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Could not reach the document API at ${API_BASE_URL}. Check the backend connection and CORS settings.`);
    }
    throw error;
  }
  if (response.redirected) {
    throw new Error("The document API redirected the request. Restart the backend and try again.");
  }
  if (!response.ok) {
    if (response.status === 401) removeToken();
    let detail = "Unable to open this document.";
    try {
      detail = (await response.json())?.detail || detail;
    } catch {
      // Keep the status-specific fallback for non-JSON responses.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  let filename = response.headers.get("x-document-filename") || "document";
  try { filename = decodeURIComponent(filename); } catch { /* Use the safe encoded value. */ }
  const blob = await response.blob();
  const contentType = response.headers.get("content-type") || "application/octet-stream";
  if (/^(text\/html|application\/(?:json|problem\+json))(?:\s*;|$)/i.test(contentType)) {
    throw new Error("Document storage returned an error page instead of the original file.");
  }
  const fileType = response.headers.get("x-document-file-type") || "";
  if (fileType.toLowerCase() === "pdf") {
    const signature = new TextDecoder().decode(await blob.slice(0, 5).arrayBuffer());
    if (!signature.startsWith("%PDF-")) {
      throw new Error("The stored file is not a valid PDF. It was not opened or downloaded.");
    }
  }
  return {
    blob,
    contentType,
    fileType,
    filename,
  };
}

export async function getDocumentPreview(documentId) {
  let response;
  try {
    response = await authenticatedFetch(
      `${API_BASE_URL}/documents/preview/${encodeURIComponent(documentId)}`,
    );
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Could not reach the document API at ${API_BASE_URL}. Check the backend connection and CORS settings.`);
    }
    throw error;
  }
  if (response.redirected) throw new Error("The document preview API redirected the request.");
  if (!response.ok) {
    if (response.status === 401) removeToken();
    let detail = "Unable to preview this workbook.";
    try { detail = (await response.json())?.detail || detail; } catch { /* Keep fallback. */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function openDocument(documentId) {
  if (!documentId || typeof window === "undefined") return;
  if (!getToken()) {
    window.alert(
      "This tab has no active ResearchAI sign-in session. Sign in, then retry opening the document."
    );
    return;
  }
  const currentPath = `${window.location.pathname || "/documents"}${window.location.search || ""}${window.location.hash || ""}`;
  const viewerUrl = new URL(`/viewer/${encodeURIComponent(documentId)}`, window.location.origin);
  viewerUrl.searchParams.set("returnTo", currentPath);
  window.open(`${viewerUrl.pathname}${viewerUrl.search}`, "_blank", "noopener,noreferrer");
}

export async function apiRequest(
  endpoint,
  options = {}
) {
  const token =
    getToken();

  const headers = {
    ...options.headers,
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await authenticatedFetch(
      `${API_BASE_URL}${endpoint}`,
      { ...options, headers }
    );
  } catch (error) {
    if (error instanceof TypeError) {
      const frontendOrigin =
        typeof window !== "undefined"
          ? window.location.origin
          : "the current frontend origin";
      throw new Error(
        `Unable to reach the API at ${API_BASE_URL}. Check that the backend is running and allows ${frontendOrigin} through CORS.`
      );
    }
    throw error;
  }

  const contentType =
    response.headers.get("content-type") || "";

  const data =
    contentType.includes("application/json")
      ? await response.json()
      : await response.text();

  if (response.status === 401) {
    const isPublicAuthEndpoint = endpoint.startsWith("/auth/");
    if (!isPublicAuthEndpoint && typeof window !== "undefined") {
      removeToken();
      window.location.href = "/login";
    }

    throw new Error(
      isPublicAuthEndpoint
        ? (typeof data === "object" ? data.detail || "Authentication failed." : data || "Authentication failed.")
        : "Session expired. Please login again."
    );
  }

  if (!response.ok) {
    throw new Error(
      typeof data === "object"
        ? data.detail || "Request failed"
        : data || "Request failed"
    );
  }

  return data;
}

export async function getDocuments() {
  return apiRequest("/documents/");
}

export async function uploadDocuments(files) {
  const formData = new FormData();
  Array.from(files || []).forEach((file) => {
    formData.append("files", file);
  });

  return apiRequest("/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function searchWeb(query) {
  const params = new URLSearchParams({
    query,
  });

  return apiRequest(
    `/urls/search?${params.toString()}`
  );
}
