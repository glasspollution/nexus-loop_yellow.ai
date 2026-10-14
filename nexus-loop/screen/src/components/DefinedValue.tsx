import { useId, useState } from 'react'
import type { ImpactFigure } from '../types'

type DefinedValueProps = {
  figure?: ImpactFigure
  size?: 'hero' | 'stat' | 'detail'
  fallback?: string
}

function describeWindow(window: ImpactFigure['window']) {
  if (!window?.length) return null
  return window.join(' – ')
}

function metaText(value: unknown): string | null {
  if (value == null || value === '') return null
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(metaText).filter(Boolean).join(' – ')
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const preferred = record.display ?? record.label ?? record.text ?? record.value
    if (preferred != null) return String(preferred)
    return Object.entries(record).map(([key, item]) => `${key}: ${metaText(item)}`).join(' · ')
  }
  return String(value)
}

export function DefinedValue({ figure, size = 'stat', fallback = 'n/a' }: DefinedValueProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const display = figure?.display ?? fallback
  const definition = figure?.metric_definition?.definition ?? figure?.definition
  const fidelity = figure?.metric_definition?.fidelity ?? figure?.fidelity
  const window = describeWindow(figure?.window)
  const coverage = metaText(figure?.metric_definition?.coverage ?? figure?.coverage)
  const calibration = metaText(figure?.metric_definition?.calibration)
  const baseline = figure?.baseline
    ? [figure.baseline.label, figure.baseline.display, figure.baseline.n != null ? `n=${figure.baseline.n}` : null]
        .filter(Boolean).join(' · ')
    : null
  const interval = figure?.ci95?.length ? figure.ci95.map(String).join(' – ') : null
  const hasDetails = Boolean(definition || fidelity || window || coverage || calibration || baseline || interval || figure?.predicate)

  if (!hasDetails) {
    return <span className={`defined-value defined-value--${size}`}>{display}</span>
  }

  return (
    <span className={`definition-wrap definition-wrap--${size}`}>
      <button
        type="button"
        className={`defined-value defined-value--${size}`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        aria-label={`${figure?.label ?? 'Value'}: ${display}. Show definition`}
        onClick={() => setOpen((value) => !value)}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget)) setOpen(false)
        }}
      >
        {display}
      </button>
      {open && (
        <span className="definition-popover" id={id} role="tooltip" tabIndex={-1}>
          <strong>{figure?.label ?? 'Definition'}</strong>
          {definition && <span>{definition}</span>}
          <span className="definition-meta">
            {figure?.unit && <span>Unit {figure.unit}</span>}
            {fidelity && <span>{fidelity}</span>}
            {window && <span>Window {window}</span>}
            {coverage && <span>Coverage {coverage}</span>}
            {calibration && <span>Calibration {calibration}</span>}
            {baseline && <span>Baseline {baseline}</span>}
            {interval && <span>95% interval {interval}</span>}
            {figure?.predicate && <span>Affected when {figure.predicate}</span>}
          </span>
        </span>
      )}
    </span>
  )
}
