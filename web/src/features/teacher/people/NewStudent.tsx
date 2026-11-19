/**
 * Add a student to the teacher's list, and suggest batches [D3]. As
 * `AddStudentForm.kt`.
 *
 * - Batches are a multi-select and may be left empty: the student is
 *   saved with no batch.
 * - Each chosen batch charges its own fee unless a different one is typed
 *   beside it; blank means INHERIT, never zero, because zero is a waiver.
 * - A name already on the list gets a hint, not a block; a number already
 *   on the list is refused by the server and shown in its own words [D2].
 * - A student email and a guardian email may be recorded too [FR6.1],
 *   checked with the shared email check, omitted when blank, and never
 *   autofilled: they are someone else's addresses [NFR3.8]. An email
 *   already on the list (`student.email.taken`) is shown under it.
 *
 * Opened from a roster's "New student" with that batch already chosen.
 *
 * **From a join request** (`?enquiry=<id>`, the owner's "Add as student"
 * [H5]) the form reads that request from the server and fills the name,
 * the guardian's phone or email when the guardian shared one, and the
 * batch asked about; the teacher checks and saves as usual, and the seat
 * starts pending like any other. Once the student is saved, the request is
 * answered `added` when the server still offers that answer. If only the
 * answer fails, the student stays saved and is never saved twice: the form
 * offers Retry for the answer alone.
 */
import { useId, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { listBatches } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone, normalisePhone } from '../../../core/format'
import { Money } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { mapBatch, type BatchSummary } from '../mappers'
import { sameNameMatch } from '../students/mappers'
import { mutationId } from '../classes/api'
import { closeEnquiry, readOwnerEnquiry, type OwnerEnquiry } from '../hub/enquiries.api'
import { failureText } from '../hub/hubUi'
import { createStudent, listStudents } from './api'
import { typedEmail } from './mappers'

interface Context {
  batches: BatchSummary[]
  names: string[]
  /** The join request the form was opened from, as the server holds it. */
  enquiry: OwnerEnquiry | null
}

async function loadContext(enquiryId: string | null, signal?: AbortSignal): Promise<Context> {
  const [batches, students, enquiry] = await Promise.all([
    listBatches(signal),
    listStudents({ kind: 'all' }, '', signal),
    enquiryId ? readOwnerEnquiry(enquiryId, signal) : null,
  ])
  return { batches: batches.map(mapBatch), names: students.map((s) => s.display_name), enquiry }
}

export function NewStudent() {
  const { t } = useT()
  const [params] = useSearchParams()
  const enquiryId = params.get('enquiry')
  const { resource, reload } = useResource((signal) => loadContext(enquiryId, signal), [enquiryId])
  const preselected =
    params.get('batch') ??
    (resource.state === 'loaded' ? (resource.data.enquiry?.batch_id ?? null) : null)

  return (
    <>
      <TopBar title={t('screen_title_add_student')} back={true} />
      {resource.state === 'loading' ? <Loading rows={4} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('students_error_title')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        <StudentForm
          batches={resource.data.batches}
          names={resource.data.names}
          preselected={preselected}
          enquiry={resource.data.enquiry}
        />
      ) : null}
    </>
  )
}

