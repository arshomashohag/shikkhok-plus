/**
 * Edit a student's name, phones and emails [FR6.1] [FR6.2]
 * [functional-spec W7 steps 5–6].
 *
 * The patch is `studentEdit`'s: unchanged fields omitted, a changed one
 * sent, an emptied contact sent as `null` to clear it. Saving with
 * nothing changed sends nothing and closes. The server refuses clearing
 * a contact that was accepted or erased, and that refusal is shown here.
 * The two emails are someone else's addresses: `autocomplete="off"`, so
 * the browser neither offers the teacher's own nor files these [NFR3.8].
 */
import { useId, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../../api/errors'
import { useT } from '../../../i18n/i18n'
import { Sheet } from '../../../ui/components'
import { useFailureText } from '../../auth/parts'
import { updateStudent } from './api'
import { editFields, editProblems, studentEdit, type Student, type StudentFields } from './mappers'

interface Refusal {
  text: string
  /** Under the student email, else the banner. */
  underEmail: boolean
  retry: boolean
}

export function EditStudentSheet({
  student,
  onClose,
  onSaved,
}: {
  student: Student
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useT()
  const failure = useFailureText()
  const ids = useId()
  const original = editFields(student)
  const [typed, setTyped] = useState<StudentFields>(original)
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<Refusal | null>(null)
  /** The patch last sent, for Retry after no connection. */
  const sent = useRef<ReturnType<typeof studentEdit>>(null)
  const problems = editProblems(typed)
  const dirty = (Object.keys(typed) as (keyof StudentFields)[]).some(
    (k) => typed[k] !== original[k],
  )

  async function save(patch: NonNullable<ReturnType<typeof studentEdit>>) {
    sent.current = patch
    setBusy(true)
    setRefusal(null)
    try {
      await updateStudent(student.id, patch)
      onSaved()
    } catch (e) {
      const error = e instanceof ApiError ? e : null
      setRefusal({
        text: failure(e),
        underEmail: error?.messageKey === 'student.email.taken',
        retry: error?.offline === true,
      })
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy || Object.keys(problems).length > 0 || !typed.name.trim()) return
    const patch = studentEdit(original, typed)
    if (!patch) {
      onClose()
      return
    }
    void save(patch)
  }

  const set = (key: keyof StudentFields) => (value: string) =>
    setTyped((v) => ({ ...v, [key]: value }))

  const contactField = (
    key: keyof StudentFields,
    label: string,
    kind: 'tel' | 'email',
    extraError: string | null = null,
  ) => {
    const id = `${ids}-${key}`
    const error = problems[key]
      ? t(kind === 'tel' ? 'phone_invalid' : 'web_auth_email_invalid')
      : extraError
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <input
          id={id}
          type={kind}
          inputMode={kind}
          autoComplete="off"
          value={typed[key]}
          disabled={busy}
          onChange={(e) => set(key)(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        {error ? (
          <span id={`${id}-error`} className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
    )
  }

  const ready = !busy && typed.name.trim() !== '' && Object.keys(problems).length === 0
  return (
    <Sheet title={t('web_student_edit_title')} onClose={onClose} dirty={dirty}>
      <form onSubmit={onSubmit} noValidate data-testid="edit-student-sheet">
        <div className="field" style={{ marginTop: 0 }}>
          <label htmlFor={`${ids}-name`}>{t('student_add_name')}</label>
          <input
            id={`${ids}-name`}
            value={typed.name}
            maxLength={120}
            autoComplete="off"
            disabled={busy}
            data-autofocus
            onChange={(e) => set('name')(e.target.value)}
          />
        </div>
        {contactField('studentPhone', t('student_add_student_phone'), 'tel')}
        {contactField(
          'studentEmail',
          t('student_add_student_email'),
          'email',
          refusal?.underEmail ? refusal.text : null,
        )}
        {contactField('guardianPhone', t('student_add_guardian'), 'tel')}
        {contactField('guardianEmail', t('student_add_guardian_email'), 'email')}
        {refusal && !refusal.underEmail ? (
          <div className="banner error" role="alert">
            <span>{refusal.text}</span>
            {refusal.retry && sent.current ? (
              <button
                type="button"
                className="btn btn-text btn-small"
                onClick={() => sent.current && void save(sent.current)}
              >
                {t('auth_retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="form-actions">
          <button type="button" className="btn btn-outline" disabled={busy} onClick={onClose}>
            {t('action_cancel')}
          </button>
          <button type="submit" className="btn btn-primary grow" disabled={!ready}>
            {t('web_student_edit_save')}
          </button>
        </div>
      </form>
    </Sheet>
  )
}
