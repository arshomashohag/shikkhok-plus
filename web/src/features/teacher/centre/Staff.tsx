/**
 * Teachers & staff: a centre's records of the people it employs.
 *
 * A record grants nothing. Inviting a teacher also offers app access,
 * which they hold only once they accept; other staff never get it. Marking
 * someone as left ends any access in the same step. The server decides all
 * of it; this screen shows its answers.
 */
import { useState } from 'react'
import {
  addOtherStaff,
  inviteStaffTeacher,
  listStaff,
  markStaffLeft,
  updateStaff,
  type Schemas,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone, formatShortDate } from '../../../core/format'
import { Money } from '../../../core/money'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  Loading,
  Sheet,
  Snackbar,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { PlusIcon, WarningIcon } from '../../../ui/icons'
import {
  accessKey,
  otherBody,
  staffInput,
  teacherBody,
  updateBody,
  type PayBasis,
  type StaffInput,
  type StaffKind,
} from './staffForm'

type Row = Schemas['StaffResponse']
const BASES: readonly PayBasis[] = ['monthly', 'per_class', 'none']

function failureText(e: unknown, t: (k: string) => string, message: (k: string) => string) {
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

/** One line of pay terms, from the server's basis and rate. */
function payLine(row: Row, t: (k: string, ...a: (string | number)[]) => string): string {
  if (row.pay_basis === 'none' || !row.pay_rate) return t('staff_pay_none')
  return t(`staff_pay_${row.pay_basis}`, Money.fromWire(row.pay_rate).format())
}

function StaffSheet({
  kind,
  row,
  onClose,
  onSaved,
}: {
  kind: StaffKind
  row?: Row
  onClose: () => void
  onSaved: () => void
}) {
  const { t, message } = useT()
  const [input, setInput] = useState<StaffInput>(() => staffInput(kind, row))
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const set = (patch: Partial<StaffInput>) => setInput((i) => ({ ...i, ...patch }))
  const editing = row !== undefined
  const teacherInvite = !editing && kind === 'teacher' ? teacherBody(input) : null
  const otherCreate = !editing && kind === 'other' ? otherBody(input) : null
  const correction = editing ? updateBody(input) : null
  const ready = teacherInvite ?? otherCreate ?? correction

  async function save() {
    setBusy(true)
    setFailure(null)
    try {
      if (row && correction) await updateStaff(row.staff_id, correction)
      else if (teacherInvite) await inviteStaffTeacher(teacherInvite)
      else if (otherCreate) await addOtherStaff(otherCreate)
      onSaved()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  const text = (id: keyof StaffInput, label: string, props: Record<string, string> = {}) => (
    <div className="field">
      <label htmlFor={`st-${id}`}>{label}</label>
      <input
        id={`st-${id}`}
        value={input[id] as string}
        onChange={(e) => set({ [id]: e.target.value } as Partial<StaffInput>)}
        {...props}
      />
    </div>
  )

  const title = editing
    ? t('staff_edit')
    : kind === 'teacher'
      ? t('staff_invite_teacher')
      : t('staff_add_other')

  return (
    <Sheet title={title} onClose={onClose}>
      {text('name', t('staff_name_label'), { maxLength: '120' })}
      {editing && kind === 'teacher'
        ? null
        : text('phone', t('staff_phone_label'), {
            type: 'tel',
            inputMode: 'tel',
            placeholder: t('auth_phone_hint'),
          })}
      {kind === 'other' ? text('roleLabel', t('staff_role_label'), { maxLength: '60' }) : null}
      {text('email', t('staff_email_label'), { type: 'email', inputMode: 'email' })}
      <fieldset className="field">
        <legend>{t('staff_address_heading')}</legend>
        {text('house', t('address_house_label'))}
        {text('road', t('address_road_label'))}
        {text('city', t('address_city_label'))}
        {text('postcode', t('address_postcode_label'), { inputMode: 'numeric', maxLength: '4' })}
      </fieldset>
      <div className="field">
        <label htmlFor="st-basis">{t('staff_pay_basis_label')}</label>
        <select
          id="st-basis"
          value={input.basis}
          onChange={(e) => set({ basis: e.target.value as PayBasis })}
        >
          {BASES.map((b) => (
            <option key={b} value={b}>
              {t(`staff_pay_basis_${b}`)}
            </option>
          ))}
        </select>
      </div>
      {input.basis === 'none'
        ? null
        : text('rate', t('staff_pay_rate_label'), { inputMode: 'decimal' })}
      {text('joinedOn', t('staff_joined_label'), { type: 'date' })}
      {!editing && kind === 'teacher' ? <p className="help">{t('staff_invite_help')}</p> : null}
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!ready || busy}
          onClick={() => void save()}
        >
          {kind === 'teacher' && !editing ? t('centre_invite_submit') : t('staff_save')}
        </button>
      </div>
    </Sheet>
  )
}

function LeaveSheet({
  row,
  onClose,
  onLeft,
}: {
  row: Row
  onClose: () => void
  onLeft: () => void
}) {
  const { t, message } = useT()
  const [day, setDay] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function confirm() {
    setBusy(true)
    setFailure(null)
    try {
      await markStaffLeft(row.staff_id, day || null)
      onLeft()
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('staff_leave')} onClose={onClose}>
      <p style={{ marginTop: 0 }}>{t('staff_leave_confirm', row.display_name)}</p>
      <div className="field">
        <label htmlFor="st-left">{t('staff_left_label')}</label>
        <input id="st-left" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      </div>
      {failure ? (
        <div className="banner error" role="alert">
          <WarningIcon />
          <span>{failure}</span>
        </div>
      ) : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={busy}
          onClick={() => void confirm()}
        >
          {t('staff_leave')}
        </button>
      </div>
    </Sheet>
  )
}

type Open =
  | { sheet: 'create'; kind: StaffKind }
  | { sheet: 'edit'; row: Row }
  | { sheet: 'leave'; row: Row }
  | null

export function Staff() {
  const { t, lang } = useT()
  const { resource, reload } = useResource((signal) => listStaff(signal), [])
  const [open, setOpen] = useState<Open>(null)
  const [snack, setSnack] = useState<string | null>(null)

  const done = (text: string) => {
    setOpen(null)
    setSnack(text)
    reload()
  }
  // Edit or mark left only from a read the server just confirmed.
  const fresh = resource.state === 'loaded' && !resource.refreshing && resource.error === null

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('staff_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('staff_title')} body={t('staff_empty')} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list">
          {resource.data.map((row) => {
            const left = row.status === 'left'
            return (
              <li key={row.staff_id}>
                <div className="row" style={left ? { opacity: 0.6 } : undefined}>
                  <span className="grow">
                    <span className="title">{row.display_name}</span>
                    <br />
                    <span className="meta">
                      {[
                        row.kind === 'other'
                          ? (row.role_label ?? t('staff_kind_other'))
                          : t('staff_kind_teacher'),
                        row.phone ? formatPhone(row.phone) : null,
                        payLine(row, t),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                    <br />
                    <span className="meta">
                      {left && row.left_on
                        ? t('staff_status_left', formatShortDate(row.left_on, lang))
                        : t(accessKey(row))}
                    </span>
                  </span>
                  {left ? null : (
                    <>
                      <button
                        type="button"
                        className="btn btn-text btn-small"
                        disabled={!fresh}
                        onClick={() => setOpen({ sheet: 'edit', row })}
                      >
                        {t('staff_edit')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-text btn-small"
                        disabled={!fresh}
                        onClick={() => setOpen({ sheet: 'leave', row })}
                      >
                        {t('staff_leave')}
                      </button>
                    </>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </>
    )

  return (
    <>
      <TopBar
        title={t('staff_title')}
        subtitle={t('staff_sub')}
        actions={
          <>
            <button
              type="button"
              className="btn btn-tonal btn-small"
              onClick={() => setOpen({ sheet: 'create', kind: 'other' })}
            >
              {t('staff_add_other')}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-small"
              onClick={() => setOpen({ sheet: 'create', kind: 'teacher' })}
            >
              <PlusIcon size={18} />
              {t('staff_invite_teacher')}
            </button>
          </>
        }
      />
      {body}
      {open?.sheet === 'create' ? (
        <StaffSheet
          kind={open.kind}
          onClose={() => setOpen(null)}
          onSaved={() => done(t('staff_saved'))}
        />
      ) : null}
      {open?.sheet === 'edit' ? (
        <StaffSheet
          kind={open.row.kind}
          row={open.row}
          onClose={() => setOpen(null)}
          onSaved={() => done(t('staff_saved'))}
        />
      ) : null}
      {open?.sheet === 'leave' ? (
        <LeaveSheet
          row={open.row}
          onClose={() => setOpen(null)}
          onLeft={() => done(t('staff_marked_left', open.row.display_name))}
        />
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
