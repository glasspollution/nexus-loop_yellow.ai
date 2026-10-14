import type { ReactNode } from 'react'
import type { ScreenModel } from '../types'
import { InfoPopover } from './InfoPopover'

type DataRecord = Record<string, unknown>

function asRecords(value: unknown): DataRecord[] {
  return Array.isArray(value) ? value.filter((item): item is DataRecord => Boolean(item && typeof item === 'object')) : []
}

function labelFor(key: string) {
  return key.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function PlainValue({ value }: { value: unknown }): ReactNode {
  if (value == null || value === '') return null
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>
  if (typeof value === 'string' || typeof value === 'number') return <span>{String(value)}</span>
  if (Array.isArray(value)) {
    return (
      <ul>
        {value.map((item, index) => <li key={index}><PlainValue value={item} /></li>)}
      </ul>
    )
  }
  if (typeof value === 'object') {
    return (
      <dl>
        {Object.entries(value as DataRecord).map(([key, item]) => (
          <div key={key}>
            <dt>{labelFor(key)}</dt>
            <dd><PlainValue value={item} /></dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span>{String(value)}</span>
}

function ContextList({ items }: { items: unknown[] }) {
  if (!items.length) return null
  return (
    <div className="context-list">
      {items.map((item, index) => {
        const record = item && typeof item === 'object' ? item as DataRecord : null
        const title = record?.label ?? record?.text ?? record?.name ?? record?.ask_id ?? `Item ${index + 1}`
        return (
          <article key={index}>
            <strong>{String(title)}</strong>
            <PlainValue value={record ? Object.fromEntries(Object.entries(record).filter(([key]) => !['label', 'text', 'name'].includes(key))) : item} />
          </article>
        )
      })}
    </div>
  )
}

export function AnalysisContext({ screen }: { screen: ScreenModel }) {
  const refusals = screen.refusals ?? {}
  const standard = screen.standard ?? {}
  const refusedQuestions = asRecords(refusals.questions)
  const refusedBreakdowns = Array.isArray(refusals.breakdowns) ? refusals.breakdowns : []
  const catalogContradictions = Array.isArray(refusals.catalog_contradictions) ? refusals.catalog_contradictions : []
  const disclosureGroups = Object.entries(screen.disclosures ?? {}).filter(([, items]) => items.length)
  const hasStandard = Object.keys(standard).length > 0
  const hasContext = Boolean(
    refusedQuestions.length
    || refusedBreakdowns.length
    || catalogContradictions.length
    || screen.asks?.length
    || screen.metrics?.length
    || hasStandard
    || screen.self_assessment
    || disclosureGroups.length,
  )

  if (!hasContext) return null

  return (
    <InfoPopover
      label="About this analysis"
      title="About this analysis"
      placement="up-end"
      className="analysis-context"
    >
      <div className="analysis-context__body">
        {(refusedQuestions.length || refusedBreakdowns.length || catalogContradictions.length) ? (
          <section>
            <h3>Limits and refusals</h3>
            <ContextList items={refusedQuestions} />
            {refusedBreakdowns.length ? <h4>Refused breakdowns</h4> : null}
            <ContextList items={refusedBreakdowns} />
            {catalogContradictions.length ? <h4>Catalog contradictions</h4> : null}
            <ContextList items={catalogContradictions} />
          </section>
        ) : null}

        {screen.asks?.length ? (
          <section>
            <h3>Operator questions</h3>
            <ContextList items={screen.asks} />
          </section>
        ) : null}

        {screen.metrics?.length ? (
          <section>
            <h3>Metric coverage</h3>
            <ContextList items={screen.metrics} />
          </section>
        ) : null}

        {hasStandard ? (
          <section>
            <h3>Standard and golden set</h3>
            <PlainValue value={standard} />
          </section>
        ) : null}

        {screen.self_assessment ? (
          <section>
            <h3>Self-assessment</h3>
            <PlainValue value={screen.self_assessment} />
          </section>
        ) : null}

        {disclosureGroups.length ? (
          <section>
            <h3>What is real, simulated, and not yet built</h3>
            <div className="disclosure-grid">
              {disclosureGroups.map(([group, items]) => (
                <article key={group}>
                  <strong>{labelFor(group)}</strong>
                  <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </InfoPopover>
  )
}
