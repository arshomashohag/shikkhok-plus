/**
 * T7 · Students tab: who is in the batch, where each stands on fees, and
 * what the teacher can do about a seat.
 *
 * Fee chips load separately from names, as the design's Loading/Error
 * board draws: names still show when fee status could not load, and fee
 * status is hidden rather than shown out of date.
 *
 * Seat actions follow `StudentsTab.kt`: tap a student to open Fee history,
 * Mark inactive and — only where the server says `is_removable` — Remove.
 * A declined seat (usually a mistyped number) shows its actions at once.
 * A removal the server refuses comes back with a code naming the remedy,
 * and the refusal offers exactly that remedy.
 */
import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { readBatchFees, readRoster } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone } from '../../../core/format'
import { useOnline, useResource } from '../../../core/useResource'
import { useWide } from '../../../core/useWide'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, FeeChip, Loading, Sheet, Snackbar } from '../../../ui/components'
import { PlusIcon } from '../../../ui/icons'
import type { BatchTabProps } from '../area'
import { paths, seatState } from '../paths'
import { removeEnrollment, setInactiveFrom } from './api'
import {
  bangladeshToday,
  mapSeats,
  removalRemedy,
  seatLine,
  type RemovalRemedy,
  type Seat,
} from './mappers'

interface Loaded {
  seats: Seat[]
  feesError: ApiError | null
}

async function load(batchId: string, signal?: AbortSignal): Promise<Loaded> {
  const [roster, fees] = await Promise.all([
    readRoster(batchId, signal),
    readBatchFees(batchId, signal).then(
      (f) => ({ ok: true as const, f }),
      (e: unknown) => ({ ok: false as const, e }),
    ),
  ])
  if (!fees.ok && !(fees.e instanceof ApiError)) throw fees.e
  return {
    seats: mapSeats(roster, fees.ok ? fees.f : null),
    feesError: fees.ok ? null : (fees.e as ApiError),
  }
}

type Dialog =
  | { kind: 'remove'; seat: Seat }
  | { kind: 'refused'; seat: Seat; messageKey: string; remedy: RemovalRemedy }
  | { kind: 'inactive'; seat: Seat }
  | null

