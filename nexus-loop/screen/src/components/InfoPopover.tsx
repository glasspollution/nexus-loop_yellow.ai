import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

type InfoPopoverProps = {
  label: string
  title?: string
  children: ReactNode
  placement?: 'down' | 'down-end' | 'up-end'
  className?: string
}

export function InfoPopover({
  label,
  title = label,
  children,
  placement = 'down',
  className = '',
}: InfoPopoverProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  function closeAndRestoreFocus() {
    setOpen(false)
    window.setTimeout(() => triggerRef.current?.focus(), 0)
  }

  useEffect(() => {
    if (!open) return

    function closeFromOutside(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }

    function closeFromKeyboard(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      closeAndRestoreFocus()
    }

    document.addEventListener('pointerdown', closeFromOutside)
    document.addEventListener('keydown', closeFromKeyboard)
    return () => {
      document.removeEventListener('pointerdown', closeFromOutside)
      document.removeEventListener('keydown', closeFromKeyboard)
    }
  }, [open])

  return (
    <div
      ref={rootRef}
      className={`info-popover info-popover--${placement}${className ? ` ${className}` : ''}`}
    >
      <button
        ref={triggerRef}
        type="button"
        className="info-popover__trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">i</span>
      </button>
      {open && (
        <div id={panelId} className="info-popover__panel" role="region" aria-label={title}>
          <div className="info-popover__header">
            <strong className="info-popover__title">{title}</strong>
            <button
              type="button"
              className="info-popover__close"
              aria-label={`Close ${title}`}
              onClick={closeAndRestoreFocus}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
          <div className="info-popover__content">{children}</div>
        </div>
      )}
    </div>
  )
}
