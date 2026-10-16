"use client";

import { useEffect, useState } from "react";
import { Files } from "lucide-react";

import { apiRequest } from "../../../lib/api";
import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, formatAdminDate } from "../../../components/admin/AdminUI";

export default function AdminDocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDocuments() {
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/admin/documents");
      setDocuments(Array.isArray(data?.documents) ? data.documents : []);
    } catch (requestError) {
      setError(requestError?.message || "Unable to load admin documents.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiRequest("/admin/documents")
      .then((data) => {
        if (active) setDocuments(Array.isArray(data?.documents) ? data.documents : []);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load admin documents.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="workspace-content admin-content">
      <AdminPageHeader title="Documents" description="Uploaded files and the account that owns each one." />
      <section className="workspace-panel admin-panel">
        <div className="admin-list-toolbar">
          <div className="admin-list-heading">
            <div className="workspace-title-icon"><Files size={18} /></div>
            <div><h2>Uploaded documents</h2><p>{documents.length} files</p></div>
          </div>
        </div>

        {error ? <AdminError message={error} onRetry={loadDocuments} /> : null}
        {loading ? <AdminLoading label="Loading documents…" /> : null}
        {!loading && !error && documents.length === 0 ? (
          <AdminEmpty title="No documents yet" description="Uploaded files will appear here when they are available." />
        ) : null}

        {!loading && !error && documents.length > 0 ? (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr>
                <th scope="col">Filename</th><th scope="col">File Type</th><th scope="col">Owner</th>
                <th scope="col">Uploaded</th><th scope="col">Chunks</th>
              </tr></thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td data-label="Filename"><strong className="admin-file-name">{document.filename || "—"}</strong></td>
                    <td data-label="File Type"><span className="admin-role">{document.file_type || "—"}</span></td>
                    <td data-label="Owner"><div className="admin-user-cell"><strong>{document.owner_name || "Unknown"}</strong><span>{document.owner_email || "—"}</span></div></td>
                    <td data-label="Uploaded">{formatAdminDate(document.created_at)}</td>
                    <td data-label="Chunks">{document.chunk_count ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
