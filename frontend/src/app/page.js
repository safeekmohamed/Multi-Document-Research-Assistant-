import Link from "next/link";

const features = [
  {
    number: "01",
    icon: "document",
    title: "Documents",
    description: "Your PDFs and research files, organized in one place.",
    detail: "UPLOAD & ORGANIZE",
  },
  {
    number: "02",
    icon: "globe",
    title: "Web sources",
    description: "Bring useful websites into your research library.",
    detail: "COLLECT SOURCES",
  },
  {
    number: "03",
    icon: "message",
    title: "Research chat",
    description: "Ask questions and revisit your research conversations.",
    detail: "EXPLORE & DISCOVER",
  },
];

function FeatureIcon({ type }) {
  if (type === "document") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M6 3.75h8l4 4v12.5H6z" />
        <path d="M14 3.75v4h4M9 12h6M9 16h6" />
      </svg>
    );
  }

  if (type === "globe") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3Z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v9a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.5A2.5 2.5 0 0 1 4 14.5z" />
      <path d="M8 8h8M8 12h5" />
    </svg>
  );
}

export default function Home() {
  return (
    <main className="landing-page">
      <div className="landing-orb landing-orb-one" aria-hidden="true" />
      <div className="landing-orb landing-orb-two" aria-hidden="true" />

      <header className="landing-header">
        <Link href="/" className="landing-logo" aria-label="ResearchAI home">
          Research<span>AI</span>
        </Link>

        <nav aria-label="Main navigation" className="landing-nav">
          <Link href="/login" className="landing-login">
            Log in
          </Link>
          <Link href="/register" className="landing-cta">
            Create account <span aria-hidden="true">↗</span>
          </Link>
        </nav>
      </header>

      <section className="landing-content">
        <div className="landing-hero">
          <div className="landing-eyebrow">
            <span className="landing-status-dot" />
            YOUR PERSONAL RESEARCH WORKSPACE
          </div>

          <h1>
            Keep your sources
            <br />
            and research <span className="landing-heading-accent">together.</span>
          </h1>

          <p className="landing-description">
            Bring documents and website sources into one workspace, then ask
            questions and review the conversations that matter.
          </p>

          <div className="landing-primary-actions">
            <Link href="/register" className="landing-cta landing-main-cta">
              Get started <span aria-hidden="true">→</span>
            </Link>
            <Link href="/login" className="landing-secondary">
              Sign in to your workspace
            </Link>
          </div>

          <div className="landing-trust-note">
            <span aria-hidden="true">✳</span>
            One workspace for everything you research.
          </div>
        </div>

        <div className="landing-preview" aria-label="Research workspace preview">
          <div className="preview-topbar">
            <div className="preview-window-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span className="preview-label">YOUR RESEARCH SPACE</span>
            <span className="preview-live">
              <span /> Workspace
            </span>
          </div>

          <div className="preview-body">
            <aside className="preview-sidebar">
              <div className="preview-brand">
                <span className="preview-brand-mark">R</span>
                <span>ResearchAI</span>
              </div>
              <div className="preview-menu-item preview-menu-active">
                <span>▦</span> Overview
              </div>
              <div className="preview-menu-item">
                <span>▤</span> Documents
              </div>
              <div className="preview-menu-item">
                <span>◎</span> Web sources
              </div>
              <div className="preview-menu-item">
                <span>◷</span> Conversations
              </div>
              <div className="preview-sidebar-note">
                Your ideas,
                <br />
                all in one place.
              </div>
            </aside>

            <div className="preview-main">
              <div className="preview-welcome">
                <div>
                  <span className="preview-kicker">WORKSPACE OVERVIEW</span>
                  <h2>Your research, organized.</h2>
                  <p>Everything you need to continue exploring.</p>
                </div>
                <span className="preview-avatar">R</span>
              </div>

              <div className="preview-stats">
                <div className="preview-stat">
                  <span className="preview-stat-icon preview-purple">▤</span>
                  <span>Documents</span>
                  <strong>Sources</strong>
                  <small>Your research files</small>
                </div>
                <div className="preview-stat">
                  <span className="preview-stat-icon preview-blue">◎</span>
                  <span>Web library</span>
                  <strong>Web sources</strong>
                  <small>Saved for later</small>
                </div>
              </div>

              <div className="preview-recent">
                <div className="preview-recent-heading">
                  <strong>Research workflow</strong>
                  <span>Workspace</span>
                </div>
                <div className="preview-document">
                  <span className="preview-file-icon">PDF</span>
                  <div>
                    <strong>Research materials</strong>
                    <small>Documents ready to explore</small>
                  </div>
                  <span className="preview-file-arrow">↗</span>
                </div>
                <div className="preview-document">
                  <span className="preview-file-icon preview-web-icon">WEB</span>
                  <div>
                    <strong>Web references</strong>
                    <small>Sources gathered in one place</small>
                  </div>
                  <span className="preview-file-arrow">↗</span>
                </div>
              </div>
            </div>
          </div>
          <div className="preview-bottom-line" />
        </div>
      </section>

      <section className="landing-features">
        <div className="landing-section-heading">
          <div>
            <span className="landing-section-kicker">BUILT FOR YOUR WORKFLOW</span>
            <h2>Research without the clutter.</h2>
          </div>
          <p>
            From the first source to the final question, keep your work
            connected.
          </p>
        </div>

        <div className="landing-capabilities">
          {features.map((feature) => (
            <article className="landing-feature-card" key={feature.number}>
              <div className="feature-card-top">
                <span className={`feature-icon feature-icon-${feature.icon}`}>
                  <FeatureIcon type={feature.icon} />
                </span>
                <span className="feature-number">{feature.number}</span>
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
              <div className="feature-card-bottom">
                <span>{feature.detail}</span>
                <span className="feature-arrow" aria-hidden="true">↗</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer className="landing-footer">
        <Link href="/" className="landing-logo landing-footer-logo">
          Research<span>AI</span>
        </Link>
        <span>Thoughtful research starts here.</span>
        <span>© {new Date().getFullYear()} ResearchAI</span>
      </footer>
    </main>
  );
}