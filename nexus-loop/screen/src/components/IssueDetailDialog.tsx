import { FormEvent, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'
import type { DecisionRequest, DecisionVerdict, Finding, ScreenModel } from '../types'
import { AnalysisContext } from './AnalysisContext'
import { InfoPopover } from './InfoPopover'
import { IssueBento } from './IssueBento'
import { ReplayOutcome } from './ReplayOutcome'

type IssueDetailDialogProps = {
  finding: Finding | null
  screen: ScreenModel
  open: boolean
  notice?: string | null
  onClose: () => void
  onSubmit: (request: DecisionRequest) => Promise<void>
}

type DetailItem = { label: string; value: string }

const verdicts: Array<{ value: DecisionVerdict; label: string; quiet?: boolean }> = [
  { value: 'accepted', label: 'Approve' },
  { value: 'rejected', label: 'Reject' },
  { value: 'deferred', label: 'Defer', quiet: true },
]

const submitLabels: Record<DecisionVerdict, string> = {
  accepted: 'Approve and run live replay',
  rejected: 'Record rejection',
  deferred: 'Record deferral',
}

const savingLabels: Record<DecisionVerdict, string> = {
  accepted: 'Applying and replaying…',
  rejected: 'Recording rejection…',
  deferred: 'Recording deferral…',
}

function displayText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) {
    const items = value.map(displayText).filter((item): item is string => Boolean(item))
    return items.length ? items.join(' · ') : null
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const preferred = record.display ?? record.text ?? record.label ?? record.description ?? record.value
    if (preferred != null) return displayText(preferred)
    const entries = Object.entries(record)
      .map(([key, item]) => {
        const rendered = displayText(item)
        return rendered ? `${key.replaceAll('_', ' ')}: ${rendered}` : null
      })
      .filter((item): item is string => Boolean(item))
    return entries.length ? entries.join(' · ') : null
  }
  return null
}

function detailItems(items: Array<{ label: string; value: unknown }>): DetailItem[] {
  return items.flatMap((item) => {
    const value = displayText(item.value)
    return value ? [{ label: item.label, value }] : []
  })
}

function uniqueLines(values: unknown[]): string[] {
  return Array.from(new Set(values.map(displayText).filter((value): value is string => Boolean(value))))
}

