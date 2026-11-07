/**
 * "Where students pay": the list, and the add / edit form
 * (`PaymentMethodsScreen.kt`, `MethodEditorScreen.kt`).
 *
 * The empty state matters: until a method exists, students and guardians
 * have nowhere to send a fee and are told to ask the teacher.
 */
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatPhone } from '../../../core/format'
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
import { WarningIcon } from '../../../ui/icons'
import { paths } from '../paths'
import {
  createPaymentMethod,
  listPaymentMethods,
  retirePaymentMethod,
  updatePaymentMethod,
} from './api'
import {
  canSave,
  draftOf,
  emptyDraft,
  providerOptions,
  requestOf,
  rowOf,
  withKind,
  type MethodDraft,
  type MethodKind,
  type MethodRow,
} from './methods'

export function PaymentMethods() {
  const { t, message } = useT()
  const { resource, reload } = useResource(() => listPaymentMethods().then((m) => m.map(rowOf)), [])
  const [removing, setRemoving] = useState<MethodRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [snack, setSnack] = useState<string | null>(null)

  async function remove(row: MethodRow) {
    setBusy(true)
    try {
      await retirePaymentMethod(row.methodId)
      setRemoving(null)
      reload()
    } catch (e) {
      setSnack(
        e instanceof ApiError
          ? e.offline
            ? t('web_money_offline_nothing_changed')
            : message(e.messageKey, e.details)
          : t('error_unexpected'),
      )
    } finally {
      setBusy(false)
    }
  }

  const add = (
    <div className="button-row">
      <Link className="btn btn-tonal" to={paths.paymentMethodNew('mobile')}>
        {t('payment_methods_add_mobile')}
      </Link>
      <Link className="btn btn-tonal" to={paths.paymentMethodNew('bank')}>
        {t('payment_methods_add_bank')}
      </Link>
    </div>
  )

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={2} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('payment_methods_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = (
      <div className="card">
        <EmptyState
          title={t('payment_methods_empty_title')}
          body={t('payment_methods_empty_body')}
          action={add}
        />
      </div>
    )
  else {
    // Changes need the list as the server has it now.
    const fresh = resource.error === null && !resource.refreshing
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <p className="meta">{t('payment_methods_intro')}</p>
        <ul className="card flush list">
          {resource.data.map((row) => (
            <li key={row.methodId} className="row" style={{ alignItems: 'flex-start' }}>
              <div className="grow">
                <div className="title">{row.title}</div>
                <div>{row.kind === 'mobile' ? formatPhone(row.detail) : row.detail}</div>
                {row.extra ? <div className="meta">{row.extra}</div> : null}
                {row.note ? <div className="meta">“{row.note}”</div> : null}
              </div>
              {fresh ? (
                <div className="end">
                  <Link
                    className="btn btn-text btn-small"
                    to={paths.paymentMethodEdit(row.methodId)}
                  >
                    {t('profile_edit')}
                  </Link>
                  <button
                    type="button"
                    className="btn btn-text btn-small money-danger-text"
                    onClick={() => setRemoving(row)}
                  >
                    {t('payment_methods_remove')}
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        {fresh ? add : null}
      </>
    )
  }

  return (
    <>
      <TopBar title={t('payment_methods_title')} back="/more" />
      {body}
      {removing ? (
        <Sheet
          title={t('payment_methods_remove_title')}
          subtitle={`${removing.title} · ${removing.kind === 'mobile' ? formatPhone(removing.detail) : removing.detail}`}
          onClose={() => setRemoving(null)}
        >
          <p className="meta">{t('payment_methods_remove_body')}</p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-danger btn-money"
              disabled={busy}
              onClick={() => void remove(removing)}
            >
              {t('payment_methods_remove')}
            </button>
            <button
              type="button"
              className="btn btn-text btn-money"
              onClick={() => setRemoving(null)}
            >
              {t('payment_methods_keep')}
            </button>
          </div>
        </Sheet>
      ) : null}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}

/** Add a method (`?kind=mobile|bank`). */
export function NewPaymentMethod() {
  const [search] = useSearchParams()
  const kind: MethodKind = search.get('kind') === 'bank' ? 'bank' : 'mobile'
  return <MethodEditor initial={emptyDraft(kind)} methodId={null} />
}

/** Edit a method: read from the list, since there is no single-method read. */
export function EditPaymentMethod() {
  const { methodId = '' } = useParams()
  const { t } = useT()
  const { resource, reload } = useResource(
    () => listPaymentMethods().then((all) => all.find((m) => m.method_id === methodId) ?? null),
    [methodId],
  )
  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('method_editor_title_edit')} back={paths.paymentMethods()} />
        <Loading rows={3} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('method_editor_title_edit')} back={paths.paymentMethods()} />
        <ErrorCard title={t('method_editor_title_edit')} error={resource.error} onRetry={reload} />
      </>
    )
  }
  if (!resource.data) {
    return (
      <>
        <TopBar title={t('method_editor_title_edit')} back={paths.paymentMethods()} />
        <EmptyState title={t('fees_not_available')} />
      </>
    )
  }
  return <MethodEditor initial={draftOf(resource.data)} methodId={methodId} />
}

function MethodEditor({ initial, methodId }: { initial: MethodDraft; methodId: string | null }) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const [draft, setDraft] = useState<MethodDraft>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const editing = methodId !== null
  const set = (patch: Partial<MethodDraft>) => setDraft((d) => ({ ...d, ...patch }))
  const options = draft.kind === 'mobile' ? providerOptions(draft.provider) : []

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSave(draft) || saving) return
    setSaving(true)
    setError(null)
    try {
      const body = requestOf(draft)
      await (methodId ? updatePaymentMethod(methodId, body) : createPaymentMethod(body))
      navigate(paths.paymentMethods(), { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.offline
            ? t('web_money_offline_nothing_changed')
            : message(err.messageKey, err.details)
          : t('error_unexpected'),
      )
      setSaving(false)
    }
  }

  const field = (key: keyof MethodDraft, label: string, extra: Record<string, string> = {}) => (
    <div className="field">
      <label htmlFor={`pm-${key}`}>{label}</label>
      <input
        id={`pm-${key}`}
        value={draft[key]}
        onChange={(e) => set({ [key]: e.target.value } as Partial<MethodDraft>)}
        {...extra}
      />
    </div>
  )

  return (
    <>
      <TopBar
        title={editing ? t('method_editor_title_edit') : t('method_editor_title_add')}
        back={paths.paymentMethods()}
      />
      <form className="card" onSubmit={onSubmit} noValidate>
        {!editing ? (
          <div className="segmented" role="group" aria-label={t('method_editor_title_add')}>
            {(['mobile', 'bank'] as const).map((k) => (
              <button
                key={k}
                type="button"
                aria-pressed={draft.kind === k}
                onClick={() => setDraft((d) => withKind(d, k))}
              >
                {t(`method_kind_${k}`)}
              </button>
            ))}
          </div>
        ) : null}

        {draft.kind === 'mobile' ? (
          <>
            {field('provider', t('method_service_label'), { autoComplete: 'off' })}
            <span className="help">{t('method_service_help')}</span>
            {options.length > 0 ? (
              <div className="chips" style={{ marginTop: 8 }}>
                {options.map((o) =>
                  o.kind === 'service' ? (
                    <button
                      key={o.name}
                      type="button"
                      className="chip chip-filter"
                      aria-pressed={draft.provider === o.name}
                      onClick={() => set({ provider: o.name })}
                    >
                      {o.name}
                    </button>
                  ) : (
                    <span key="typed" className="chip chip-neutral">
                      {t('method_service_use', o.text)}
                    </span>
                  ),
                )}
              </div>
            ) : null}
            {field('mobileNumber', t('method_number_label'), {
              inputMode: 'tel',
              autoComplete: 'off',
            })}
          </>
        ) : (
          <>
            {field('provider', t('method_bank_name_label'))}
            <span className="help">{t('method_bank_help')}</span>
            {field('accountName', t('method_account_name_label'))}
            {field('accountNumber', t('method_account_number_label'), { autoComplete: 'off' })}
            {field('branchName', t('method_branch_label'))}
          </>
        )}

        <div className="field">
          <label htmlFor="pm-note">{t('method_note_label')}</label>
          <textarea
            id="pm-note"
            value={draft.note}
            onChange={(e) => set({ note: e.target.value })}
          />
        </div>

        {error ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            <WarningIcon />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="button-row">
          <button
            type="submit"
            className="btn btn-primary btn-money"
            disabled={!canSave(draft) || saving}
          >
            {saving ? t('method_saving') : t('method_save')}
          </button>
        </div>
      </form>
    </>
  )
}
