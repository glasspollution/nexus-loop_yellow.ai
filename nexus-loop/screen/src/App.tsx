import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, loadScreen, saveDecision } from './api'
import { DashboardSkeleton } from './components/DashboardSkeleton'
import { DefinedValue } from './components/DefinedValue'
import { DismissedLookalikes } from './components/DismissedLookalikes'
import { IssueDetailDialog } from './components/IssueDetailDialog'
import type { DecisionRequest, Finding, ImpactFigure, ScreenModel } from './types'

const mainFigureOrder = [
  'impact.cost_excess',
  'impact.lost_resolutions',
  'impact.extra_minutes',
  'impact.unplanned_handoffs_excess',
  'impact.hit',
  'impact.exposed',
]

const supportFigureOrder = [
  'impact.exposed',
  'impact.share',
  'impact.extra_turns',
  'impact.unplanned_handoffs_excess',
  'impact.hit',
]

function findFigure(finding: Finding, definitionId: string) {
  return finding.impact.figures.find((figure) => figure.def === definitionId)
}

function usableFigure(figure: ImpactFigure | undefined) {
  return figure && figure.display != null && figure.display !== 'n/a'
}

function primaryFigure(finding: Finding) {
  return mainFigureOrder
    .map((definitionId) => findFigure(finding, definitionId))
    .find(usableFigure) ?? finding.impact.figures.find(usableFigure)
}

function supportFigures(finding: Finding, primary: ImpactFigure | undefined) {
  const selected: ImpactFigure[] = []
  for (const definitionId of supportFigureOrder) {
    const figure = findFigure(finding, definitionId)
    if (usableFigure(figure) && figure !== primary && !selected.includes(figure!)) selected.push(figure!)
    if (selected.length === 3) break
  }
  return selected
}

function reportSubtitle(screen: ScreenModel) {
  const reviewWindow = screen.header.days != null
    ? `the latest ${screen.header.days} days of`
    : 'the latest'
  return `We reviewed ${reviewWindow} customer conversations, tools, handoffs, and outcomes.`
}

function ProfileIcon() {
  return (
    <span className="profile-icon" role="img" aria-label="User profile">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="8.25" r="3.25" />
        <path d="M5.5 20c.65-4.1 3.05-6.15 6.5-6.15s5.85 2.05 6.5 6.15" />
      </svg>
    </span>
  )
}

function ReportHeader({ screen }: { screen: ScreenModel }) {
  return (
    <header className="intro-header">
      <div className="intro-copy">
        <h1>
          <span>Hi there.</span>
          <span>Your latest agent report is ready.</span>
        </h1>
        <p>{reportSubtitle(screen)}</p>
      </div>
      <ProfileIcon />
    </header>
  )
}

function EmptyDashboard({ screen }: { screen: ScreenModel }) {
  return (
    <main className="page-shell empty-shell">
      <div className="dashboard-frame empty-frame">
        <ReportHeader screen={screen} />
        <section className="empty-card">
          <span aria-hidden="true">✓</span>
          <h2>Your latest analysis is clear</h2>
          <p>The engine found no issues requiring a decision.</p>
          <DismissedLookalikes
            count={screen.summary.dismissed}
            items={screen.dismissed}
            tone="light"
          />
        </section>
      </div>
    </main>
  )
}

