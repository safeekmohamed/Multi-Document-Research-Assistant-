import { AlertCircle } from "lucide-react";

export function AdminPageHeader({ eyebrow = "Administration", title, description, children }) {
  return (
    <header className="admin-page-heading">
      <div>
        <p className="app-eyebrow">{eyebrow}</p>
        <h1 className="app-title">{title}</h1>
        {description ? <p className="app-subtitle">{description}</p> : null}
      </div>
      {children ? <div className="admin-heading-actions">{children}</div> : null}
    </header>
  );
}

export function AdminLoading({ label = "Loading…" }) {
  return (
    <div className="admin-state" role="status" aria-live="polite">
      <span className="admin-spinner" />
      <span>{label}</span>
    </div>
  );
}

export function AdminError({ message, onRetry }) {
  return (
    <div className="admin-feedback admin-feedback-error" role="alert">
      <AlertCircle size={17} />
      <span>{message || "Something went wrong while loading this page."}</span>
      {onRetry ? <button type="button" className="admin-inline-button" onClick={onRetry}>Try again</button> : null}
    </div>
  );
}

export function AdminEmpty({ title, description }) {
  return (
    <div className="admin-empty">
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

export function AdminStatus({ children, tone = "neutral" }) {
  return <span className={`admin-status admin-status-${tone}`}>{children}</span>;
}

export function formatAdminDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
