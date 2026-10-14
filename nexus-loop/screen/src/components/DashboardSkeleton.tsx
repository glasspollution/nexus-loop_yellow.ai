export function DashboardSkeleton() {
  return (
    <main className="page-shell loading-shell" aria-busy="true" aria-label="Loading the latest analysis">
      <div className="dashboard-frame">
        <header className="loading-header">
          <div className="skeleton skeleton-title" />
          <div className="skeleton skeleton-title-short" />
          <div className="skeleton skeleton-subtitle" />
          <div className="loading-profile" aria-hidden="true">
            <span className="skeleton skeleton-avatar" />
          </div>
        </header>

        <div className="loading-overview">
          <section className="skeleton-card skeleton-impact" aria-hidden="true">
            <span className="skeleton-kicker">IMPACT VIEW</span>
            <span className="skeleton skeleton-small-line" />
            <span className="skeleton skeleton-large-block" />
            <span className="skeleton skeleton-medium-line" />
            <div className="skeleton-stats">
              {[0, 1, 2].map((item) => (
                <span key={item}>
                  <i className="skeleton skeleton-stat-value" />
                  <i className="skeleton skeleton-stat-label" />
                </span>
              ))}
            </div>
          </section>

          <section className="skeleton-card skeleton-issues" aria-hidden="true">
            <span className="skeleton-kicker">ISSUES DETECTED — LIST ONLY</span>
            <span className="skeleton skeleton-small-line skeleton-small-line--right" />
            <span className="skeleton skeleton-count" />
            <div className="skeleton-rows">
              {[0, 1, 2, 3, 4].map((item) => <span className="skeleton skeleton-row" key={item} />)}
            </div>
            <span className="skeleton skeleton-button" />
          </section>
        </div>
        <span className="sr-only">Loading analysis</span>
      </div>
    </main>
  )
}
