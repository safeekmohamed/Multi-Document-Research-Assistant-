"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Link2 } from "lucide-react";

import { apiRequest } from "../../../lib/api";
import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, formatAdminDate } from "../../../components/admin/AdminUI";

export default function AdminUrlsPage() {
  const [urls, setUrls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadUrls() {
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/admin/urls");
      setUrls(Array.isArray(data?.urls) ? data.urls : []);
    } catch (requestError) {
      setError(requestError?.message || "Unable to load saved URLs.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiRequest("/admin/urls")
      .then((data) => {
        if (active) setUrls(Array.isArray(data?.urls) ? data.urls : []);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load saved URLs.");
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
      <AdminPageHeader title="URLs" description="Saved websites and the account that added each one." />
      <section className="workspace-panel admin-panel">
        <div className="admin-list-toolbar">
          <div className="admin-list-heading">
            <div className="workspace-title-icon"><Link2 size={18} /></div>
            <div><h2>Saved URLs</h2><p>{urls.length} websites</p></div>
          </div>
        </div>

        {error ? <AdminError message={error} onRetry={loadUrls} /> : null}
        {loading ? <AdminLoading label="Loading URLs…" /> : null}
        {!loading && !error && urls.length === 0 ? (
          <AdminEmpty title="No saved URLs yet" description="Saved websites will appear here when they are available." />
        ) : null}

        {!loading && !error && urls.length > 0 ? (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr>
                <th scope="col">Website</th><th scope="col">Owner</th><th scope="col">Added</th><th scope="col">Link</th>
              </tr></thead>
              <tbody>
                {urls.map((item) => (
                  <tr key={item.id}>
                    <td data-label="Website"><strong className="admin-file-name">{item.title || "—"}</strong></td>
                    <td data-label="Owner"><div className="admin-user-cell"><strong>{item.owner_name || "Unknown"}</strong><span>{item.owner_email || "—"}</span></div></td>
                    <td data-label="Added">{formatAdminDate(item.created_at)}</td>
                    <td data-label="Link">
                      {getSafeWebUrl(item.url) ? (
                        <a className="admin-url-link" href={getSafeWebUrl(item.url)} target="_blank" rel="noreferrer noopener">
                          <span>{item.url}</span><ExternalLink size={14} aria-hidden="true" />
                        </a>
                      ) : item.url ? <span className="admin-url-text">{item.url}</span> : "—"}
                    </td>
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

function getSafeWebUrl(value) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : "";
  } catch {
    return "";
  }
}
