"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, MessageSquareText } from "lucide-react";

import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, AdminStatus, formatAdminDate } from "../../../components/admin/AdminUI";
import { apiRequest } from "../../../lib/api";

const categoryLabels = {
  bug_report: "Bug Report",
  suggestion: "Suggestion",
  general: "General Feedback",
};

export default function AdminFeedbackPage() {
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [markingRead, setMarkingRead] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    apiRequest("/admin/feedback")
      .then(async (data) => {
        if (!active) return;
        const feedback = Array.isArray(data?.feedback) ? data.feedback : [];
        setItems(feedback);
        const queryId = new URLSearchParams(window.location.search).get("id");
        setSelectedId(queryId || "");
        const linkedFeedback = feedback.find((item) => item.id === queryId);
        if (linkedFeedback && !linkedFeedback.is_read) {
          const readData = await apiRequest(
            `/admin/feedback/${encodeURIComponent(linkedFeedback.id)}/read`,
            { method: "PATCH" }
          );
          if (!active) return;
          setItems((current) => current.map((item) => (
            item.id === linkedFeedback.id
              ? { ...item, ...readData?.feedback }
              : item
          )));
          window.dispatchEvent(new Event("researchai-feedback-read"));
        }
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load feedback.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);

  useEffect(() => {
    function handleFeedbackOpen(event) {
      const item = items.find((entry) => entry.id === event.detail);
      if (item) openFeedback(item);
    }
    window.addEventListener("researchai-feedback-open", handleFeedbackOpen);
    return () => window.removeEventListener("researchai-feedback-open", handleFeedbackOpen);
  }, [items]);

  function retryLoadingFeedback() {
    setLoading(true);
    setError("");
    setRefreshKey((key) => key + 1);
  }

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId]
  );

  async function openFeedback(item) {
    setSelectedId(item.id);
    window.history.replaceState(null, "", `/admin/feedback?id=${encodeURIComponent(item.id)}`);
    if (item.is_read) return;

    setMarkingRead(true);
    try {
      const data = await apiRequest(`/admin/feedback/${encodeURIComponent(item.id)}/read`, {
        method: "PATCH",
      });
      const updated = data?.feedback;
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, ...updated } : entry));
      window.dispatchEvent(new Event("researchai-feedback-read"));
    } catch (requestError) {
      setError(requestError?.message || "Unable to mark feedback as read.");
    } finally {
      setMarkingRead(false);
    }
  }

  return (
    <div className="workspace-content admin-content">
      <AdminPageHeader
        title="User Feedback"
        description="Read feedback submitted by users in the ResearchAI workspace."
      >
        <Link href="/admin" className="app-secondary-button"><ArrowLeft size={15} /> Overview</Link>
      </AdminPageHeader>

      {error ? (
        <AdminError
          message={error}
          onRetry={retryLoadingFeedback}
        />
      ) : null}
      {loading ? <AdminLoading label="Loading feedback…" /> : null}
      {!loading && !error && items.length === 0 ? (
        <section className="admin-panel">
          <AdminEmpty title="No feedback yet" description="User-submitted feedback will appear here." />
        </section>
      ) : null}

      {!loading && items.length > 0 ? (
        <section className="admin-feedback-workspace" aria-label="Feedback inbox">
          <div className="admin-panel admin-feedback-list">
            <div className="admin-list-toolbar">
              <div className="admin-list-heading">
                <span className="admin-feedback-heading-icon"><MessageSquareText size={17} /></span>
                <div><h2>Inbox</h2><p>{items.length} {items.length === 1 ? "message" : "messages"}</p></div>
              </div>
            </div>
            <div className="admin-feedback-items">
              {items.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={`admin-feedback-item ${selectedId === item.id ? "admin-feedback-item-selected" : ""} ${!item.is_read ? "admin-feedback-item-unread" : ""}`}
                  onClick={() => openFeedback(item)}
                  aria-current={selectedId === item.id ? "true" : undefined}
                >
                  <span className="admin-feedback-item-top">
                    <strong>{item.user_name || item.user_email || "Workspace user"}</strong>
                    {!item.is_read ? <span className="admin-feedback-unread-dot" aria-label="Unread" /> : null}
                  </span>
                  <span className="admin-feedback-item-category">{categoryLabels[item.category] || "Feedback"}</span>
                  <span className="admin-feedback-item-message">{item.message}</span>
                  <span className="admin-feedback-item-date">{formatAdminDate(item.created_at)}</span>
                </button>
              ))}
            </div>
          </div>

          <article className="admin-panel admin-feedback-detail" aria-live="polite">
            {selectedItem ? (
              <>
                <header className="admin-feedback-detail-header">
                  <div>
                    <p className="app-eyebrow">{categoryLabels[selectedItem.category] || "Feedback"}</p>
                    <h2>{selectedItem.user_name || "Workspace user"}</h2>
                    {selectedItem.user_email ? <a href={`mailto:${selectedItem.user_email}`}>{selectedItem.user_email}</a> : null}
                  </div>
                  <AdminStatus tone={selectedItem.is_read ? "neutral" : "success"}>
                    {selectedItem.is_read ? "Read" : "Unread"}
                  </AdminStatus>
                </header>
                <p className="admin-feedback-detail-date">Submitted {formatAdminDate(selectedItem.created_at)}</p>
                <p className="admin-feedback-detail-message">{selectedItem.message}</p>
                {!selectedItem.is_read ? (
                  <button
                    type="button"
                    className="app-secondary-button admin-feedback-read-button"
                    onClick={() => openFeedback(selectedItem)}
                    disabled={markingRead}
                  >
                    <Check size={15} /> {markingRead ? "Marking read…" : "Mark as read"}
                  </button>
                ) : null}
              </>
            ) : (
              <AdminEmpty title="Select feedback" description="Choose a message from the inbox to read it." />
            )}
          </article>
        </section>
      ) : null}
    </div>
  );
}
