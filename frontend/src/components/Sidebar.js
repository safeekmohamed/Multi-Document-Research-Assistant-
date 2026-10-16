"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import {
  ArrowLeft,
  FileText,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  MessageSquareText,
  X,
} from "lucide-react";
import FeedbackDialog from "./FeedbackDialog";

const menuItems = [
  {
    label: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    label: "Documents",
    href: "/documents",
    icon: FileText,
  },
  {
    label: "Research Chat",
    href: "/chat",
    icon: MessageSquare,
  },
  {
    label: "History",
    href: "/history",
    icon: History,
  },
];

function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  function handleLogout() {
    localStorage.removeItem("access_token");
    sessionStorage.removeItem(
      "research_ai_conversation_id"
    );

    router.push("/login");
  }

  function closeMobile() {
    setMobileOpen(false);
  }

  return (
    <>
      {

}

      <header className="mobile-workspace-bar">
        <Link
          href="/dashboard"
          className="mobile-workspace-logo"
          onClick={closeMobile}
        >
          Research<span>AI</span>
        </Link>

        <button
          type="button"
          className="mobile-menu-button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
        >
          <Menu size={24} />
        </button>
      </header>

      {

}

      {mobileOpen && (
        <button
          type="button"
          className="workspace-sidebar-overlay"
          aria-label="Close menu"
          onClick={closeMobile}
        />
      )}

      {

}

      <aside
        className={`workspace-sidebar ${
          mobileOpen
            ? "workspace-sidebar-mobile-open"
            : ""
        }`}
      >
        {

}

        <div className="workspace-sidebar-logo-row">
          <Link
            href="/dashboard"
            className="workspace-sidebar-logo"
            onClick={closeMobile}
          >
            Research<span>AI</span>
          </Link>

          <button
            type="button"
            className="workspace-mobile-close"
            onClick={closeMobile}
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>

        {

}

        <nav className="workspace-sidebar-nav">
          <p className="workspace-nav-label">
            Workspace
          </p>

          {menuItems.map((item) => {
            const Icon = item.icon;

            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" &&
                pathname?.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={closeMobile}
                className={`workspace-nav-item ${
                  active
                    ? "workspace-nav-item-active"
                    : ""
                }`}
              >
                <Icon size={18} />

                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {

}

        <div className="workspace-sidebar-bottom">
          <button
            type="button"
            className="workspace-sidebar-bottom-item"
            onClick={() => {
              setFeedbackOpen(true);
              closeMobile();
            }}
          >
            <MessageSquareText size={17} />
            <span>Feedback</span>
          </button>
          <Link
            href="/"
            className="workspace-sidebar-bottom-item"
            onClick={closeMobile}
          >
            <ArrowLeft size={17} />

            <span>Back to Home</span>
          </Link>

          <button
            type="button"
            className="workspace-sidebar-bottom-item"
            onClick={handleLogout}
          >
            <LogOut size={17} />

            <span>Logout</span>
          </button>
        </div>
      </aside>
      {feedbackOpen ? <FeedbackDialog onClose={() => setFeedbackOpen(false)} /> : null}
    </>
  );
}

export default Sidebar;

export function AppShell({
  children,
  className = "",
  contentClassName = "",
}) {
  return (
    <div
      className={`workspace-page workspace-layout ${className}`.trim()}
    >
      <Sidebar />

      <main
        className={`workspace-main ${contentClassName}`.trim()}
      >
        {children}
      </main>
    </div>
  );
}