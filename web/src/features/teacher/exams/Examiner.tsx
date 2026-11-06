/**
 * Who marks an exam at a centre: picked at creation, changed later. Only a
 * live member of the centre is offered; whether one may be named at all is
 * the server's rule, and a solo tutor never sees this.
 */
import { useState } from 'react'
import { listMembers } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { assignable } from '../centre/timetable'
import { readExam, setExaminer } from './api'

/** The value meaning "leave it to the server's default". */
export const DEFAULT_EXAMINER = ''

/** The picker on the create form: default, nobody, or a named member. */
export function ExaminerPicker({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string) => void
}) {
  const { t } = useT()
  const members = useResource(() => listMembers(), [])
  if (members.resource.state !== 'loaded') return null
  return (
    <div className="field">
      <label htmlFor="ex-examiner">{t('examiner_label')}</label>
      <select id="ex-examiner" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={DEFAULT_EXAMINER}>{t('examiner_default')}</option>
        {assignable(members.resource.data).map((m) => (
          <option key={m.member_id} value={m.member_id}>
            {m.display_name}
          </option>
        ))}
      </select>
      <span className="help">{t('examiner_help')}</span>
    </div>
  )
}

/** The control on an existing exam: shows the examiner and changes it. */
export function ExaminerControl({ examId }: { examId: string }) {
  const { t, message } = useT()
  const exam = useResource(() => readExam(examId), [examId])
  const members = useResource(() => listMembers(), [])
  const [note, setNote] = useState<string | null>(null)
  if (exam.resource.state !== 'loaded' || members.resource.state !== 'loaded') return null

  async function change(next: string) {
    setNote(null)
    try {
      await setExaminer(examId, next || null)
      setNote(t('examiner_changed'))
      exam.reload()
    } catch (e) {
      setNote(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))
    }
  }

  return (
    <div className="field">
      <label htmlFor="ex-examiner-now">{t('examiner_label')}</label>
      <select
        id="ex-examiner-now"
        value={exam.resource.data.examiner_member_id ?? ''}
        disabled={exam.resource.data.cancelled}
        onChange={(e) => void change(e.target.value)}
      >
        <option value="">{t('examiner_none')}</option>
        {assignable(members.resource.data).map((m) => (
          <option key={m.member_id} value={m.member_id}>
            {m.display_name}
          </option>
        ))}
      </select>
      {note ? <span className="help">{note}</span> : null}
    </div>
  )
}