export function StudentsTab({ batchId, batch }: BatchTabProps) {
  const { t, message } = useT()
  const online = useOnline()
  const { resource, reload } = useResource((signal) => load(batchId, signal), [batchId])
  const wide = useWide()
  const [open, setOpen] = useState<string | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const dismiss = useCallback(() => setSnack(null), [])

  const label = (seat: Seat) =>
    seat.declined
      ? seat.guardianPhone
        ? formatPhone(seat.guardianPhone)
        : t('roster_declined_no_number')
      : seat.displayName

  async function remove(seat: Seat) {
    setBusy(true)
    try {
      await removeEnrollment(seat.enrollmentId)
      setDialog(null)
      setSnack(t('web_students_removed', label(seat)))
      reload()
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      const remedy = error ? removalRemedy(error.code) : null
      if (error && remedy) {
        setDialog({ kind: 'refused', seat, messageKey: error.messageKey, remedy })
      } else {
        setDialog(null)
        setSnack(message(error?.messageKey ?? 'error.unexpected'))
      }
    } finally {
      setBusy(false)
    }
  }

  async function markInactive(seat: Seat) {
    setBusy(true)
    try {
      await setInactiveFrom(seat.enrollmentId, bangladeshToday())
      setDialog(null)
      setSnack(t('web_students_marked_inactive', label(seat)))
      reload()
    } catch (e) {
      setDialog(null)
      setSnack(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
    } finally {
      setBusy(false)
    }
  }

  // Existing students first, with "New student" for anyone not on the
  // teacher's list yet [0018].
  const addLink = paths.pickStudents(batchId)
  let body: React.ReactNode
  if (resource.state === 'loading') {
    body = <Loading rows={5} />
  } else if (resource.state === 'failed') {
    body = <ErrorCard title={t('batch_students_failed')} error={resource.error} onRetry={reload} />
  } else if (resource.data.seats.length === 0) {
    body = (
      <EmptyState
        title={t('batch_students_empty')}
        body={t('batch_students_empty_body')}
        action={
          <Link to={addLink} className="btn btn-primary btn-money">
            {t('batch_add_first_student')}
          </Link>
        }
      />
    )
  } else {
    const { seats, feesError } = resource.data
    // Acting on a seat needs a fresh read: no actions on a stale roster.
    const actionable = resource.error === null && !resource.refreshing && online
    body = (
      <>
        {batch && batch.acceptedCount < batch.enrollmentCount ? (
          <div className="banner" role="status" style={{ marginBottom: 12 }}>
            <span>
              <strong>
                {t('batch_accepted_count', batch.acceptedCount, batch.enrollmentCount)}
              </strong>{' '}
              {t('batch_accepted_body')}
            </span>
          </div>
        ) : null}
        {feesError ? (
          <div className="card error" role="status" style={{ marginBottom: 12 }}>
            <div className="title">{t('batch_fees_failed')}</div>
            <p className="meta">{t('batch_fees_failed_body')}</p>
            <button type="button" className="btn btn-outline" onClick={reload}>
              {t('roster_retry')}
            </button>
          </div>
        ) : null}
        {wide ? (
          <section className="card flush">
            <div className="panel-head">
              <h2>{batch?.name ?? ''}</h2>
              <Link to={addLink} className="btn btn-primary btn-small">
                <PlusIcon />
                {t('batch_add_student')}
              </Link>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">{t('web_roster_col_student')}</th>
                    <th scope="col">{t('web_roster_col_contact')}</th>
                    <th scope="col">{t('web_roster_col_fee')}</th>
                    <th scope="col">
                      <span className="visually-hidden">{t('web_roster_col_actions')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {seats.map((seat) => (
                    <tr key={seat.enrollmentId}>
                      <td className="title">{label(seat)}</td>
                      <td>
                        <span className={seat.declined ? 'meta danger' : 'meta'}>
                          {seatLine(seat, formatPhone)
                            .map(([key, ...args]) => t(key, ...args))
                            .join(' · ')}
                        </span>
                        {seat.declined ? (
                          <div className="meta">{t('batch_declined_help')}</div>
                        ) : null}
                      </td>
                      <td>
                        {seat.declined ? (
                          <span className="chip chip-due">{t('batch_declined')}</span>
                        ) : seat.chip && !feesError ? (
                          <FeeChip chip={seat.chip} />
                        ) : null}
                      </td>
                      <td className="num">
                        {actionable ? (
                          <span className="row-actions">
                            {!seat.declined ? (
                              <Link
                                className="btn btn-text btn-small"
                                to={paths.seatFees(seat.enrollmentId)}
                                state={seatState(seat.displayName, batch?.name)}
                              >
                                {t('batch_fee_history')}
                              </Link>
                            ) : null}
                            {!seat.declined && seat.inactiveFrom === null ? (
                              <button
                                type="button"
                                className="btn btn-text btn-small"
                                onClick={() => setDialog({ kind: 'inactive', seat })}
                              >
                                {t('batch_mark_inactive')}
                              </button>
                            ) : null}
                            {seat.isRemovable ? (
                              <button
                                type="button"
                                className="btn btn-text btn-small danger"
                                onClick={() => setDialog({ kind: 'remove', seat })}
                              >
                                {t('batch_remove')}
                              </button>
                            ) : null}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <ul className="card flush list">
            {seats.map((seat) => {
              const expanded = seat.declined || open === seat.enrollmentId
              const line = seatLine(seat, formatPhone)
                .map(([key, ...args]) => t(key, ...args))
                .join(' · ')
              return (
                <li key={seat.enrollmentId} className="seat">
                  <button
                    type="button"
                    className="row"
                    aria-expanded={expanded}
                    aria-label={t('web_students_actions_for', label(seat))}
                    onClick={() =>
                      seat.declined ||
                      setOpen((cur) => (cur === seat.enrollmentId ? null : seat.enrollmentId))
                    }
                  >
                    <span className="grow">
                      <span className="title" style={{ display: 'block' }}>
                        {label(seat)}
                      </span>
                      <span className={seat.declined ? 'meta danger' : 'meta'}>{line}</span>
                    </span>
                    {seat.declined ? (
                      <span className="chip chip-due">{t('batch_declined')}</span>
                    ) : seat.chip && !feesError ? (
                      <FeeChip chip={seat.chip} />
                    ) : null}
                  </button>
                  {seat.declined ? (
                    <p className="meta seat-help">{t('batch_declined_help')}</p>
                  ) : null}
                  {expanded && actionable ? (
                    <div className="seat-actions">
                      {!seat.declined ? (
                        <Link
                          className="btn btn-text btn-small"
                          to={paths.seatFees(seat.enrollmentId)}
                          state={seatState(seat.displayName, batch?.name)}
                        >
                          {t('batch_fee_history')}
                        </Link>
                      ) : null}
                      {!seat.declined && seat.inactiveFrom === null ? (
                        <button
                          type="button"
                          className="btn btn-text btn-small"
                          onClick={() => setDialog({ kind: 'inactive', seat })}
                        >
                          {t('batch_mark_inactive')}
                        </button>
                      ) : null}
                      {seat.isRemovable ? (
                        <button
                          type="button"
                          className="btn btn-text btn-small danger"
                          onClick={() => setDialog({ kind: 'remove', seat })}
                        >
                          {t('batch_remove')}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
        {wide ? null : (
          <Link to={addLink} className="btn btn-primary fab">
            <PlusIcon />
            {t('batch_add_student')}
          </Link>
        )}
      </>
    )
  }

  return (
    <>
      {body}
      {dialog?.kind === 'remove' ? (
        <Sheet title={t('roster_remove_confirm_title')} onClose={() => setDialog(null)}>
          <p className="meta">{t('roster_remove_confirm_body', label(dialog.seat))}</p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-danger btn-money"
              disabled={busy}
              onClick={() => void remove(dialog.seat)}
            >
              {t('roster_remove_confirm')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setDialog(null)}
            >
              {t('action_cancel')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {dialog?.kind === 'refused' ? (
        <Sheet title={t('roster_remove_refused_title')} onClose={() => setDialog(null)}>
          <p className="meta">
            {dialog.remedy === 'mark-inactive'
              ? t('roster_remove_claimed_remedy')
              : t('roster_remove_erased_remedy')}
          </p>
          <div className="button-row">
            {dialog.remedy === 'mark-inactive' ? (
              <button
                type="button"
                className="btn btn-primary btn-money"
                disabled={busy}
                onClick={() => void markInactive(dialog.seat)}
              >
                {t('roster_mark_inactive')}
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setDialog(null)}
            >
              {t('action_close')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {dialog?.kind === 'inactive' ? (
        <Sheet
          title={t('web_students_inactive_title', label(dialog.seat))}
          onClose={() => setDialog(null)}
        >
          <p className="meta">{t('web_students_inactive_body')}</p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-primary btn-money"
              disabled={busy}
              onClick={() => void markInactive(dialog.seat)}
            >
              {t('roster_mark_inactive')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setDialog(null)}
            >
              {t('action_cancel')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}
