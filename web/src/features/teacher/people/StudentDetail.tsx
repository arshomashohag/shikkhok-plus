/**
 * One student: who has accepted, what is owed, their batches, and the
 * actions on them [0018]. As `StudentDetailScreen.kt`.
 *
 * Fees, attendance and marks stay per batch [D5]; a batch opens that
 * seat's fee history. Which seat may be deleted, and whether the student
 * may be removed, are the server's answers; a refusal is shown in the
 * server's own words [D4].
 */
import { useCallback, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Sheet, Snackbar, TopBar } from '../../../ui/components'
import { mapBatch } from '../mappers'
import { paths } from '../paths'
import { removeEnrollment, setInactiveFrom } from '../students/api'
import { RecordPaymentSheet } from '../money/RecordPaymentSheet'
import { bangladeshToday } from '../students/mappers'
import { enrollStudent, readStudent, removeStudent } from './api'
import { linkKey, mapStudent, otherBatches, type SeatLine } from './mappers'

type Dialog =
  { kind: 'leave'; seat: SeatLine } | { kind: 'remove' } | { kind: 'record'; seat: SeatLine } | null

export function StudentDetail() {
  const { studentId = '' } = useParams()
  const { t, message } = useT()
  const navigate = useNavigate()
  const { resource, reload } = useResource(
    () =>
      Promise.all([readStudent(studentId), listBatches()]).then(([s, b]) => ({
        student: mapStudent(s),
        batches: b.map(mapBatch),
      })),
    [studentId],
  )
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)
  const dismiss = useCallback(() => setSnack(null), [])
  const close = useCallback(() => setDialog(null), [])

  async function act(write: () => Promise<unknown>, after: () => void = reload) {
    setBusy(true)
    try {
      await write()
      setDialog(null)
      after()
    } catch (e) {
      setDialog(null)
      setSnack(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
    } finally {
      setBusy(false)
    }
  }

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('students_title')} back={paths.students()} />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('students_title')} back={paths.students()} />
        <ErrorCard
          title={t('student_detail_error_title')}
          error={resource.error}
          onRetry={reload}
        />
      </>
    )
  }

  const { student, batches } = resource.data
  const others = otherBatches(student, batches)
  const guardianLabel = student.guardianPhone
    ? `${t('student_detail_guardian_link')} · ${formatPhone(student.guardianPhone)}`
    : t('student_detail_guardian_link')

  return (
    <>
      <TopBar
        title={student.name}
        subtitle={student.studentPhone ? formatPhone(student.studentPhone) : undefined}
        back={paths.students()}
      />
      <section className="card" style={{ marginTop: 8 }}>
        <div className="kv">
          <span className="meta">{t('student_detail_student_link')}</span>
          <span className="title">{t(linkKey(student.studentState))}</span>
        </div>
        <div className="kv">
          <span className="meta">{guardianLabel}</span>
          <span className="title">{t(linkKey(student.guardianState))}</span>
        </div>
        <div className="kv">
          <span className="meta">{t('student_detail_total_due')}</span>
          <span className="title">{student.totalOutstanding.format()}</span>
        </div>
      </section>

      <h2 className="section-label">{t('student_detail_batches')}</h2>
      {student.seats.length === 0 ? (
        <p className="meta">{t('student_detail_no_batches')}</p>
      ) : (
        <ul className="list card" style={{ padding: 0 }}>
          {student.seats.map((seat) => (
            <li key={seat.enrollmentId} className="row">
              <Link
                className="grow"
                style={{ color: 'inherit', textDecoration: 'none' }}
                to={paths.seatFees(seat.enrollmentId, student.name, seat.batchName)}
              >
                <span className="title" style={{ display: 'block' }}>
                  {seat.batchName}
                </span>
                <span className="meta">
                  {[
                    seat.fee ? t('student_detail_seat_fee', seat.fee.format()) : null,
                    t('student_detail_seat_due', seat.outstanding.format()),
                    seat.active ? null : t('student_detail_left'),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </Link>
              <button
                type="button"
                className="btn btn-text"
                disabled={busy}
                onClick={() => setDialog({ kind: 'record', seat })}
              >
                {t('fees_record_payment')}
              </button>
              {seat.removable ? (
                <button
                  type="button"
                  className="btn btn-text"
                  disabled={busy}
                  onClick={() => void act(() => removeEnrollment(seat.enrollmentId))}
                >
                  {t('student_detail_remove_seat')}
                </button>
              ) : seat.active ? (
                <button
                  type="button"
                  className="btn btn-text"
                  disabled={busy}
                  onClick={() => setDialog({ kind: 'leave', seat })}
                >
                  {t('student_detail_leave')}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {others.length > 0 ? (
        <div className="field" style={{ marginTop: 12 }}>
          <label htmlFor="add-to-batch">{t('student_detail_add_batch')}</label>
          <select
            id="add-to-batch"
            value=""
            disabled={busy}
            onChange={(e) => {
              const batchId = e.target.value
              if (batchId) void act(() => enrollStudent(student.id, batchId))
            }}
          >
            <option value="">{t('student_add_batches_choose')}</option>
            {others.map((b) => (
              <option key={b.id} value={b.id}>
                {b.defaultFee ? `${b.name} · ${b.defaultFee.format()}` : b.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        {student.removable ? (
          <button
            type="button"
            className="btn btn-outline danger"
            onClick={() => setDialog({ kind: 'remove' })}
          >
            {t('student_detail_remove')}
          </button>
        ) : (
          <p className="meta">{t('student_detail_remove_blocked')}</p>
        )}
      </div>

      {dialog?.kind === 'leave' ? (
        <Sheet
          title={t('student_detail_leave_title', student.name, dialog.seat.batchName)}
          subtitle={t('student_detail_leave_body')}
          onClose={close}
        >
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={close}>
              {t('action_cancel')}
            </button>
            <button
              type="button"
              className="btn btn-primary grow"
              disabled={busy}
              onClick={() =>
                void act(() => setInactiveFrom(dialog.seat.enrollmentId, bangladeshToday()))
              }
            >
              {t('action_confirm')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {dialog?.kind === 'remove' ? (
        <Sheet
          title={t('student_detail_remove_title', student.name)}
          subtitle={t('student_detail_remove_body')}
          onClose={close}
        >
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={close}>
              {t('action_cancel')}
            </button>
            <button
              type="button"
              className="btn btn-primary grow"
              disabled={busy}
              onClick={() =>
                void act(
                  () => removeStudent(student.id),
                  () => navigate(paths.students(), { replace: true }),
                )
              }
            >
              {t('action_confirm')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {dialog?.kind === 'record' ? (
        <RecordPaymentSheet
          enrollmentId={dialog.seat.enrollmentId}
          name={`${student.name} · ${dialog.seat.batchName}`}
          owed={dialog.seat.outstanding}
          onClose={close}
          onRecorded={() => {
            setDialog(null)
            setSnack(t('fees_record_done'))
            reload()
          }}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </>
  )
}