function StudentForm({
  batches,
  names,
  preselected,
  enquiry,
}: {
  batches: BatchSummary[]
  names: string[]
  preselected: string | null
  enquiry: OwnerEnquiry | null
}) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const ids = useId()
  // From a join request: what the guardian sent, and their contact only if shared.
  const [name, setName] = useState(enquiry?.student_name ?? '')
  const [phone, setPhone] = useState('')
  const [guardian, setGuardian] = useState(
    enquiry?.guardian_phone ? formatPhone(enquiry.guardian_phone) : '',
  )
  const [studentEmailTyped, setStudentEmail] = useState('')
  const [guardianEmailTyped, setGuardianEmail] = useState(enquiry?.guardian_email ?? '')
  /** `student.email.taken`, shown under the student email until it is edited. */
  const [emailTaken, setEmailTaken] = useState<string | null>(null)
  // Batch id → the fee typed for it; blank inherits the batch's fee.
  const [chosen, setChosen] = useState<Record<string, string>>(() =>
    preselected && batches.some((b) => b.id === preselected) ? { [preselected]: '' } : {},
  )
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The student is saved; only the join request's answer is outstanding.
  const [saved, setSaved] = useState(false)
  const [closeFailure, setCloseFailure] = useState<{ text: string; retryable: boolean } | null>(
    null,
  )

  const studentPhone = normalisePhone(phone)
  const guardianPhone = normalisePhone(guardian)
  // The shared email check; blank means absent [W7 steps 2–3].
  const studentEmail = typedEmail(studentEmailTyped)
  const guardianEmail = typedEmail(guardianEmailTyped)
  const picked = batches.filter((b) => b.id in chosen)
  const fees = picked.map((b) => {
    const typed = chosen[b.id] ?? ''
    return { batch: b, typed, money: typed.trim() ? Money.fromTyped(typed) : null }
  })
  const feesOk = fees.every((f) => f.typed.trim() === '' || f.money !== null)
  const ready =
    !busy &&
    !saved &&
    name.trim() !== '' &&
    (phone.trim() === '' || studentPhone !== null) &&
    (guardian.trim() === '' || guardianPhone !== null) &&
    studentEmail !== null &&
    guardianEmail !== null &&
    feesOk
  const sameName = sameNameMatch(name, names)

  function toggle(batchId: string) {
    setChosen((c) =>
      batchId in c
        ? Object.fromEntries(Object.entries(c).filter(([id]) => id !== batchId))
        : { ...c, [batchId]: '' },
    )
  }

  // One key per form, kept across retries: a resend after a lost
  // response returns the student the first one made [audit C-25].
  const [retryKey] = useState(mutationId)

  /** Answer the join request `added`, once the student is saved; then leave. */
  async function answerEnquiry(id: string) {
    setBusy(true)
    setCloseFailure(null)
    try {
      await closeEnquiry(id, 'added')
      navigate(-1)
    } catch (err) {
      setCloseFailure({
        text: `${t('hub_enquiry_saved_not_closed')} ${failureText(err, t, message)}`,
        retryable: !(err instanceof ApiError) || err.offline || err.retryable,
      })
      setBusy(false)
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await createStudent({
        client_mutation_id: retryKey,
        display_name: name.trim(),
        student_phone: studentPhone,
        guardian_phone: guardianPhone,
        // Omitted when blank, trimmed when sent.
        ...(studentEmail ? { student_email: studentEmail } : {}),
        ...(guardianEmail ? { guardian_email: guardianEmail } : {}),
        enrollments: fees.map((f) => ({ batch_id: f.batch.id, fee_amount: f.money?.wire ?? null })),
      })
    } catch (err) {
      const key = err instanceof ApiError ? err.messageKey : 'error.unexpected'
      if (key === 'student.email.taken') setEmailTaken(message(key))
      else setError(message(key))
      setBusy(false)
      return
    }
    // Answer only what the server still offers; a request already answered is left as it is.
    if (enquiry && enquiry.outcomes_allowed.includes('added')) {
      setSaved(true)
      await answerEnquiry(enquiry.id)
    } else navigate(-1)
  }

  const emailField = (
    which: 'student' | 'guardian',
    value: string,
    onChange: (v: string) => void,
    malformed: boolean,
    refused: string | null,
  ) => {
    const id = `${ids}-${which}-email`
    const problem = malformed ? t('web_auth_email_invalid') : refused
    return (
      <div className="field">
        <label htmlFor={id}>
          {t(which === 'student' ? 'student_add_student_email' : 'student_add_guardian_email')}
        </label>
        <input
          id={id}
          type="email"
          inputMode="email"
          // Someone else's address: never offer the teacher's own [NFR3.8].
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={problem ? true : undefined}
          aria-describedby={problem ? `${id}-error` : undefined}
        />
        {problem ? (
          <span id={`${id}-error`} className="field-error" role="alert">
            {problem}
          </span>
        ) : null}
      </div>
    )
  }

  return (
    <form className="card" onSubmit={onSubmit} noValidate>
      {enquiry ? (
        <div className="banner info" role="status" style={{ marginBottom: 16 }}>
          {t('hub_enquiry_prefilled')}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor={`${ids}-name`}>{t('student_add_name')}</label>
        <input
          id={`${ids}-name`}
          value={name}
          maxLength={120}
          autoComplete="off"
          onChange={(e) => setName(e.target.value)}
        />
        {sameName ? <span className="help">{t('student_add_same_name_any', sameName)}</span> : null}
      </div>
      <div className="field">
        <label htmlFor={`${ids}-phone`}>{t('student_add_student_phone')}</label>
        <input
          id={`${ids}-phone`}
          type="tel"
          inputMode="tel"
          autoComplete="off"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          aria-invalid={phone.trim() !== '' && studentPhone === null ? true : undefined}
        />
        {phone.trim() !== '' && studentPhone === null ? (
          <span className="field-error">{t('phone_invalid')}</span>
        ) : (
          <span className="help">{t('student_add_student_phone_help')}</span>
        )}
      </div>
      {emailField(
        'student',
        studentEmailTyped,
        (v) => {
          setStudentEmail(v)
          setEmailTaken(null)
        },
        studentEmail === null,
        emailTaken,
      )}
      <div className="field">
        <label htmlFor={`${ids}-guardian`}>{t('student_add_guardian')}</label>
        <input
          id={`${ids}-guardian`}
          type="tel"
          inputMode="tel"
          autoComplete="off"
          value={guardian}
          onChange={(e) => setGuardian(e.target.value)}
          aria-invalid={guardian.trim() !== '' && guardianPhone === null ? true : undefined}
        />
        {guardian.trim() !== '' && guardianPhone === null ? (
          <span className="field-error">{t('phone_invalid')}</span>
        ) : null}
      </div>
      {emailField('guardian', guardianEmailTyped, setGuardianEmail, guardianEmail === null, null)}

      <div className="field">
        <span id={`${ids}-batches`} className="label">
          {t('student_add_batches')}
        </span>
        {batches.length === 0 ? (
          <span className="help">{t('student_add_batches_none')}</span>
        ) : (
          <div className="multi-select">
            <button
              type="button"
              className="multi-select-trigger"
              aria-haspopup="listbox"
              aria-expanded={open}
              aria-labelledby={`${ids}-batches`}
              onClick={() => setOpen((o) => !o)}
            >
              {picked.length === 0
                ? t('student_add_batches_choose')
                : picked.map((b) => b.name).join(', ')}
            </button>
            {open ? (
              <ul className="multi-select-list" role="listbox" aria-multiselectable="true">
                {batches.map((b) => (
                  <li
                    key={b.id}
                    role="option"
                    aria-selected={b.id in chosen}
                    tabIndex={0}
                    onClick={() => toggle(b.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        toggle(b.id)
                      }
                    }}
                  >
                    <input type="checkbox" readOnly tabIndex={-1} checked={b.id in chosen} />
                    <span className="grow">{b.name}</span>
                    {b.defaultFee ? <span className="meta">{b.defaultFee.format()}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            <span className="help">{t('student_add_batches_help')}</span>
          </div>
        )}
      </div>

      {fees.map((f) => (
        <div className="field" key={f.batch.id}>
          <label htmlFor={`${ids}-fee-${f.batch.id}`}>
            {t('student_add_seat_fee', f.batch.name)}
          </label>
          <input
            id={`${ids}-fee-${f.batch.id}`}
            inputMode="decimal"
            placeholder={
              f.batch.defaultFee ? t('student_add_batch_fee', f.batch.defaultFee.format()) : ''
            }
            value={f.typed}
            onChange={(e) => setChosen((c) => ({ ...c, [f.batch.id]: e.target.value }))}
            aria-invalid={f.typed.trim() !== '' && f.money === null ? true : undefined}
          />
          <span className={f.typed.trim() !== '' && f.money === null ? 'field-error' : 'help'}>
            {f.typed.trim() !== '' && f.money === null ? t('fee_invalid') : t('fee_inherits')}
          </span>
        </div>
      ))}
      {picked.length === 0 ? <p className="meta">{t('student_add_no_batch')}</p> : null}

      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}
      {closeFailure && enquiry ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          <span className="grow">{closeFailure.text}</span>
          {closeFailure.retryable ? (
            <button
              type="button"
              className="btn btn-text btn-small"
              disabled={busy}
              onClick={() => void answerEnquiry(enquiry.id)}
            >
              {t('auth_retry')}
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="form-actions">
        <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>
          {t('action_cancel')}
        </button>
        <button type="submit" className="btn btn-primary grow" disabled={!ready}>
          {busy ? t('student_add_submitting') : t('student_add_submit')}
        </button>
      </div>
    </form>
  )
}
