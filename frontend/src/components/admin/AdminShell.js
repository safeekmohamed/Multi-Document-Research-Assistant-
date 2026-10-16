"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Bell,
  Files,
  LayoutDashboard,
  Link2,
  LogOut,
  Menu,
  MessageSquareText,
  UsersRound,
  X,
} from "lucide-react";

import { apiRequest } from "../../lib/api";
import { getToken, removeToken } from "../../lib/auth";

const navigation = [
  { label: "Overview", href: "/admin", icon: LayoutDashboard },
  { label: "Users", href: "/admin/users", icon: UsersRound },
  { label: "Documents", href: "/admin/documents", icon: Files },
  { label: "URLs", href: "/admin/urls", icon: Link2 },
  { label: "Feedback", href: "/admin/feedback", icon: MessageSquareText },
];

function AdminGate({ state, message, children }) {
  if (state === "checking") {
    return (
      <main className="admin-gate" aria-live="polite">
        <span className="admin-spinner" />
        <p>Checking administrator access…</p>
      </main>
    );
  }

  if (state !== "allowed") {
    return (
      <main className="admin-gate">
        <div className="admin-gate-card">
          <span className="admin-gate-mark">!</span>
          <p className="app-eyebrow">ResearchAI Admin</p>
          <h1>{state === "denied" ? "Access denied" : "Unable to verify access"}</h1>
          <p>{message}</p>
          <Link className="app-secondary-button" href="/dashboard">
            <ArrowLeft size={15} /> Back to workspace
          </Link>
        </div>
      </main>
    );
  }

  return children;
}

