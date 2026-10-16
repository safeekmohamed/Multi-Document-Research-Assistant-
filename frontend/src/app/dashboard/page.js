"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileSpreadsheet,
  FileStack,
  FileText,
  Globe2,
  Link2,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import Sidebar from "../../components/Sidebar";
import { apiRequest, openDocument } from "../../lib/api";

export default function DashboardPage() {
  const router = useRouter();

  const [user, setUser] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");
  const [openingId, setOpeningId] = useState(null);
  const [deletingConversationId, setDeletingConversationId] = useState(null);

  const [search, setSearch] = useState("");
  const [searchConversations, setSearchConversations] = useState([]);
  const [searchConversationQuery, setSearchConversationQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchErrorQuery, setSearchErrorQuery] = useState("");

  async function loadDashboard() {
    try {
      setDashboardError("");
      const [me, docs, convos] = await Promise.all([
        apiRequest("/users/me"),
        apiRequest("/documents/"),
        apiRequest("/history/conversations").catch((err) => {
          console.error("Conversations load failed:", err);
          return { conversations: [] };
        }),
      ]);

      setUser(me);
      setDocuments(Array.isArray(docs?.documents) ? docs.documents : []);
      setConversations(
        Array.isArray(convos?.conversations) ? convos.conversations : []
      );
    } catch (error) {
      console.error("Dashboard loading failed:", error);
      setDashboardError(error?.message || "Unable to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function initialize() {
      try {
        const [me, docs, convos] = await Promise.all([
          apiRequest("/users/me"),
          apiRequest("/documents/"),
          apiRequest("/history/conversations").catch((err) => {
            console.error("Conversations load failed:", err);
            return { conversations: [] };
          }),
        ]);

        if (!isMounted) return;
        setUser(me);
        setDocuments(Array.isArray(docs?.documents) ? docs.documents : []);
        setConversations(
          Array.isArray(convos?.conversations) ? convos.conversations : []
        );
      } catch (error) {
        if (!isMounted) return;
        console.error("Dashboard initialization failed:", error);
        setDashboardError(error?.message || "Unable to load dashboard data.");
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    initialize();

    function handleConversationsUpdated() {
      if (isMounted) {
        apiRequest("/history/conversations")
          .then((data) => {
            if (isMounted && Array.isArray(data?.conversations)) {
              setConversations(data.conversations);
            }
          })
          .catch((err) => console.error("Conversations refresh failed:", err));
      }
    }

    function handleSourcesUpdated() {
      if (isMounted) {
        apiRequest("/documents/")
          .then((data) => {
            if (isMounted && Array.isArray(data?.documents)) {
              setDocuments(data.documents);
            }
          })
          .catch((err) => console.error("Sources refresh failed:", err));
      }
    }

    function handleWindowFocus() {
      if (isMounted) {
        Promise.all([
          apiRequest("/documents/").catch(() => null),
          apiRequest("/history/conversations").catch(() => null),
        ]).then(([docs, convos]) => {
          if (!isMounted) return;
          if (docs && Array.isArray(docs.documents)) {
            setDocuments(docs.documents);
          }
          if (convos && Array.isArray(convos.conversations)) {
            setConversations(convos.conversations);
          }
        });
      }
    }

    window.addEventListener("research:conversations-updated", handleConversationsUpdated);
    window.addEventListener("research:sources-updated", handleSourcesUpdated);
    window.addEventListener("focus", handleWindowFocus);

    return () => {
      isMounted = false;
      window.removeEventListener("research:conversations-updated", handleConversationsUpdated);
      window.removeEventListener("research:sources-updated", handleSourcesUpdated);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, []);

  useEffect(() => {
    const query = search.trim();
    let active = true;

    const timeoutId = window.setTimeout(async () => {
      if (!active) {
        return;
      }

      if (!query) {
        setSearchConversations([]);
        setSearchConversationQuery("");
        setSearchLoading(false);
        setSearchError("");
        setSearchErrorQuery("");
        return;
      }

      setSearchLoading(true);
      setSearchError("");

      try {
        const data = await apiRequest("/history/conversations");

        if (active) {
          setSearchConversations(data?.conversations || []);
          setSearchConversationQuery(query.toLowerCase());
        }
      } catch (error) {
        if (active) {
          setSearchConversations([]);
          setSearchConversationQuery(query.toLowerCase());
          setSearchErrorQuery(query.toLowerCase());
          setSearchError(error?.message || "Unable to search conversations.");
        }
      } finally {
        if (active) {
          setSearchLoading(false);
        }
      }
    }, query ? 250 : 0);

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [search]);

  function handleNewChat() {
    router.push("/chat");
  }

  function handleDocuments() {
    router.push("/documents");
  }

  function handleHistory() {
    router.push("/history");
  }

  function handleAddWebsite() {
    router.push("/documents");
  }

  async function handleOpenSource(document) {
    if (!document?.id) {
      return;
    }

    if (document.source_type === "url" && document.source_url) {
      window.open(document.source_url, "_blank", "noopener,noreferrer");
      return;
    }

    setOpeningId(document.id);

    try {
      await openDocument(document.id);
    } catch (error) {
      console.error("Document opening failed:", error);
      alert("Unable to open this document.");
    } finally {
      setOpeningId(null);
    }
  }

  async function handleDeleteConversation(conversationId, event) {
    if (event) {
      event.stopPropagation();
    }

    if (!conversationId || deletingConversationId) {
      return;
    }

    const confirmed = window.confirm(
      "Are you sure you want to delete this conversation?"
    );
    if (!confirmed) {
      return;
    }

    setDeletingConversationId(conversationId);

    try {
      await apiRequest(`/history/conversations/${encodeURIComponent(conversationId)}`, {
        method: "DELETE",
      });

      setConversations((prev) => prev.filter((c) => c.id !== conversationId));
      window.dispatchEvent(new Event("research:conversations-updated"));
    } catch (error) {
      console.error("Failed to delete conversation:", error);
      alert(error?.message || "Failed to delete conversation.");
    } finally {
      setDeletingConversationId(null);
    }
  }

  const pdfCount = useMemo(() => {
    return documents.filter(
      (document) => document?.file_type?.toLowerCase() === "pdf"
    ).length;
  }, [documents]);

  const urlCount = useMemo(() => {
    return documents.filter(
      (document) => document?.source_type === "url"
    ).length;
  }, [documents]);

  const conversationCount = conversations.length;

  const filteredDocuments = useMemo(() => {
    const value = search.trim().toLowerCase();

    if (!value) {
      return documents.slice(0, 6);
    }

    return documents
      .filter((document) => {
        const filename = document?.filename?.toLowerCase() || "";
        const sourceUrl = document?.source_url?.toLowerCase() || "";
        const fileType = document?.file_type?.toLowerCase() || "";
        const docType = document?.document_type?.toLowerCase() || "";

        return (
          filename.includes(value) ||
          sourceUrl.includes(value) ||
          fileType.includes(value) ||
          docType.includes(value)
        );
      })
      .slice(0, 6);
  }, [documents, search]);

  const recentConversations = useMemo(() => {
    return conversations.slice(0, 4);
  }, [conversations]);

  const recentActivities = useMemo(() => {
    const docActivities = (documents || []).map((doc) => ({
      id: `doc-${doc.id || doc._id}`,
      type: "document",
      action:
        doc.source_type === "url" ? "Added website source" : "Uploaded document",
      title: doc.filename || doc.title || "Untitled source",
      date: doc.created_at,
      sourceType: doc.source_type,
      fileType: doc.file_type,
      rawItem: doc,
    }));

    const convoActivities = (conversations || []).map((convo) => ({
      id: `convo-${convo.id}`,
      type: "conversation",
      action: "Started research dialogue",
      title: convo.title || "New Conversation",
      date: convo.created_at,
      rawItem: convo,
    }));

    return [...docActivities, ...convoActivities]
      .filter((item) => item.date)
      .sort((a, b) => new Date(b.date) - new Date(a.date))
      .slice(0, 5);
  }, [documents, conversations]);

  const searchDocumentResults = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return [];
    }

    return documents
      .filter((document) => {
        const metadata =
          document?.metadata && typeof document.metadata === "object"
            ? JSON.stringify(document.metadata)
            : "";
        const searchableText = [
          document?.filename,
          document?.original_filename,
          document?.name,
          document?.title,
          document?.description,
          document?.source_url,
          document?.url,
          document?.file_type,
          document?.source_type,
          document?.document_type,
          metadata,
        ]
          .filter((value) => value !== null && value !== undefined)
          .join(" ")
          .toLowerCase();

        return searchableText.includes(query);
      })
      .slice(0, 5);
  }, [documents, search]);

  const searchConversationResults = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query || searchConversationQuery !== query) {
      return [];
    }

    return searchConversations
      .filter((conversation) =>
        String(conversation?.title || "")
          .toLowerCase()
          .includes(query)
      )
      .slice(0, 5);
  }, [search, searchConversationQuery, searchConversations]);

  function openSearchDocument(document) {
    setSearch("");

    if (document?.id) {
      handleOpenSource(document);
    } else {
      handleDocuments();
    }
  }

  function openSearchConversation(conversation) {
    if (!conversation?.id) {
      return;
    }

    setSearch("");
    router.push(
      `/chat?conversation_id=${encodeURIComponent(conversation.id)}`
    );
  }

  function getSourceType(document) {
    if (document?.source_type === "url") {
      return "Website";
    }

    return document?.file_type?.toUpperCase() || "FILE";
  }

  function getDocumentCategory(document) {
    const docType = document?.document_type;
    if (!docType) return null;

    const labels = {
      resume: "Resume",
      research_paper: "Research Paper",
      assignment: "Assignment",
      report: "Report",
      presentation: "Presentation",
      spreadsheet: "Spreadsheet",
      text_document: "Text Document",
      other: "General",
    };

    return labels[docType] || docType.replace(/_/g, " ");
  }

  function getSourceIcon(document) {
    if (document?.source_type === "url") {
      return (
        <div className="workspace-source-icon workspace-source-web">
          <Globe2 size={18} />
        </div>
      );
    }

    const type = document?.file_type?.toLowerCase() || "";

    if (type === "xlsx" || type === "csv") {
      return (
        <div className="workspace-source-icon workspace-source-sheet">
          <FileSpreadsheet size={18} />
        </div>
      );
    }

    return (
      <div className="workspace-source-icon workspace-source-file">
        <FileText size={18} />
      </div>
    );
  }

  function formatDate(dateValue) {
    if (!dateValue) {
      return "Recently";
    }

    try {
      const date = new Date(dateValue);

      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return "Recently";
    }
  }

  return (
    <div className="workspace-page">
      <div className="workspace-layout">
        <Sidebar />

        <main className="workspace-main">
          {/* Top Header & Search Bar */}
          <header className="workspace-topbar">
            <div className="workspace-search" style={{ position: "relative" }}>
              <Search size={18} />

              <input
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search documents, chats or research topics..."
                aria-label="Search documents and conversations"
                aria-controls="dashboard-search-results"
              />

              {search.trim() && (
                <div
                  id="dashboard-search-results"
                  role="region"
                  aria-live="polite"
                  aria-label="Search results"
                  style={{
                    position: "absolute",
                    zIndex: 110,
                    top: "calc(100% + 8px)",
                    left: 0,
                    right: 0,
                    maxHeight: 360,
                    overflowY: "auto",
                    padding: "8px",
                    border: "1px solid #e2e8f0",
                    borderRadius: 10,
                    background: "#fff",
                    boxShadow: "0 12px 30px rgba(15, 23, 42, 0.14)",
                    color: "#475569",
                  }}
                >
                  {searchDocumentResults.length > 0 && (
                    <div>
                      <div
                        style={{
                          padding: "7px 10px 5px",
                          color: "#64748b",
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                        }}
                      >
                        Documents ({searchDocumentResults.length})
                      </div>
                      {searchDocumentResults.map((document, index) => (
                        <button
                          type="button"
                          key={document?.id || `${document?.filename}-${index}`}
                          onClick={() => openSearchDocument(document)}
                          disabled={openingId === document?.id}
                          style={{
                            display: "flex",
                            width: "100%",
                            alignItems: "center",
                            gap: 10,
                            padding: "9px 10px",
                            border: 0,
                            borderRadius: 7,
                            background: "transparent",
                            color: "#1e293b",
                            cursor: "pointer",
                            textAlign: "left",
                          }}
                        >
                          {getSourceIcon(document)}
                          <span
                            style={{
                              minWidth: 0,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              fontSize: 13,
                              flex: 1,
                            }}
                          >
                            {document?.filename ||
                              document?.title ||
                              "Untitled source"}
                          </span>
                          <span
                            style={{
                              marginLeft: "auto",
                              color: "#64748b",
                              fontSize: 11,
                            }}
                          >
                            {getSourceType(document)}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}

                  {searchConversationResults.length > 0 && (
                    <div style={{ marginTop: searchDocumentResults.length > 0 ? 8 : 0 }}>
                      <div
                        style={{
                          padding: "7px 10px 5px",
                          color: "#64748b",
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                        }}
                      >
                        Conversations ({searchConversationResults.length})
                      </div>
                      {searchConversationResults.map((conversation) => (
                        <button
                          type="button"
                          key={conversation.id}
                          onClick={() => openSearchConversation(conversation)}
                          style={{
                            display: "flex",
                            width: "100%",
                            alignItems: "center",
                            gap: 10,
                            padding: "9px 10px",
                            border: 0,
                            borderRadius: 7,
                            background: "transparent",
                            color: "#1e293b",
                            cursor: "pointer",
                            textAlign: "left",
                            fontSize: 13,
                          }}
                        >
                          <MessageSquare
                            size={18}
                            style={{ flex: "0 0 auto", color: "#64748b" }}
                          />
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              flex: 1,
                            }}
                          >
                            {conversation.title || "New Conversation"}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}

                  {(searchLoading ||
                    searchConversationQuery !== search.trim().toLowerCase()) && (
                    <p style={{ margin: "8px 10px", fontSize: 13 }}>
                      Searching...
                    </p>
                  )}

                  {searchError &&
                    searchErrorQuery === search.trim().toLowerCase() && (
                    <p
                      role="status"
                      style={{
                        margin: "8px 10px",
                        color: "#b91c1c",
                        fontSize: 12,
                      }}
                    >
                      {searchError}
                    </p>
                  )}

                  {!searchLoading &&
                    !(searchError &&
                      searchErrorQuery === search.trim().toLowerCase()) &&
                    searchConversationQuery === search.trim().toLowerCase() &&
                    searchDocumentResults.length === 0 &&
                    searchConversationResults.length === 0 && (
                      <p style={{ margin: "8px 10px", fontSize: 13 }}>
                        No matching documents or conversations.
                      </p>
                    )}
                </div>
              )}
            </div>

            <div className="workspace-top-actions">
              <button
                type="button"
                className="workspace-new-chat"
                onClick={handleNewChat}
                title="Start a new research chat session"
              >
                <Plus size={17} />
                <span>New Chat</span>
              </button>

              <div className="workspace-profile">
                <div className="workspace-avatar">
                  {(user?.name || "U").charAt(0).toUpperCase()}
                </div>
                <span className="workspace-profile-name">
                  {user?.name || "User"}
                </span>
              </div>
            </div>
          </header>

          <div className="workspace-content">
            {/* Error Banner with Retry */}
            {dashboardError && (
              <div className="workspace-alert-error" role="alert">
                <span>{dashboardError}</span>
                <button
                  type="button"
                  onClick={loadDashboard}
                  style={{ display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  <RefreshCw size={13} /> Retry
                </button>
              </div>
            )}

            {/* Welcome & Research Heading */}
            <section className="workspace-heading">
              <div>
                <div className="workspace-heading-label">
                  <Sparkles size={15} />
                  Research Workspace
                </div>

                <h1>
                  Organize your sources
                  <br className="workspace-heading-break" />
                  and start intelligent research.
                </h1>

                <p>
                  Search and ask questions across your uploaded files and saved
                  website sources with verifiable citations.
                </p>

                <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="workspace-status-badge">
                    <CheckCircle2 size={12} />
                    {loading ? "Loading..." : `${documents.length} sources indexed`}
                  </span>
                  <span className="workspace-status-badge" style={{ background: "#f5efff", color: "#7657e8", borderColor: "#e9ddff" }}>
                    <MessageSquare size={12} />
                    {loading ? "Loading..." : `${conversationCount} saved conversations`}
                  </span>
                </div>
              </div>

              <div className="workspace-date">
                <CalendarDays size={17} />
                <div>
                  <strong>
                    {new Date().toLocaleDateString("en-US", {
                      weekday: "long",
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </strong>

                  <span>
                    Good{" "}
                    {new Date().getHours() < 12
                      ? "morning"
                      : new Date().getHours() < 18
                      ? "afternoon"
                      : "evening"}
                    , {user?.name ? user.name.split(" ")[0] : "Researcher"}!
                  </span>
                </div>
              </div>
            </section>

            {/* 4 Clickable Statistics Cards */}
            <section className="workspace-stats" aria-label="Research Workspace Statistics">
              <div
                className="workspace-stat stat-blue"
                onClick={handleDocuments}
                title="View all your uploaded files and saved websites"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleDocuments()}
              >
                <div className="workspace-stat-icon">
                  <FileStack size={19} />
                </div>
                <div>
                  <span>Total Sources</span>
                  <strong>{loading ? "—" : documents.length}</strong>
                  <small>All documents & websites</small>
                </div>
              </div>

              <div
                className="workspace-stat stat-red"
                onClick={handleDocuments}
                title="View your uploaded PDF files"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleDocuments()}
              >
                <div className="workspace-stat-icon">
                  <FileText size={19} />
                </div>
                <div>
                  <span>PDF Documents</span>
                  <strong>{loading ? "—" : pdfCount}</strong>
                  <small>Uploaded PDF files</small>
                </div>
              </div>

              <div
                className="workspace-stat stat-green"
                onClick={handleDocuments}
                title="View your saved web sources"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleDocuments()}
              >
                <div className="workspace-stat-icon">
                  <Globe2 size={19} />
                </div>
                <div>
                  <span>Website Sources</span>
                  <strong>{loading ? "—" : urlCount}</strong>
                  <small>Saved web sources</small>
                </div>
              </div>

              <div
                className="workspace-stat stat-purple"
                onClick={handleHistory}
                title="Browse your saved research conversations"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleHistory()}
              >
                <div className="workspace-stat-icon">
                  <MessageSquare size={19} />
                </div>
                <div>
                  <span>Conversations</span>
                  <strong>{loading ? "—" : conversationCount}</strong>
                  <small>Research conversations</small>
                </div>
              </div>
            </section>

            {/* Main Content Grid: 2 Columns */}
            <section className="workspace-grid">
              {/* Primary Column: Documents & Activity */}
              <div className="workspace-primary">
                {/* Documents Panel */}
                <div className="workspace-panel">
                  <div className="workspace-panel-header">
                    <div className="workspace-panel-title">
                      <div className="workspace-title-icon">
                        <FileText size={18} />
                      </div>
                      <div>
                        <h2>Your Documents</h2>
                        <p>
                          Your indexed files and saved website publications.
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={handleDocuments}
                      className="workspace-view-all"
                      title="Open full document manager"
                    >
                      View all ({documents.length})
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {loading ? (
                    <div className="workspace-loading">
                      <div className="workspace-spinner" />
                      <span>Loading your sources...</span>
                    </div>
                  ) : filteredDocuments.length === 0 ? (
                    <div className="workspace-empty">
                      <div className="workspace-empty-icon">
                        <FileText size={22} />
                      </div>
                      <h3>No sources indexed yet</h3>
                      <p>
                        Upload a PDF, DOCX, TXT, Excel or PowerPoint file, or
                        add a website URL to begin researching.
                      </p>
                      <button type="button" onClick={handleDocuments}>
                        Add your first source
                      </button>
                    </div>
                  ) : (
                    <div className="workspace-table">
                      <div className="workspace-table-head">
                        <span>Name</span>
                        <span>Category / Format</span>
                        <span>Added On</span>
                        <span style={{ textAlign: "right" }}>Actions</span>
                      </div>

                      {filteredDocuments.map((document, index) => {
                        const key =
                          document?.id || `${document?.filename}-${index}`;
                        const isOpening = openingId === document?.id;
                        const category = getDocumentCategory(document);

                        return (
                          <div key={key} className="workspace-table-row">
                            <button
                              type="button"
                              className="workspace-document-name"
                              onClick={() => handleOpenSource(document)}
                              disabled={isOpening}
                              title="Click to view original source"
                            >
                              {getSourceIcon(document)}
                              <span>
                                <strong>
                                  {document?.filename ||
                                    document?.title ||
                                    "Untitled source"}
                                </strong>
                                <small>
                                  {document?.chunk_count
                                    ? `${document.chunk_count} chunks indexed`
                                    : document?.source_type === "url"
                                    ? "Saved website"
                                    : "Uploaded file"}
                                </small>
                              </span>
                            </button>

                            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                              <span className="workspace-type">
                                {getSourceType(document)}
                              </span>
                              {category && (
                                <span className="workspace-doc-badge">
                                  {category}
                                </span>
                              )}
                            </div>

                            <span className="workspace-date-text">
                              {formatDate(document?.created_at)}
                            </span>

                            <div className="workspace-table-actions">
                              <button
                                type="button"
                                className="workspace-manage"
                                onClick={() => handleOpenSource(document)}
                                disabled={isOpening}
                                title="Open and view original content"
                              >
                                {isOpening ? "Opening..." : "Open"}
                              </button>

                              <button
                                type="button"
                                className="workspace-chat-action"
                                onClick={() => router.push("/chat")}
                                title="Ask questions about this in research chat"
                              >
                                <MessageSquare size={12} />
                                Chat
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Unified Research Activity Feed */}
                <div className="workspace-panel workspace-activity-panel">
                  <div className="workspace-panel-header">
                    <div className="workspace-panel-title">
                      <div className="workspace-title-icon activity-icon">
                        <Clock3 size={18} />
                      </div>
                      <div>
                        <h2>Recent Activity</h2>
                        <p>
                          Chronological timeline of uploaded documents and research conversations.
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      className="workspace-view-all"
                      onClick={handleHistory}
                      title="View conversation history"
                    >
                      View history
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {loading ? (
                    <div className="workspace-loading">
                      <div className="workspace-spinner" />
                      <span>Loading recent activity...</span>
                    </div>
                  ) : recentActivities.length === 0 ? (
                    <div className="workspace-activity-empty">
                      <span>
                        Your recent document uploads and research chats will appear here.
                      </span>
                    </div>
                  ) : (
                    <div className="workspace-timeline">
                      {recentActivities.map((activity) => {
                        const isDoc = activity.type === "document";

                        return (
                          <div
                            className="workspace-timeline-item"
                            key={activity.id}
                            style={{ cursor: "pointer" }}
                            onClick={() => {
                              if (isDoc) {
                                handleOpenSource(activity.rawItem);
                              } else {
                                router.push(
                                  `/chat?conversation_id=${encodeURIComponent(
                                    activity.rawItem.id
                                  )}`
                                );
                              }
                            }}
                            title={
                              isDoc
                                ? "Click to view document"
                                : "Click to continue conversation in chat"
                            }
                          >
                            <div className="workspace-timeline-line">
                              <div className="workspace-timeline-dot" />
                            </div>

                            {isDoc ? (
                              getSourceIcon(activity.rawItem)
                            ) : (
                              <div
                                className="workspace-source-icon"
                                style={{
                                  background: "#f3efff",
                                  color: "#7657e8",
                                }}
                              >
                                <MessageSquare size={17} />
                              </div>
                            )}

                            <div className="workspace-activity-text">
                              <strong>{activity.action}</strong>
                              <span>{activity.title}</span>
                              <small>{formatDate(activity.date)}</small>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Right Aside Column */}
              <aside className="workspace-right">
                {/* Quick Actions Panel */}
                <div className="workspace-side-panel">
                  <div className="workspace-side-title">
                    <Sparkles size={18} />
                    <h2>Quick Actions</h2>
                  </div>

                  <button
                    type="button"
                    className="workspace-action primary-action"
                    onClick={handleDocuments}
                    title="Upload local files to your research workspace"
                  >
                    <div className="workspace-action-icon">
                      <Upload size={18} />
                    </div>

                    <div>
                      <strong>Upload Document</strong>
                      <span>PDF, DOCX, TXT, CSV, XLSX, PPTX</span>
                    </div>

                    <ArrowUpRight size={16} />
                  </button>

                  <button
                    type="button"
                    className="workspace-action"
                    onClick={handleAddWebsite}
                    title="Add a web link to your research corpus"
                  >
                    <div className="workspace-action-icon">
                      <Link2 size={18} />
                    </div>

                    <div>
                      <strong>Add Website</strong>
                      <span>Save and index web publications</span>
                    </div>

                    <ArrowUpRight size={16} />
                  </button>

                  <button
                    type="button"
                    className="workspace-action"
                    onClick={handleNewChat}
                    title="Start an AI research conversation"
                  >
                    <div className="workspace-action-icon">
                      <MessageSquare size={18} />
                    </div>

                    <div>
                      <strong>Start Research Chat</strong>
                      <span>Ask questions grounded in sources</span>
                    </div>

                    <ArrowUpRight size={16} />
                  </button>
                </div>

                {/* Recent Conversations Connected to Actual Data */}
                <div className="workspace-side-panel">
                  <div className="workspace-side-header">
                    <div className="workspace-side-title">
                      <MessageSquare size={18} />
                      <h2>Recent Conversations</h2>
                    </div>

                    <button
                      type="button"
                      onClick={handleHistory}
                      title="View all saved conversations"
                    >
                      View all ({conversationCount})
                    </button>
                  </div>

                  <div className="workspace-conversations">
                    {loading ? (
                      <div className="workspace-loading" style={{ minHeight: 100 }}>
                        <div className="workspace-spinner" />
                        <span>Loading chats...</span>
                      </div>
                    ) : recentConversations.length === 0 ? (
                      <div className="workspace-no-conversations">
                        <MessageSquare size={20} />
                        <p>No conversations yet.</p>
                        <button type="button" onClick={handleNewChat}>
                          Start a research chat
                        </button>
                      </div>
                    ) : (
                      <div className="workspace-conversation-list">
                        {recentConversations.map((convo) => (
                          <div
                            key={convo.id}
                            className="workspace-conversation-item"
                            onClick={() =>
                              router.push(
                                `/chat?conversation_id=${encodeURIComponent(
                                  convo.id
                                )}`
                              )
                            }
                            title="Click to continue this conversation"
                          >
                            <div className="workspace-conversation-icon">
                              <MessageSquare size={16} />
                            </div>

                            <div className="workspace-conversation-info">
                              <strong>
                                {convo.title || "Untitled Conversation"}
                              </strong>
                              <span>{formatDate(convo.created_at)}</span>
                            </div>

                            <div className="workspace-conversation-actions">
                              <button
                                type="button"
                                className="workspace-conversation-del-btn"
                                onClick={(e) =>
                                  handleDeleteConversation(convo.id, e)
                                }
                                disabled={deletingConversationId === convo.id}
                                title="Delete this conversation"
                                aria-label="Delete conversation"
                              >
                                <Trash2 size={13} />
                              </button>
                              <ChevronRight
                                size={15}
                                style={{ color: "#94a3b8" }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Research Tips Panel */}
                <div className="workspace-tips">
                  <div className="workspace-tips-title">
                    <CheckCircle2 size={18} />
                    <h2>Research Tips</h2>
                  </div>

                  <ul>
                    <li>
                      Upload relevant documents for grounded factual answers.
                    </li>
                    <li>
                      Add website links to pull in current external research.
                    </li>
                    <li>
                      Compare multiple resumes or reports by name in research chat.
                    </li>
                    <li>
                      Click citations under any answer to inspect page references.
                    </li>
                    <li>
                      Continue previous conversations seamlessly from History.
                    </li>
                  </ul>
                </div>
              </aside>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
