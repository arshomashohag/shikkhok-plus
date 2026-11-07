/**
 * The shared pieces every screen is built from.
 *
 * **These render decisions; they do not make them.** A chip is told
 * which state it is in by a mapper that read the server's answer
 * [TC-9] — nothing here compares an amount or a date.
 */
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import type { ApiError } from '../api/errors'
import { useT } from '../i18n/i18n'
import type { Money } from '../core/money'
import { formatShortDate } from '../core/format'
import {
  BackIcon,
  CheckCircleIcon,
  CircleIcon,
  ClockIcon,
  CloudOffIcon,
  HalfCircleIcon,
  WarningIcon,
} from './icons'

// ---------------------------------------------------------------- top bar

export function TopBar({
  title,
  subtitle,
  back,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  back?: string | true
  actions?: ReactNode
}) {
  const navigate = useNavigate()
  const { t } = useT()
  useEffect(() => {
    if (typeof title === 'string') document.title = `${title} · ShikkhokPlus`
  }, [title])
  return (
    <header className="top-bar">
      {back ? (
        <button
          type="button"
          className="icon-btn"
          aria-label={t('action_back')}
          onClick={() => (back === true ? navigate(-1) : navigate(back))}
        >
          <BackIcon size={24} />
        </button>
      ) : null}
      <div className="titles">
        <h1>{title}</h1>
        {subtitle ? <p className="subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </header>
  )
}

export function Section({
  title,
  aside,
  children,
}: {
  title: ReactNode
  aside?: ReactNode
  children: ReactNode
}) {
  const id = useId()
  return (
    <section className="section" aria-labelledby={id}>
      <div className="section-head">
        <h2 id={id}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

// ------------------------------------------------------------- fee chips

/**
 * The five payment states. "Colour + shape + fill style + words": each
 * state differs in all four, so they still separate in greyscale.
 */
export type FeeChipModel =
  | { kind: 'paid'; label?: string }
  | { kind: 'partial'; left: Money | null; label?: string }
  | { kind: 'due'; dueDate: string | null; amount?: Money | null }
  | { kind: 'overdue'; days: number; amount: Money | null }
  | { kind: 'verifying'; amount: Money | null }
  | { kind: 'waived' }

export function FeeChip({ chip }: { chip: FeeChipModel }) {
  const { t, lang } = useT()
  switch (chip.kind) {
    case 'paid':
      return (
        <span className="chip chip-paid">
          <CheckCircleIcon size={14} />
          {chip.label ?? t('fees_status_paid')}
        </span>
      )
    case 'partial':
      return (
        <span className="chip chip-partial">
          <HalfCircleIcon size={14} />
          {chip.label ??
            (chip.left ? t('batch_fee_left', chip.left.format()) : t('verify_partial'))}
        </span>
      )
    case 'due':
      return (
        <span className="chip chip-due">
          <CircleIcon size={14} />
          {chip.amount
            ? t('batch_fee_due_on', chip.amount.format())
            : chip.dueDate
              ? t('fees_due_on', formatShortDate(chip.dueDate, lang))
              : t('fees_status_unpaid')}
        </span>
      )
    case 'overdue':
      return (
        <span className="chip chip-overdue">
          <WarningIcon size={14} />
          {chip.amount
            ? `${chip.amount.format()} · ${t('dues_days', chip.days)}`
            : t('dues_days', chip.days)}
        </span>
      )
    case 'verifying':
      return (
        <span className="chip chip-verifying">
          <ClockIcon size={14} />
          {chip.amount
            ? t('batch_fee_verifying', chip.amount.format())
            : t('student_chip_verifying')}
        </span>
      )
    case 'waived':
      return <span className="chip chip-neutral">{t('fees_status_waived')}</span>
  }
}

// --------------------------------------------------------- states

export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div className="card" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ padding: '8px 0' }}>
          <span className="skeleton skeleton-line" style={{ width: '55%' }} />
          <span className="skeleton skeleton-line" style={{ width: '35%' }} />
        </div>
      ))}
    </div>
  )
}

/** The "Loading…" a screen announces while its static skeleton shows. */
export function Loading({ rows }: { rows?: number }) {
  const { t } = useT()
  return (
    <div role="status">
      <span className="visually-hidden">{t('batches_loading_label')}</span>
      <SkeletonList rows={rows} />
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: ReactNode
  body?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
      {action}
    </div>
  )
}