export default function AdminShell({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const [access, setAccess] = useState({ state: "checking", message: "" });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationError, setNotificationError] = useState("");

  const loadNotifications = useCallback(async () => {
    try {
      const data = await apiRequest("/admin/feedback/notifications");
      setNotifications(Array.isArray(data?.notifications) ? data.notifications : []);
      setUnreadCount(Number(data?.unread_count) || 0);
      setNotificationError("");
    } catch (error) {
      setNotificationError(error?.message || "Unable to load feedback notifications.");
    }
  }, []);

  useEffect(() => {
    let active = true;

    async function verifyAccess() {
      if (!getToken()) {
        router.replace("/login");
        return;
      }

      try {
        const user = await apiRequest("/users/me");
        if (!active) return;

        setAccess(
          user?.role === "admin"
            ? { state: "allowed", message: "" }
            : {
                state: "denied",
                message: "Access denied. Admin privileges are required.",
              }
        );
      } catch (error) {
        if (!active) return;
        setAccess({
          state: "error",
          message: error?.message || "We could not verify your account. Please try again.",
        });
      }
    }

    verifyAccess();
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (access.state !== "allowed") return undefined;
    let active = true;
    apiRequest("/admin/feedback/notifications")
      .then((data) => {
        if (!active) return;
        setNotifications(Array.isArray(data?.notifications) ? data.notifications : []);
        setUnreadCount(Number(data?.unread_count) || 0);
        setNotificationError("");
      })
      .catch((error) => {
        if (active) setNotificationError(error?.message || "Unable to load feedback notifications.");
      });
    const interval = window.setInterval(loadNotifications, 60000);
    window.addEventListener("researchai-feedback-read", loadNotifications);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("researchai-feedback-read", loadNotifications);
    };
  }, [access.state, loadNotifications]);

  function logout() {
    removeToken();
    sessionStorage.removeItem("research_ai_conversation_id");
    router.push("/login");
  }

  function isActive(href) {
    return href === "/admin"
      ? pathname === href
      : pathname === href || pathname?.startsWith(`${href}/`);
  }

  return (
    <AdminGate state={access.state} message={access.message}>
      <div className="workspace-page workspace-layout admin-layout">
        <header className="mobile-workspace-bar admin-mobile-bar">
          <Link href="/admin" className="mobile-workspace-logo" onClick={() => setMobileOpen(false)}>
            Research<span>AI</span>
          </Link>
          <span className="admin-mobile-label">Admin</span>
          <button
            type="button"
            className="mobile-menu-button"
            aria-label={mobileOpen ? "Close admin menu" : "Open admin menu"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
        </header>

        {mobileOpen && (
          <button
            type="button"
            className="workspace-sidebar-overlay admin-sidebar-overlay"
            aria-label="Close admin menu"
            onClick={() => setMobileOpen(false)}
          />
        )}

        <aside className={`workspace-sidebar admin-sidebar ${mobileOpen ? "workspace-sidebar-mobile-open" : ""}`}>
          <div className="workspace-sidebar-logo-row">
            <Link href="/admin" className="workspace-sidebar-logo" onClick={() => setMobileOpen(false)}>
              Research<span>AI</span>
            </Link>
            <span className="admin-sidebar-badge">ADMIN</span>
            <button
              type="button"
              className="workspace-mobile-close"
              aria-label="Close admin menu"
              onClick={() => setMobileOpen(false)}
            >
              <X size={20} />
            </button>
          </div>

          <nav className="workspace-sidebar-nav" aria-label="Admin navigation">
            <p className="workspace-nav-label">Administration</p>
            {navigation.map(({ label, href, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`workspace-nav-item ${isActive(href) ? "workspace-nav-item-active" : ""}`}
                aria-current={isActive(href) ? "page" : undefined}
              >
                <Icon size={18} />
                <span>{label}</span>
              </Link>
            ))}
          </nav>

          <div className="workspace-sidebar-bottom">
            <Link href="/dashboard" className="workspace-sidebar-bottom-item" onClick={() => setMobileOpen(false)}>
              <ArrowLeft size={17} />
              <span>User workspace</span>
            </Link>
            <button type="button" className="workspace-sidebar-bottom-item" onClick={logout}>
              <LogOut size={17} />
              <span>Logout</span>
            </button>
          </div>
        </aside>

        <main className="workspace-main admin-main">
          <header className="workspace-topbar admin-topbar">
            <div className="admin-topbar-title">
              <span className="admin-topbar-kicker">Research Workspace</span>
              <strong>Administration</strong>
            </div>
            <div className="admin-topbar-actions">
              <div className="admin-notification-wrap">
                <button
                  type="button"
                  className="admin-notification-button"
                  aria-label={`Feedback notifications, ${unreadCount} unread`}
                  aria-expanded={notificationPanelOpen}
                  onClick={() => setNotificationPanelOpen((open) => !open)}
                >
                  <Bell size={17} />
                  {unreadCount > 0 ? <span className="admin-notification-count">{unreadCount > 99 ? "99+" : unreadCount}</span> : null}
                </button>
                {notificationPanelOpen ? (
                  <section className="admin-notification-panel" aria-label="Recent feedback notifications">
                    <div className="admin-notification-panel-header">
                      <strong>Feedback notifications</strong>
                      <span>{unreadCount} unread</span>
                    </div>
                    {notificationError ? <p className="admin-notification-error" role="alert">{notificationError}</p> : null}
                    {!notificationError && notifications.length === 0 ? (
                      <p className="admin-notification-empty">No unread feedback.</p>
                    ) : null}
                    {notifications.map((item) => (
                      <Link
                        key={item.id}
                        href={`/admin/feedback?id=${encodeURIComponent(item.id)}`}
                        className="admin-notification-item"
                        onClick={() => {
                          setNotificationPanelOpen(false);
                          if (pathname === "/admin/feedback") {
                            window.dispatchEvent(new CustomEvent("researchai-feedback-open", {
                              detail: item.id,
                            }));
                          }
                        }}
                      >
                        <span className="admin-notification-dot" />
                        <span className="admin-notification-copy">
                          <strong>{item.user_name || item.user_email || "User feedback"}</strong>
                          <span>{item.message}</span>
                        </span>
                      </Link>
                    ))}
                    <Link href="/admin/feedback" className="admin-notification-view-all" onClick={() => setNotificationPanelOpen(false)}>
                      View all feedback
                    </Link>
                  </section>
                ) : null}
              </div>
              <Link href="/dashboard" className="admin-workspace-link">
                <ArrowLeft size={15} /> User workspace
              </Link>
            </div>
          </header>
          {children}
        </main>
      </div>
    </AdminGate>
  );
}
