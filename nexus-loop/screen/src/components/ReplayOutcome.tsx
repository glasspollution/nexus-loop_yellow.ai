import type { Verification } from '../types'
import { InfoPopover } from './InfoPopover'

type ReplayOutcomeProps = {
  verification: Verification | null | undefined
}

type TechnicalRow = {
  label: string
  value: string
}

function textValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) {
    const values = value.map(textValue).filter((item): item is string => Boolean(item))
    return values.length ? values.join('–') : null
  }
  if (value && typeof value === 'object') {
    const values = Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const rendered = textValue(item)
        return rendered ? `${key.replaceAll('_', ' ')}: ${rendered}` : null
      })
      .filter((item): item is string => Boolean(item))
    return values.length ? values.join(' · ') : null
  }
  return null
}

function technicalRows(items: Array<{ label: string; value: unknown }>): TechnicalRow[] {
  return items.flatMap(({ label, value }) => {
    const rendered = textValue(value)
    return rendered ? [{ label, value: rendered }] : []
  })
}

export function ReplayOutcome({ verification }: ReplayOutcomeProps) {
  const gate = textValue(verification?.gate)
  const verdict = textValue(verification?.verdict)
  const isUnavailable = !verification || gate === 'unverified' || (!verdict && verification.before == null && verification.after == null)
  const before = textValue(verification?.before_display)
  const after = textValue(verification?.after_display)
  const metric = textValue(verification?.metric_label)
  const gateLabel = textValue(verification?.gate_label)
  const verdictLabel = textValue(verification?.verdict_label)
  const gateReason = textValue(verification?.gate_reason)
  const noEffectMeaning = textValue(verification?.no_effect_meaning)
  const unverifiedReason = textValue(verification?.reason)
  const details = technicalRows([
    { label: 'Simulation disclosure', value: verification?.simulation_note },
    { label: 'Metric', value: verification?.metric },
    { label: 'Before', value: verification?.before_display },
    { label: 'After', value: verification?.after_display },
    { label: 'Predicted change', value: verification?.predicted_delta_display },
    { label: 'Observed change', value: verification?.observed_delta_display },
    { label: 'Prediction error', value: verification?.prediction_error_display },
    { label: 'Replay window', value: verification?.replayed_window },
    { label: 'Golden-set version', value: verification?.golden_set_version },
    { label: 'Golden conversations replayed', value: verification?.golden_set_replayed },
    { label: 'Golden conversations regressed', value: verification?.golden_set_regressed },
    { label: 'Sessions replayed (simulated)', value: verification?.sessions_replayed_simulated },
    { label: 'Replay run', value: verification?.replay_run_id },
    { label: 'Loaded from cache', value: verification?.from_cache },
    { label: 'Runs used', value: verification?.runs_used },
  ])

  return (
    <section
      className="replay-outcome"
      data-gate={gate ?? 'unverified'}
      aria-label="Live apply and replay outcome"
    >
      <header className="replay-outcome__header">
        <div>
          <span className="detail-eyebrow">Live apply &amp; replay outcome</span>
          <strong className="replay-outcome__title">
            {isUnavailable ? (gateLabel ?? 'Replay unavailable') : (verdictLabel ?? gateLabel ?? 'Replay result available')}
          </strong>
        </div>
        <div className="replay-outcome__status">
          {!isUnavailable && gateLabel && gateLabel !== verdictLabel ? <span>{gateLabel}</span> : null}
          {details.length ? (
            <InfoPopover label="Replay technical details" title="Replay details" placement="up-end">
              <dl className="issue-context-list">
                {details.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </InfoPopover>
          ) : null}
        </div>
      </header>

      {isUnavailable ? (
        <p className="replay-outcome__explanation">
          {unverifiedReason ?? 'The backend did not return a replay result for this approved session run.'}
        </p>
      ) : (
        <>
          {(before || after) ? (
            <div className="replay-outcome__comparison" aria-label={metric ? `Replay metric: ${metric}` : 'Replay before and after'}>
              <div>
                <span>Before</span>
                <strong>{before ?? 'Not provided'}</strong>
              </div>
              <span className="replay-outcome__arrow" aria-hidden="true">→</span>
              <div>
                <span>After</span>
                <strong>{after ?? 'Not provided'}</strong>
              </div>
              {metric ? <span className="replay-outcome__metric">{metric}</span> : null}
            </div>
          ) : null}
          {verification?.golden_set_pass != null ? (
            <p className="replay-outcome__golden">
              {verification.golden_set_pass ? 'Golden conversations held.' : 'Golden conversations regressed.'}
            </p>
          ) : null}
          {gateReason ? <p className="replay-outcome__explanation">{gateReason}</p> : null}
          {noEffectMeaning && noEffectMeaning !== gateReason ? (
            <p className="replay-outcome__explanation replay-outcome__explanation--secondary">{noEffectMeaning}</p>
          ) : null}
        </>
      )}

      <p className="replay-outcome__disclaimer">
        {isUnavailable
          ? 'The approval was recorded, but replay did not return a result. Nothing was deployed to production.'
          : 'Run after approval in this session using the sandbox replay. Nothing was deployed to production.'}
      </p>
    </section>
  )
}
