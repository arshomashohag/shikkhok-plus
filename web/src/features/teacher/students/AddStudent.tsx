/**
 * T8 · Add student. As `AddStudentRoute.kt` and `StudentAddForm`:
 *
 * - the student's phone is required (they sign in with it), the guardian's
 *   is optional;
 * - when the batch has a fee, a toggle keeps it, and a fee field appears
 *   only when it is turned off; with no batch fee, the field is optional;
 * - a name already on the roster gets a hint, not a block — two students
 *   can share a name;
 * - "Save & add next" keeps the screen open with "N added so far".
 *
 * Validation is format only. Whether the number may be added (already in
 * this batch, say) is the server's answer, shown in its own words.
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useNavigate, useParams } from 'react-router'
import { listBatches, readRoster } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { normalisePhone } from '../../../core/format'
import { Money } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, Snackbar, TopBar } from '../../../ui/components'
import { mapBatch } from '../mappers'
import { paths } from '../paths'
import { addEnrollment } from './api'
import { phoneProblem, sameNameMatch, type Phrase } from './mappers'

interface Context {
  batchName: string | null
  batchFee: Money | null
  existingNames: string[]
}

async function loadContext(batchId: string, signal?: AbortSignal): Promise<Context> {
  const [batches, roster] = await Promise.all([listBatches(signal), readRoster(batchId, signal)])
  const batch = batches.map(mapBatch).find((b) => b.id === batchId) ?? null
  return {
    batchName: batch?.name ?? null,
    batchFee: batch?.defaultFee ?? null,
    existingNames: roster.map((r) => r.display_name),
  }
}

export function AddStudent() {
  const { batchId = '' } = useParams()
  const { t, plural } = useT()
  const { resource, reload } = useResource((signal) => loadContext(batchId, signal), [batchId])
  const [added, setAdded] = useState(0)
  const [names, setNames] = useState<string[]>([])
  const back = paths.batch(batchId)

  const subtitle =
    resource.state === 'loaded'
      ? [resource.data.batchName, added > 0 ? plural('student_add_added_so_far', added) : null]
          .filter(Boolean)
          .join(' · ')
      : undefined

  return (
    <>
      <TopBar title={t('student_add_title')} subtitle={subtitle} back={back} />
      {resource.state === 'loading' ? <Loading rows={4} /> : null}
      {resource.state === 'failed' ? (
        <ErrorCard title={t('batch_students_failed')} error={resource.error} onRetry={reload} />
      ) : null}
      {resource.state === 'loaded' ? (
        // A fresh form after each "Save & add next", as Android's key(added).
        <StudentForm
          key={added}
          batchId={batchId}
          batchFee={resource.data.batchFee}
          existingNames={[...resource.data.existingNames, ...names]}
          justAdded={added > 0 ? (names[names.length - 1] ?? null) : null}
          onSaved={(name, next) => {
            setNames((n) => [...n, name])
            if (next) setAdded((n) => n + 1)
          }}
          back={back}
        />
      ) : null}
    </>
  )
}

function Field({
  label,
  help,
  error,
  children,
}: {
  label: ReactNode
  help?: ReactNode
  error?: string | null
  children: (ids: { id: string; describedBy: string | undefined }) => ReactNode
}) {
  const id = useId()
  const describedBy = [error ? `${id}-error` : null, help ? `${id}-help` : null].filter(Boolean)
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children({ id, describedBy: describedBy.join(' ') || undefined })}
      {error ? (
        <span id={`${id}-error`} className="field-error">
          {error}
        </span>
      ) : null}
      {help ? (
        <span id={`${id}-help`} className="help">
          {help}
        </span>
      ) : null}
    </div>
  )
}

function StudentForm({
  batchId,
  batchFee,
  existingNames,
  justAdded,
  onSaved,
  back,
}: {
  batchId: string
  batchFee: Money | null
  existingNames: string[]
  justAdded: string | null
  onSaved: (name: string, next: boolean) => void
  back: string
}) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [guardian, setGuardian] = useState('')
  const [useBatchFee, setUseBatchFee] = useState(true)
  const [fee, setFee] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [snack, setSnack] = useState<string | null>(justAdded ? t('student_add_added') : null)
  const dismiss = useCallback(() => setSnack(null), [])
  const phoneRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    phoneRef.current?.focus()
  }, [])

  const phrase = (p: Phrase | null) => (p ? t(...p) : null)
  const studentPhone = normalisePhone(phone)
  const guardianPhone = normalisePhone(guardian)
  const feeShown = batchFee === null || !useBatchFee
  const typedFee = feeShown && fee.trim() ? Money.fromTyped(fee) : null
  const feeOk = !feeShown || fee.trim() === '' || typedFee !== null
  const ready =
    !busy &&
    name.trim() !== '' &&
    studentPhone !== null &&
    (guardian.trim() === '' || guardianPhone !== null) &&
    feeOk
  const sameName = sameNameMatch(name, existingNames)

  async function save(next: boolean) {
    if (!ready || !studentPhone) return
    setBusy(true)
    setError(null)
    try {
      await addEnrollment(batchId, {
        display_name: name.trim(),
        student_phone: studentPhone,
        guardian_phone: guardianPhone,
        fee_amount: typedFee?.wire ?? null,
      })
      onSaved(name.trim(), next)
      if (!next) navigate(back, { replace: true })
    } catch (e) {
      setError(message(e instanceof ApiError ? e.messageKey : 'error.unexpected'))
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void save(false)
  }

  return (
    <form className="card" onSubmit={onSubmit} noValidate>
      <Field
        label={t('student_add_student_phone')}
        help={t('student_add_student_phone_help')}
        error={phrase(phoneProblem(phone, studentPhone !== null))}
      >
        {({ id, describedBy }) => (
          <div className="phone-field">
            <span className="prefix" aria-hidden="true">
              {t('web_students_phone_prefix')}
            </span>
            <input
              ref={phoneRef}
              id={id}
              type="tel"
              inputMode="tel"
              autoComplete="off"
              placeholder={t('auth_phone_hint')}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              aria-invalid={phoneProblem(phone, studentPhone !== null) ? true : undefined}
              aria-describedby={describedBy}
            />
          </div>
        )}
      </Field>

      <Field
        label={t('student_add_name')}
        help={sameName ? t('student_add_same_name', sameName) : null}
      >
        {({ id, describedBy }) => (
          <input
            id={id}
            value={name}
            maxLength={120}
            autoComplete="off"
            onChange={(e) => setName(e.target.value)}
            aria-describedby={describedBy}
          />
        )}
      </Field>

      <Field
        label={t('student_add_guardian')}
        help={t('student_add_guardian_hint')}
        error={phrase(phoneProblem(guardian, guardianPhone !== null))}
      >
        {({ id, describedBy }) => (
          <div className="phone-field">
            <span className="prefix" aria-hidden="true">
              {t('web_students_phone_prefix')}
            </span>
            <input
              id={id}
              type="tel"
              inputMode="tel"
              autoComplete="off"
              value={guardian}
              onChange={(e) => setGuardian(e.target.value)}
              aria-invalid={phoneProblem(guardian, guardianPhone !== null) ? true : undefined}
              aria-describedby={describedBy}
            />
          </div>
        )}
      </Field>

      <fieldset className="field">
        <legend>{t('web_students_monthly_fee')}</legend>
        {batchFee ? (
          <label className="toggle-row">
            <span className="grow">
              <span className="title" style={{ display: 'block' }}>
                {t('student_add_batch_fee', batchFee.format())}
              </span>
              <span className="meta">{t('student_add_batch_fee_help')}</span>
            </span>
            <input
              type="checkbox"
              role="switch"
              className="switch"
              checked={useBatchFee}
              onChange={(e) => setUseBatchFee(e.target.checked)}
            />
          </label>
        ) : null}
      </fieldset>
      {feeShown ? (
        <Field label={t('student_add_fee')} error={feeOk ? null : t('fee_invalid')}>
          {({ id, describedBy }) => (
            <input
              id={id}
              inputMode="decimal"
              value={fee}
              onChange={(e) => setFee(e.target.value)}
              aria-invalid={feeOk ? undefined : true}
              aria-describedby={describedBy}
            />
          )}
        </Field>
      ) : null}

      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}

      <div className="form-actions">
        <button type="submit" className="btn btn-outline" disabled={!ready}>
          {busy ? t('student_add_submitting') : t('student_add_submit')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!ready}
          onClick={() => void save(true)}
        >
          {t('student_add_submit_next')}
        </button>
      </div>
      {snack ? <Snackbar text={snack} onDismiss={dismiss} /> : null}
    </form>
  )
}