export function IssueDetailDialog({ finding, screen, open, notice, onClose, onSubmit }: IssueDetailDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const firstVerdictRef = useRef<HTMLInputElement>(null)
  const receiptRef = useRef<HTMLElement>(null)
  const [verdict, setVerdict] = useState<DecisionVerdict | null>(null)
  const [name, setName] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingRecorded, setEditingRecorded] = useState(false)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      titleRef.current?.focus({ preventScroll: true })
    }
    if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    setError(null)
    setVerdict(null)
    setName('')
    setReason('')
    setEditingRecorded(false)
  }, [open, finding?.finding_id, finding?.proposal?.proposal_sha, finding?.approval?.state])

  if (!finding || !open) return null

  const proposal = finding.proposal
  const decision = proposal?.decision ?? {}
  const conciseTitle = finding.diagnosis?.label || finding.title
  const headerStatus = [finding.severity_label, finding.status.label].filter(Boolean).join(' · ')
  const issueContext = detailItems([
    { label: 'Full finding', value: finding.title !== conciseTitle ? finding.title : null },
    { label: 'Status detail', value: finding.status.sentence },
    { label: 'Report built', value: screen.built_at },
    { label: 'Report version', value: screen.source.report_version },
  ])

  const approvalRequest = displayText(decision.asking_approval_for)
  const proposalSummary = approvalRequest ?? displayText(proposal?.description)
  const proposalMeta = detailItems([
    { label: 'Description', value: approvalRequest ? proposal?.description : null },
    { label: 'Change type', value: proposal?.change_type },
    { label: 'Target', value: proposal?.target },
    { label: 'Owner', value: proposal?.owner },
    { label: 'Autonomy', value: proposal?.autonomy_rung },
  ])
  const predictionDetails = detailItems([
    { label: 'Predicted change', value: proposal?.predicted_delta },
    { label: 'Mechanism prediction', value: proposal?.mechanism_prediction },
    { label: 'Replay prediction', value: proposal?.replay_prediction },
    { label: 'Gap to standard', value: proposal?.standard_gap },
  ])
  const alternatives = uniqueLines(proposal?.alternatives ?? [])
  const hasTechnicalDetails = Boolean(
    proposalMeta.length
    || predictionDetails.length
    || alternatives.length,
  )
  const decisionDetails = detailItems([
    { label: 'Why no change is recommended', value: decision.why_no_action },
    { label: 'Downside if we are wrong', value: decision.risk_if_diagnosis_wrong },
    { label: 'Do not proceed if', value: decision.would_not_ship_if },
    { label: 'Trade-off', value: decision.trade_off },
  ])

  const detectionLines = uniqueLines((finding.evidence ?? []).map((item) => item.line))
  const detectionSet = new Set(detectionLines)
  const diagnosisLines = uniqueLines(finding.diagnosis?.evidence ?? [])
    .filter((line) => !detectionSet.has(line))
  const hasEvidence = Boolean(
    finding.impact.derivation
    || detectionLines.length
    || diagnosisLines.length,
  )
  const approvalState = finding.approval?.state ?? 'pending'
  const isRecorded = approvalState !== 'pending'
  const isAccepted = approvalState === 'accepted'
  const showDecisionForm = !isRecorded || editingRecorded
  const selectedSubmitLabel = verdict ? submitLabels[verdict] : 'Record decision'
  const savingLabel = verdict ? savingLabels[verdict] : 'Working…'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!proposal || !verdict) return
    if (!screen.source.generated_report_sha256) {
      setError('Decision not saved. The current report is missing its freshness hash.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSubmit({
        prescription_id: proposal.prescription_id,
        verdict,
        decided_by: name.trim(),
        reason: reason.trim(),
        proposal_sha: proposal.proposal_sha,
        generated_report_sha256: screen.source.generated_report_sha256,
      })
      setVerdict(null)
      setName('')
      setReason('')
      setEditingRecorded(false)
      window.setTimeout(() => receiptRef.current?.focus({ preventScroll: true }), 0)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setVerdict(null)
        setName('')
        setReason('')
      }
      setError(caught instanceof Error ? caught.message : 'Decision not saved.')
    } finally {
      setSaving(false)
    }
  }

  function startEditingDecision() {
    setError(null)
    setVerdict(null)
    setName('')
    setReason('')
    setEditingRecorded(true)
    window.setTimeout(() => firstVerdictRef.current?.focus({ preventScroll: true }), 0)
  }

  function cancelEditingDecision() {
    setError(null)
    setVerdict(null)
    setName('')
    setReason('')
    setEditingRecorded(false)
    window.setTimeout(() => receiptRef.current?.focus({ preventScroll: true }), 0)
  }

  return (
    <dialog
      id="issue-detail-dialog"
      ref={dialogRef}
      className="issue-dialog"
      tabIndex={-1}
      aria-labelledby="issue-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!saving) onClose()
      }}
      onClose={onClose}
      onClick={(event) => {
        if (!saving && event.target === dialogRef.current) onClose()
      }}
    >
      <article className="issue-dialog__panel">
        <header className="issue-dialog__header">
          <div className="issue-dialog__heading">
            {headerStatus && <span className="detail-eyebrow">{headerStatus}</span>}
            <div className="issue-dialog__title-row">
              <h2 id="issue-dialog-title" ref={titleRef} tabIndex={-1}>{conciseTitle}</h2>
              {issueContext.length ? (
                <InfoPopover label="Issue context" title="Issue context" placement="down-end">
                  <dl className="issue-context-list">
                    {issueContext.map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                </InfoPopover>
              ) : null}
            </div>
          </div>
          <button type="button" className="dialog-close" onClick={onClose} aria-label="Close issue review" disabled={saving}>×</button>
        </header>

        <div className="issue-dialog__content">
          <IssueBento finding={finding} />

          {proposal ? (
            <section className="proposal-panel" aria-labelledby="proposal-heading">
              <header className="proposal-panel__header">
                <div>
                  <span className="detail-eyebrow">Recommended action</span>
                  <h3 id="proposal-heading">{proposal.label ?? 'Review the proposed change'}</h3>
                </div>
                <div className="proposal-statuses" aria-label="Proposal status and details">
                  {displayText(finding.approval?.label) && <span className="proposal-status-chip">{displayText(finding.approval?.label)}</span>}
                  {hasTechnicalDetails ? (
                    <InfoPopover label="Proposal technical details" title="Proposal details" placement="down-end">
                      <div className="proposal-technical-details">
                        {proposalMeta.length ? (
                          <dl className="issue-context-list">
                            {proposalMeta.map((item) => (
                              <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>
                            ))}
                          </dl>
                        ) : null}
                        {predictionDetails.length ? (
                          <section>
                            <h4>Predictions and standard</h4>
                            <dl className="issue-context-list">
                              {predictionDetails.map((item) => (
                                <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>
                              ))}
                            </dl>
                          </section>
                        ) : null}
                        {alternatives.length ? (
                          <section>
                            <h4>Other paths considered</h4>
                            <ul className="evidence-list">
                              {alternatives.map((alternative) => <li key={alternative}>{alternative}</li>)}
                            </ul>
                            <p className="proposal-technical-note">These alternatives are context only. This decision applies to the recommended action shown here.</p>
                          </section>
                        ) : null}
                      </div>
                    </InfoPopover>
                  ) : null}
                </div>
              </header>

              {proposalSummary && <p className="proposal-ask">{proposalSummary}</p>}

              {decisionDetails.length ? (
                <dl className="decision-conditions">
                  {decisionDetails.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}

              {showDecisionForm ? (
                <form className="decision-form" aria-busy={saving} onSubmit={handleSubmit}>
                  <p className="decision-recording-note" id="decision-recording-note">
                    Approve applies the proposal in this session and runs a live sandbox replay. Reject or Defer only records the decision. Nothing is deployed to production.
                  </p>
                  <p className="decision-required-note" id="decision-required-note">
                    Choose one option. Your name and reason are required.
                  </p>
                  <fieldset disabled={saving} aria-describedby="decision-recording-note decision-required-note">
                    <legend>{editingRecorded ? 'Change recorded decision' : 'Record your decision'}</legend>
                    <div className="verdict-options">
                      {verdicts.map((option) => (
                        <label
                          className={option.quiet ? 'verdict-option verdict-option--quiet' : 'verdict-option'}
                          key={option.value}
                        >
                          <input
                            ref={option.value === 'accepted' ? firstVerdictRef : undefined}
                            type="radio"
                            name="verdict"
                            value={option.value}
                            required
                            checked={verdict === option.value}
                            onChange={() => setVerdict(option.value)}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <div className="decision-fields">
                    <label>
                      Your name
                      <input required disabled={saving} maxLength={2000} value={name} onChange={(event) => setName(event.target.value)} />
                    </label>
                    <label>
                      Reason
                      <textarea required disabled={saving} maxLength={2000} rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
                    </label>
                  </div>
                  {saving ? (
                    <section className="live-decision-status" role="status" aria-live="polite" aria-atomic="true">
                      <span className="live-decision-status__indicator" aria-hidden="true" />
                      <div>
                        <strong>
                          {verdict === 'accepted'
                            ? 'Approval is running live in the background'
                            : `${verdict === 'rejected' ? 'Rejection' : 'Deferral'} is being recorded`}
                        </strong>
                        <p>
                          {verdict === 'accepted'
                            ? 'The backend is applying the approved proposal for this session and running replay. Keep this review open for the result.'
                            : 'No change will be applied and no replay will run.'}
                        </p>
                      </div>
                    </section>
                  ) : null}
                  {(error || notice) && <p className="form-error" role="alert" tabIndex={-1}>{error || notice}</p>}
                  <div className="decision-actions">
                    {editingRecorded ? (
                      <button type="button" className="decision-cancel" disabled={saving} onClick={cancelEditingDecision}>
                        Cancel
                      </button>
                    ) : <span />}
                    <button type="submit" disabled={saving || !verdict || !name.trim() || !reason.trim()}>
                      {saving ? savingLabel : selectedSubmitLabel}
                    </button>
                  </div>
                </form>
              ) : (
                <section ref={receiptRef} className="decision-receipt" data-state={approvalState} aria-label="Recorded decision" aria-live="polite" tabIndex={-1}>
                  <div className="decision-receipt__header">
                    <div>
                      <span className="detail-eyebrow">Recorded decision</span>
                      {finding.approval?.label && <strong>{finding.approval.label}</strong>}
                    </div>
                    <button type="button" onClick={startEditingDecision}>Change decision</button>
                  </div>
                  {finding.approval?.reason && <p>{finding.approval.reason}</p>}
                  <div className="decision-receipt__meta">
                    {finding.approval?.decided_by && <span>Recorded by {finding.approval.decided_by}</span>}
                    {finding.approval?.at && <time dateTime={finding.approval.at}>{finding.approval.at}</time>}
                  </div>
                  <p className="decision-receipt__note">
                    {isAccepted
                      ? 'Applied for this session’s sandbox replay only. Nothing was deployed to production.'
                      : 'Recorded for this session. No change was applied and no replay was run.'}
                  </p>
                </section>
              )}

              {isAccepted && !saving ? <ReplayOutcome verification={finding.verification} /> : null}
            </section>
          ) : null}

          <footer className="issue-dialog__footer">
            {hasEvidence ? (
              <details className="detail-disclosure issue-evidence">
                <summary>Evidence</summary>
                <div className="issue-evidence__body">
                  {finding.impact.derivation ? (
                    <section>
                      <h3>Impact calculation</h3>
                      <p>{finding.impact.derivation}</p>
                    </section>
                  ) : null}

                  {detectionLines.length ? (
                    <section>
                      <h3>Detection evidence</h3>
                      <ul className="evidence-list">
                        {detectionLines.map((line) => <li key={line}>{line}</li>)}
                      </ul>
                    </section>
                  ) : null}

                  {diagnosisLines.length ? (
                    <section>
                      <h3>Diagnosis evidence</h3>
                      <ul className="evidence-list">
                        {diagnosisLines.map((line) => <li key={line}>{line}</li>)}
                      </ul>
                    </section>
                  ) : null}
                </div>
              </details>
            ) : null}
            <AnalysisContext screen={screen} />
          </footer>
        </div>
      </article>
    </dialog>
  )
}