function Dashboard({
  screen,
  selected,
  onPreview,
  onSelect,
}: {
  screen: ScreenModel
  selected: Finding
  onPreview: (id: string) => void
  onSelect: (id: string) => void
}) {
  const primary = primaryFigure(selected)
  const supporting = supportFigures(selected, primary)

  return (
    <main className="page-shell">
      <div className="dashboard-frame">
        <ReportHeader screen={screen} />

        {Boolean(screen.summary.needs_reconfirmation?.length) && (
          <div className="reconfirmation-alert" role="status">
            A previous decision needs confirmation because its proposal changed.
          </div>
        )}

        <div className="overview-grid">
          <section className="impact-card" aria-labelledby="impact-title">
            <div className="eyebrow" id="impact-title"><span />What it is costing you</div>
            <div className="impact-hero">
              <DefinedValue figure={primary} size="hero" />
              <span>{primary?.label ?? 'Reported impact'}<br />{selected.status.label}</span>
            </div>
            <p className="impact-summary">{selected.status.sentence || selected.if_nothing_changes || selected.headline}</p>
            <div className="impact-divider" />
            <div className="impact-stats">
              {supporting.map((figure) => (
                <div className="impact-stat" key={figure.def}>
                  <DefinedValue figure={figure} size="stat" />
                  <span>{figure.label}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="issues-card" aria-labelledby="issues-title">
            <div className="issues-content">
              <div className="issues-topline">
                <span id="issues-title">Issues detected</span>
                <span>{screen.summary.decisions_pending} pending</span>
              </div>
              <strong className="issues-count">{String(screen.summary.regressions).padStart(2, '0')}</strong>
              <p className="issues-intro">Prioritized for review. Open one to see the full evidence.</p>

              <ol className="issue-list" aria-label="Detected issues">
                {screen.findings.map((finding, index) => {
                  const isSelected = finding.finding_id === selected.finding_id
                  return (
                    <li key={finding.finding_id}>
                      <button
                        type="button"
                        className="issue-row"
                        data-selected={isSelected ? 'true' : 'false'}
                        onMouseEnter={() => onPreview(finding.finding_id)}
                        onFocus={() => onPreview(finding.finding_id)}
                        onClick={() => onSelect(finding.finding_id)}
                        aria-current={isSelected ? 'true' : undefined}
                        aria-haspopup="dialog"
                        aria-controls="issue-detail-dialog"
                        aria-label={`${finding.title}. ${finding.status.label}`}
                      >
                        <span className="issue-number">{String(index + 1).padStart(2, '0')}</span>
                        <span className="issue-title">{finding.diagnosis?.label ?? finding.title}</span>
                        <span className={`status-pill status-pill--${finding.status.state || 'unknown'}`}>
                          {finding.status.label}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ol>

              <DismissedLookalikes count={screen.summary.dismissed} items={screen.dismissed} />
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}

export default function App() {
  const [screen, setScreen] = useState<ScreenModel | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [decisionAlert, setDecisionAlert] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const dialogTriggerRef = useRef<HTMLElement | null>(null)

  const refresh = useCallback(async (signal?: AbortSignal): Promise<ScreenModel | null> => {
    setLoading(true)
    setError(null)
    try {
      const next = await loadScreen(signal)
      setScreen(next)
      setSelectedId((current) => next.findings.some((finding) => finding.finding_id === current)
        ? current
        : next.findings[0]?.finding_id ?? null)
      return next
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return null
      setError(caught instanceof Error ? caught.message : 'The analysis could not be loaded.')
      return null
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [refresh])

  const selected = useMemo(
    () => screen?.findings.find((finding) => finding.finding_id === selectedId) ?? screen?.findings[0] ?? null,
    [screen, selectedId],
  )

  function openDialog(id?: string) {
    if (id) setSelectedId(id)
    setNotice(null)
    setDecisionAlert(null)
    dialogTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setDialogOpen(true)
  }

  function closeDialog() {
    setDialogOpen(false)
    window.setTimeout(() => dialogTriggerRef.current?.focus(), 0)
  }

  async function handleDecision(request: DecisionRequest) {
    try {
      const next = await saveDecision(request)
      setScreen(next)
      setDecisionAlert(null)
      setNotice(request.verdict === 'accepted'
        ? 'Approval completed. The screen now shows the backend’s live apply and replay outcome.'
        : `${request.verdict === 'rejected' ? 'Rejection' : 'Deferral'} recorded for this session. No change was applied.`)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        const reviewedFindingId = selected?.finding_id
        const refreshed = await refresh()
        if (!refreshed) throw new ApiError('The evidence changed, but the latest analysis could not be loaded.', 409)
        if (!reviewedFindingId || !refreshed.findings.some((finding) => finding.finding_id === reviewedFindingId)) {
          closeDialog()
          setNotice('The proposal changed and is no longer in the latest analysis.')
          return
        }
        const message = 'This proposal changed. Review the updated recommendation before recording a new decision.'
        setDecisionAlert(message)
        setNotice('The proposal changed. The latest evidence is loaded; please review it again.')
        throw new ApiError(message, 409)
      }
      throw caught
    }
  }

  if (loading && !screen) return <DashboardSkeleton />

  if (error && !screen) {
    return (
      <main className="state-shell">
        <div className="state-card" role="alert">
          <span className="state-mark" aria-hidden="true">!</span>
          <h1>We couldn’t load the review</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void refresh()}>Try again</button>
        </div>
      </main>
    )
  }

  if (!screen) return null
  if (!selected) return <EmptyDashboard screen={screen} />

  return (
    <>
      <Dashboard
        screen={screen}
        selected={selected}
        onPreview={setSelectedId}
        onSelect={(id) => openDialog(id)}
      />
      <IssueDetailDialog
        finding={selected}
        screen={screen}
        open={dialogOpen}
        notice={decisionAlert}
        onClose={closeDialog}
        onSubmit={handleDecision}
      />
      <div className="sr-only" role="status" aria-live="polite">
        {error || notice || (loading ? 'Refreshing analysis' : '')}
      </div>
    </>
  )
}
