"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, FileText, Link2, Mail, ShieldCheck, UserRound } from "lucide-react";

import { apiRequest } from "../../../../lib/api";
import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, AdminStatus, formatAdminDate } from "../../../../components/admin/AdminUI";

export default function AdminUserDetailsPage() {
  const params = useParams();
  const userId = typeof params?.userId === "string" ? params.userId : "";
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDetails() {
    if (!userId) {
      setError("A user ID was not provided.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setDetails(await apiRequest(`/admin/users/${encodeURIComponent(userId)}`));
    } catch (requestError) {
      setError(requestError?.message || "Unable to load this user.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!userId) return;
    let active = true;
    apiRequest(`/admin/users/${encodeURIComponent(userId)}`)
      .then((data) => {
        if (active) setDetails(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load this user.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  const user = details?.user;

  return (
    <div className="workspace-content admin-content">
      <AdminPageHeader title="User Details" description="Account information and source totals for this user.">
        <Link href="/admin/users" className="app-secondary-button"><ArrowLeft size={15} /> Back to users</Link>
      </AdminPageHeader>

      {error ? <AdminError message={error} onRetry={loadDetails} /> : null}
      {!userId ? <AdminError message="A user ID was not provided." /> : null}
      {loading && userId ? <AdminLoading label="Loading user details…" /> : null}
      {!loading && !error && userId && !user ? <AdminEmpty title="User not found" description="The requested account was not returned by the API." /> : null}

      {!loading && !error && user ? (
        <>
          <section className="workspace-panel admin-detail-panel">
            <div className="admin-detail-heading">
              <div className="admin-detail-avatar"><UserRound size={22} /></div>
              <div><p className="app-eyebrow">Account</p><h2>{user.name || "Unnamed user"}</h2><span>{user.email || "—"}</span></div>
              <div className="admin-detail-statuses">
                <AdminStatus tone={user.is_verified ? "success" : "neutral"}>{user.is_verified ? "Verified" : "Unverified"}</AdminStatus>
                <AdminStatus tone={user.is_blocked ? "danger" : "success"}>{user.is_blocked ? "Blocked" : "Active"}</AdminStatus>
              </div>
            </div>
            <div className="admin-detail-grid">
              <div className="admin-detail-field"><span><UserRound size={15} /> Role</span><strong>{user.role || "—"}</strong></div>
              <div className="admin-detail-field"><span><Mail size={15} /> Email</span><strong>{user.email || "—"}</strong></div>
              <div className="admin-detail-field"><span><ShieldCheck size={15} /> Verification</span><strong>{user.is_verified ? "Verified" : "Not verified"}</strong></div>
              <div className="admin-detail-field"><span><ShieldCheck size={15} /> Access status</span><strong>{user.is_blocked ? "Blocked" : "Active"}</strong></div>
              <div className="admin-detail-field"><span>Created</span><strong>{formatAdminDate(user.created_at)}</strong></div>
            </div>
          </section>

          <section className="admin-usage-grid" aria-label="User source totals">
            <article className="workspace-stat admin-metric-card">
              <div className="workspace-stat-icon admin-metric-icon admin-tone-blue"><FileText size={19} /></div>
              <div className="admin-metric-copy"><span>Documents</span><strong>{details.document_count ?? "—"}</strong><small>Uploaded files</small></div>
            </article>
            <article className="workspace-stat admin-metric-card">
              <div className="workspace-stat-icon admin-metric-icon admin-tone-green"><Link2 size={19} /></div>
              <div className="admin-metric-copy"><span>URLs</span><strong>{details.url_count ?? "—"}</strong><small>Saved websites</small></div>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
