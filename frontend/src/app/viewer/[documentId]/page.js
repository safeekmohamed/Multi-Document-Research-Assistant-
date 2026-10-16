"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, ExternalLink, FileText, LoaderCircle } from "lucide-react";
import { getDocumentFile, getDocumentPreview } from "@/lib/api";
import { parseCsv } from "@/lib/documentFormats";
import { getViewerBackDestination } from "@/lib/viewerNavigation";

export default function DocumentViewerPage() {
  const { documentId } = useParams();
  const router = useRouter();
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [rows, setRows] = useState([]);
  const [csvTruncated, setCsvTruncated] = useState(false);
  const [workbook, setWorkbook] = useState(null);
  const [objectUrl, setObjectUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let createdUrl = "";
    async function load() {
      try {
        const result = await getDocumentFile(documentId);
        if (!active) return;
        createdUrl = URL.createObjectURL(result.blob);
        setObjectUrl(createdUrl);
        setFile(result);
        const type = (result.fileType || result.filename.split(".").pop() || "").toLowerCase();
        if (type === "txt") setText(await result.blob.text());
        if (type === "csv") {
          const parsed = parseCsv(await result.blob.text());
          setRows(parsed.rows);
          setCsvTruncated(parsed.truncated);
        }
        if (type === "xlsx") setWorkbook(await getDocumentPreview(documentId));
      } catch (loadError) {
        if (!active) return;
        if (loadError.status === 401) setError("Your session expired. Sign in again, then reopen this document.");
        else if (loadError.status === 403) setError("You do not have permission to open this document.");
        else if (loadError.status === 404) setError("This document or its stored Cloudinary file could not be found.");
        else if (loadError.status === 502) setError("Cloud storage could not return this file. Try again later or contact support.");
        else setError(loadError.message || "Unable to load this document.");
      } finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; if (createdUrl) URL.revokeObjectURL(createdUrl); };
  }, [documentId]);

  const fileType = (file?.fileType || file?.filename?.split(".").pop() || "").toLowerCase();

  function downloadFile() {
    if (!objectUrl || !file) return;
    const anchor = window.document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = file.filename;
    anchor.click();
  }

  function returnToDocuments() {
    const destination = getViewerBackDestination({
      search: window.location.search,
      referrer: document.referrer,
      origin: window.location.origin,
      historyLength: window.history.length,
    });
    if (destination.useHistory) router.back();
    else router.push(destination.fallback);
  }

  return (
    <main className="document-viewer-page">
      <header className="document-viewer-toolbar">
        <button type="button" className="document-viewer-back" onClick={returnToDocuments}><ArrowLeft size={17} /> Back</button>
        <div className="document-viewer-title"><FileText size={18} /><span>{file?.filename || "Document viewer"}</span></div>
        <div className="document-viewer-actions">
          {objectUrl && <a href={objectUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Open in new tab</a>}
          {objectUrl && <button type="button" onClick={downloadFile}><Download size={16} /> Download</button>}
        </div>
      </header>
      <section className="document-viewer-content">
        {loading && <div className="document-viewer-state"><LoaderCircle className="document-viewer-spinner" size={26} />Loading your document…</div>}
        {!loading && error && <div className="document-viewer-state document-viewer-error"><strong>Could not open document</strong><span>{error}</span>{error.includes("Sign in again") && <a className="document-viewer-login" href="/login">Go to sign in</a>}</div>}
        {!loading && !error && fileType === "pdf" && <iframe className="document-viewer-pdf" src={objectUrl} title={file.filename} />}
        {!loading && !error && fileType === "txt" && <pre className="document-viewer-text">{text}</pre>}
        {!loading && !error && fileType === "csv" && (rows.length ? (
          <div className="document-viewer-table-scroll"><table className="document-viewer-table"><thead><tr>{rows[0].map((cell, index) => <th key={index}>{cell || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{rows.slice(1, 301).map((row, rowIndex) => <tr key={rowIndex}>{Array.from({ length: Math.max(rows[0].length, row.length) }, (_, columnIndex) => <td key={columnIndex}>{row[columnIndex] || ""}</td>)}</tr>)}</tbody></table>{csvTruncated && <p className="document-viewer-limit">Showing the first 300 rows. Download the file to view the rest.</p>}</div>
        ) : <div className="document-viewer-state">This CSV has no rows to display.</div>)}
        {!loading && !error && fileType === "xlsx" && workbook && <WorkbookPreview workbook={workbook} />}
        {!loading && !error && !["pdf", "txt", "csv"].includes(fileType) && <div className="document-viewer-state"><strong>Preview is unavailable for {fileType.toUpperCase() || "this file type"}</strong><span>The original file is available to download.</span><button type="button" onClick={downloadFile}><Download size={16} /> Download {file.filename}</button></div>}
      </section>
    </main>
  );
}

function WorkbookPreview({ workbook }) {
  const [activeSheet, setActiveSheet] = useState(0);
  const sheet = workbook.sheets[activeSheet];
  return (
    <div className="document-viewer-table-scroll">
      {workbook.sheets.length > 1 && <nav className="document-viewer-sheet-tabs" aria-label="Workbook sheets">{workbook.sheets.map((item, index) => <button type="button" key={`${item.name}-${index}`} className={index === activeSheet ? "active" : ""} onClick={() => setActiveSheet(index)}>{item.name}</button>)}</nav>}
      {sheet?.rows?.length ? <table className="document-viewer-table"><tbody>{sheet.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => rowIndex === 0 ? <th key={cellIndex}>{cell}</th> : <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table> : <p>This worksheet is empty.</p>}
      {workbook.truncated && <p className="document-viewer-limit">Preview is limited to the first 500 rows and 50 columns per worksheet.</p>}
    </div>
  );
}
