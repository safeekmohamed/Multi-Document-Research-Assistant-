"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Files, Link2, MessageSquareText, ShieldCheck, UsersRound } from "lucide-react";

import { apiRequest } from "../../lib/api";
import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, AdminStatus } from "../../components/admin/AdminUI";

const metrics = [
  { key: "total_users", label: "Total Users", note: "Registered accounts", icon: UsersRound, tone: "blue" },
  { key: "total_documents", label: "Total Documents", note: "Uploaded files", icon: Files, tone: "purple" },
  { key: "total_urls", label: "Total URLs", note: "Saved websites", icon: Link2, tone: "green" },
  { key: "blocked_users", label: "Blocked Users", note: "Accounts currently blocked", icon: ShieldCheck, tone: "slate" },
];

const quickActions = [
  { label: "Manage users", detail: "Review accounts and access", href: "/admin/users", icon: UsersRound },
  { label: "View documents", detail: "Browse uploaded file records", href: "/admin/documents", icon: Files },
  { label: "Review URLs", detail: "Browse saved website records", href: "/admin/urls", icon: Link2 },
  { label: "Read feedback", detail: "Open the user feedback inbox", href: "/admin/feedback", icon: MessageSquareText },
];

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [healthUnavailable, setHealthUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadOverview() {
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/admin/overview");
      setOverview(data);
    } catch (requestError) {
      setError(requestError?.message || "Unable to load the admin overview.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiRequest("/admin/overview")
      .then((data) => {
        if (active) setOverview(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load the admin overview.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    apiRequest("/health")
      .then((data) => {
        if (active) setHealth(data);
      })
      .catch(() => {
        if (active) setHealthUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="workspace-content admin-content">
      <AdminPageHeader
        title="Admin Overview"
        description="A current view of users and sources across the workspace."
      />

      {error ? <AdminError message={error} onRetry={loadOverview} /> : null}
      {loading ? <AdminLoading label="Loading overview…" /> : null}
      {!loading && !error && overview ? (
        <section className="admin-metric-grid" aria-label="Workspace totals">
          {metrics.map(({ key, label, note, icon: Icon, tone }) => (
            <article className="workspace-stat admin-metric-card" key={key}>
              <div className={`workspace-stat-icon admin-metric-icon admin-tone-${tone}`}>
                <Icon size={19} />
              </div>
              <div className="admin-metric-copy">
                <span>{label}</span>
                <strong>{overview[key] ?? "—"}</strong>
                <small>{note}</small>
              </div>
            </article>
          ))}
        </section>
      ) : null}
      <section className="admin-panel admin-quick-actions">
        <div className="admin-list-toolbar">
          <div className="admin-list-heading">
            <div><h2>Quick actions</h2><p>Jump to a workspace management area.</p></div>
          </div>
        </div>
        <div className="admin-quick-action-grid">
          {quickActions.map(({ label, detail, href, icon: Icon }) => (
            <Link href={href} className="admin-quick-action" key={href}>
              <span className="admin-quick-action-icon"><Icon size={18} /></span>
              <span><strong>{label}</strong><small>{detail}</small></span>
            </Link>
          ))}
        </div>
      </section>
      <section className="admin-panel admin-system-panel" aria-label="Verified system information">
        <div className="admin-list-toolbar">
          <div className="admin-list-heading">
            <div><h2>System information</h2><p>Live status from the backend health endpoint.</p></div>
          </div>
        </div>
        <div className="admin-system-status-grid">
          <div className="admin-system-status">
            <span>API</span>
            <AdminStatus tone={health?.status === "healthy" ? "success" : healthUnavailable ? "danger" : "neutral"}>
              {health?.status === "healthy" ? "Healthy" : healthUnavailable ? "Unavailable" : health ? "Unverified" : "Checking"}
            </AdminStatus>
          </div>
          <div className="admin-system-status">
            <span>Database</span>
            <AdminStatus tone={health?.mongodb === "connected" ? "success" : health?.mongodb === "disconnected" ? "danger" : "neutral"}>
              {health?.mongodb === "connected" ? "Connected" : health?.mongodb === "disconnected" ? "Disconnected" : healthUnavailable ? "Unavailable" : health ? "Unverified" : "Checking"}
            </AdminStatus>
          </div>
        </div>
      </section>
      {!loading && !error && !overview ? (
        <AdminEmpty title="Overview unavailable" description="The API returned no overview data." />
      ) : null}
    </div>
  );
}
