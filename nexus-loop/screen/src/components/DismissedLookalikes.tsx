import { useEffect, useId, useRef, useState } from 'react'
import type { DismissedFinding } from '../types'

type DismissedLookalikesProps = {
  count?: number
  items?: DismissedFinding[]
  tone?: 'dark' | 'light'
}

function windowLabel(window: DismissedFinding['window']) {
  if (window?.from_day != null && window.to_day != null) return `Days ${window.from_day}–${window.to_day}`
  if (window?.from_day != null) return `From day ${window.from_day}`
  if (window?.to_day != null) return `Through day ${window.to_day}`
  return null
}

export function DismissedLookalikes({ count, items = [], tone = 'dark' }: DismissedLookalikesProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const displayCount = count ?? items.length

  function resetPanel() {
    if (!panelRef.current) return
    panelRef.current.scrollTop = 0
    panelRef.current.querySelectorAll<HTMLDetailsElement>('details[open]').forEach((details) => {
      details.open = false
    })
  }

  function closeAndRestoreFocus() {
    resetPanel()
    setOpen(false)
    window.setTimeout(() => triggerRef.current?.focus(), 0)
  }

  useEffect(() => {
    if (!open) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      resetPanel()
      setOpen(false)
      triggerRef.current?.focus()
    }

    function handlePointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        resetPanel()
        setOpen(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handlePointerDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [open])

  if (displayCount <= 0 || items.length === 0) return null

  const countLabel = `${displayCount} ${displayCount === 1 ? 'lookalike' : 'lookalikes'} ruled out by the engine`

  return (
    <div className={`dismissed-lookalikes dismissed-lookalikes--${tone}`} ref={rootRef}>
      <button
        type="button"
        className="dismissed-lookalikes__trigger"
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={countLabel}
        onClick={() => {
          resetPanel()
          setOpen((current) => !current)
        }}
      >
        <span className="dismissed-lookalikes__trigger-copy">
          <strong>{displayCount} {displayCount === 1 ? 'lookalike' : 'lookalikes'} ruled out</strong>
        </span>
        <span className="dismissed-lookalikes__chevron" aria-hidden="true">→</span>
      </button>

      <section
        className="dismissed-lookalikes__panel"
        id={panelId}
        aria-label="Lookalikes ruled out by the engine"
        hidden={!open}
        ref={panelRef}
      >
        <div className="dismissed-lookalikes__panel-header">
          <div>
            <span>Engine checks</span>
            <h3>{displayCount} {displayCount === 1 ? 'lookalike' : 'lookalikes'} ruled out</h3>
          </div>
          <button type="button" onClick={closeAndRestoreFocus} aria-label="Close dismissed lookalikes">×</button>
        </div>
        <p className="dismissed-lookalikes__intro">Examined patterns that the engine did not classify as regressions.</p>

        <div className="dismissed-lookalikes__list">
          {items.map((item) => {
            const period = windowLabel(item.window)
            return (
              <details className="dismissed-lookalike" key={item.finding_id}>
                <summary>
                  <span className="dismissed-lookalike__mark" aria-hidden="true">✓</span>
                  <span className="dismissed-lookalike__summary-copy">
                    <strong>{item.label}</strong>
                    <span>
                      {[item.tenant, item.slice, period].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                  <span className="dismissed-lookalike__row-chevron" aria-hidden="true">›</span>
                </summary>
                <div className="dismissed-lookalike__body">
                  {item.why_not_a_problem && <p>{item.why_not_a_problem}</p>}
                  {Boolean(item.evidence?.length) && (
                    <details className="dismissed-lookalike__evidence">
                      <summary>Evidence</summary>
                      <ul>
                        {item.evidence?.map((line, index) => <li key={index}>{line}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
              </details>
            )
          })}
        </div>
      </section>
    </div>
  )
}
