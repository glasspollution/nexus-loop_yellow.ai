import type { Finding, ImpactFigure } from '../types'
import { DefinedValue } from './DefinedValue'
import { InfoPopover } from './InfoPopover'

const outcomeFigureOrder = [
  'impact.lost_resolutions',
  'impact.unplanned_handoffs_excess',
  'impact.abandoned_excess',
  'impact.hit',
  'impact.exposed',
]

const behaviourFigureOrder = [
  'impact.extra_minutes',
  'impact.extra_turns',
  'impact.cost_excess',
  'impact.hit',
  'impact.exposed',
]

function figureById(finding: Finding, definitionId: string) {
  return finding.impact.figures.find((figure) => figure.def === definitionId)
}

function hasDisplay(figure: ImpactFigure | undefined): figure is ImpactFigure {
  return Boolean(figure?.display && figure.display !== 'n/a')
}

function firstAvailable(finding: Finding, ids: string[]) {
  return ids.map((id) => figureById(finding, id)).find(hasDisplay)
}

function primaryImpact(finding: Finding) {
  const order = finding.impact.harm === 'behaviour' ? behaviourFigureOrder : outcomeFigureOrder
  return firstAvailable(finding, order)
}

function valueText(value: unknown) {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number') return String(value)
  return null
}

type InfoRow = { label: string; value: string }

function infoRows(items: Array<{ label: string; value: unknown }>): InfoRow[] {
  return items.flatMap((item) => {
    const value = Array.isArray(item.value)
      ? item.value.filter((part) => part != null && part !== '').join('–')
      : valueText(item.value)
    return value ? [{ label: item.label, value }] : []
  })
}

function InfoList({ rows }: { rows: InfoRow[] }) {
  return (
    <dl className="issue-context-list">
      {rows.map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function IssueBento({ finding }: { finding: Finding }) {
  const hero = primaryImpact(finding)
  const mechanism = figureById(finding, 'impact.mechanism')
  const duration = figureById(finding, 'impact.days_running')
  const mechanismLabel = mechanism?.metric_definition?.label ?? mechanism?.label
  const confidence = valueText(finding.diagnosis?.confidence)
  const diagnosis = finding.diagnosis?.label
  const change = finding.diagnosis?.config_change
  const heroInfo = infoRows([
    { label: 'Tenant', value: finding.tenant },
    { label: 'Scope', value: finding.slice },
    { label: 'Engine summary', value: finding.headline },
  ])
  const signalInfo = mechanism ? infoRows([
    { label: 'Definition', value: mechanism.metric_definition?.definition ?? mechanism.definition },
    { label: 'Baseline value', value: mechanism.baseline?.display },
    { label: 'Baseline reference', value: mechanism.baseline?.label },
    { label: 'Baseline sample', value: mechanism.baseline?.n },
    { label: 'Window', value: mechanism.window },
  ]) : []
  const diagnosisInfo = infoRows([
    { label: 'Confidence', value: confidence },
    { label: 'Change type', value: change?.kind },
    { label: 'Target', value: change?.target },
    { label: 'Changed', value: change?.day },
    { label: 'From', value: change?.from },
    { label: 'To', value: change?.to },
    { label: 'Source', value: change?.source },
    { label: 'Note', value: change?.note },
  ])

  return (
    <section className="issue-bento" aria-label="Issue detection and diagnosis summary">
      {hero && (
        <article className="issue-bento__hero">
          <div className="issue-bento__card-head">
            <span className="issue-bento__tag">Measured impact</span>
            {heroInfo.length ? (
              <InfoPopover label="Impact context" title="Impact context" placement="down-end">
                <InfoList rows={heroInfo} />
              </InfoPopover>
            ) : null}
          </div>
          <div className="issue-bento__hero-value">
            <DefinedValue figure={hero} size="detail" />
            {hero.label && <span>{hero.label}</span>}
          </div>
        </article>
      )}

      {mechanism && hasDisplay(mechanism) && (
        <article className="issue-bento__signal">
          <div>
            <div className="issue-bento__card-head">
              <span className="issue-bento__kicker">Detected signal</span>
              {signalInfo.length ? (
                <InfoPopover label="Signal details" title="Signal details" placement="down-end">
                  <InfoList rows={signalInfo} />
                </InfoPopover>
              ) : null}
            </div>
            <div className="issue-bento__signal-value">
              <DefinedValue figure={mechanism} size="detail" />
            </div>
            {mechanismLabel && <p>{mechanismLabel}</p>}
          </div>
        </article>
      )}

      <div className="issue-bento__lower">
        {duration && hasDisplay(duration) && (
          <article className="issue-bento__duration">
            <div className="issue-bento__duration-value">
              <DefinedValue figure={duration} size="detail" />
            </div>
            {finding.status.label && <span>{finding.status.label}</span>}
          </article>
        )}

        {diagnosis && (
          <article className="issue-bento__diagnosis">
            <span className="issue-bento__diagnosis-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="m12 3 2.2 5.1 5.4.5-4.1 3.6 1.2 5.3-4.7-2.8-4.7 2.8 1.2-5.3-4.1-3.6 5.4-.5L12 3Z" />
              </svg>
            </span>
            <div>
              <div className="issue-bento__card-head">
                <span className="issue-bento__kicker">Diagnosis</span>
                {diagnosisInfo.length ? (
                  <InfoPopover label="Diagnosis details" title="Diagnosis details" placement="down-end">
                    <InfoList rows={diagnosisInfo} />
                  </InfoPopover>
                ) : null}
              </div>
              <strong>{diagnosis}</strong>
            </div>
          </article>
        )}
      </div>
    </section>
  )
}