/** A failed load with nothing to show: the message the server named, and Try again. */
export function ErrorCard({
  title,
  error,
  onRetry,
}: {
  title: ReactNode
  error: ApiError
  onRetry: () => void
}) {
  const { t, message } = useT()
  return (
    <div className="card error" role="alert">
      <div className="title">{title}</div>
      <p className="meta" style={{ margin: '8px 0 16px' }}>
        {error.offline ? t('web_offline_shell') : message(error.messageKey)}
      </p>
      {error.retryable ? (
        <button type="button" className="btn btn-outline" onClick={onRetry}>
          {t('auth_retry')}
        </button>
      ) : null}
    </div>
  )
}

/** Shown above data that is still on screen but could not be refreshed. */
export function StaleBanner({ error, loadedAt }: { error: ApiError; loadedAt: Date }) {
  const { t, message, lang } = useT()
  const time = new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(loadedAt)
  return (
    <div className="banner" role="status">
      <CloudOffIcon />
      <div>
        {error.offline ? (
          <>
            <strong>{t('offline_title')}</strong> {t('offline_figures_from', time)}
          </>
        ) : (
          message(error.messageKey)
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------- snackbar & sheet

export function Snackbar({
  text,
  action,
  onAction,
  onDismiss,
}: {
  text: string
  action?: string
  onAction?: () => void
  onDismiss: () => void
}) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 6000)
    return () => window.clearTimeout(timer)
  }, [text, onDismiss])
  return (
    <div className="snackbar" role="status" aria-live="polite">
      <span className="grow">{text}</span>
      {action && onAction ? (
        <button type="button" onClick={onAction}>
          {action}
        </button>
      ) : null}
    </div>
  )
}

const FOCUSABLE =
  'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), ' +
  'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'

/**
 * Make everything outside `inside` inert: each sibling of each of its
 * ancestors up to <body>. Returns the undo, which touches only what this
 * call changed, so a sheet opened over a sheet leaves the outer one's
 * background as it found it.
 */
function inertOutside(inside: HTMLElement): () => void {
  const changed: Element[] = []
  let node: Element = inside
  while (node.parentElement && node !== document.body) {
    const parent: HTMLElement = node.parentElement
    for (const sibling of Array.from(parent.children)) {
      if (sibling === node || sibling.hasAttribute('inert')) continue
      if (sibling.tagName === 'SCRIPT' || sibling.tagName === 'STYLE') continue
      sibling.setAttribute('inert', '')
      changed.push(sibling)
    }
    node = parent
  }
  return () => {
    for (const el of changed) el.removeAttribute('inert')
  }
}

/**
 * A bottom sheet on a phone, a centred dialog on a desktop window.
 *
 * Modal in fact, not only in `aria-modal`: while it is open the rest of
 * the page is inert and Tab cycles inside the sheet. Focus moves to the
 * first field once, when it opens — never again on a parent's re-render,
 * which would pull the cursor out of the field being typed in — and goes
 * back where it was when it closes.
 */
export function Sheet({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: ReactNode
  subtitle?: ReactNode
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const backdrop = useRef<HTMLDivElement>(null)
  const titleId = useId()
  // Callers pass an inline arrow, a new function every render: read the
  // latest through a ref so the opening effect never re-runs because of it.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })
  useEffect(() => {
    const sheet = ref.current
    const outer = backdrop.current
    if (!sheet || !outer) return
    const active = document.activeElement
    const previous = active instanceof HTMLElement ? active : null
    const restore = inertOutside(outer)
    ;(sheet.querySelector<HTMLElement>(FOCUSABLE) ?? sheet).focus()
    return () => {
      restore()
      if (previous?.isConnected) previous.focus()
    }
  }, [])

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      // The innermost sheet answers: one Escape closes one sheet.
      e.stopPropagation()
      onCloseRef.current()
      return
    }
    if (e.key !== 'Tab' || !ref.current) return
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    const first = items[0]
    const last = items[items.length - 1]
    if (!first || !last) {
      e.preventDefault()
    } else if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="sheet-backdrop"
      ref={backdrop}
      onKeyDown={onKeyDown}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCloseRef.current()
      }}
    >
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
      >
        <div className="sheet-handle" />
        <h2 id={titleId}>{title}</h2>
        {subtitle ? (
          <p className="meta" style={{ marginTop: 0 }}>
            {subtitle}
          </p>
        ) : null}
        {children}
      </div>
    </div>
  )
}

export function Avatar({ letter, primary }: { letter: string; primary?: boolean }) {
  return (
    <span className={primary ? 'avatar primary' : 'avatar'} aria-hidden="true">
      {letter}
    </span>
  )
}
