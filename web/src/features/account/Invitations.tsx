/**
 * Places a teacher has offered this number. Accepting grants the lens —
 * which is an authorization change, so it is the server's to make; this
 * screen asks, then re-reads `/v1/me` to learn what changed.
 */
import { useState } from 'react'
import { acceptInvitation, declineInvitation, listInvitations } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { Money } from '../../core/money'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { useSession } from '../../session/session'
import { EmptyState, ErrorCard, Loading, Snackbar, TopBar } from '../../ui/components'

export function Invitations() {
  const { t, message } = useT()
  const { refresh } = useSession()
  const { resource, reload } = useResource(() => listInvitations(), [])
  const [busy, setBusy] = useState<string | null>(null)
  const [snack, setSnack] = useState<string | null>(null)

  async function answer(id: string, accept: boolean, batchName: string) {
    setBusy(id)
    try {
      await (accept ? acceptInvitation(id) : declineInvitation(id))
      setSnack(
        accept
          ? t('invitation_accepted_confirmation', batchName)
          : t('invitation_declined_confirmation', batchName),
      )
      reload()
      refresh()
    } catch (e) {
      setSnack(e instanceof ApiError ? message(e.messageKey) : t('error_unexpected'))
    } finally {
      setBusy(null)
    }
  }

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={2} />
  else if (resource.state === 'failed')
    body = (
      <ErrorCard title={t('invitations_error_title')} error={resource.error} onRetry={reload} />
    )
  else if (resource.data.length === 0)
    body = <EmptyState title={t('invitations_empty_title')} body={t('invitations_empty_body')} />
  else
    body = (
      <div className="grid-2">
        {resource.data.map((inv) => {
          const fee = Money.fromWireOrNull(inv.fee_amount)
          const forChild = inv.role === 'guardian' ? (inv.child_name ?? null) : null
          return (
            <article key={inv.enrollment_id} className="card">
              <div className="title">{inv.batch_name}</div>
              <div className="meta">
                {[
                  (inv.subject as string[]).join(', '),
                  fee ? t('invitation_fee_per_month', fee.format()) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
              <div className="meta" style={{ marginTop: 4 }}>
                {inv.decision === 'declined'
                  ? t('invitation_state_declined')
                  : t('invitation_state_pending')}
              </div>
              {forChild ? (
                <p style={{ marginBottom: 0 }}>{t('invitation_child_question', forChild)}</p>
              ) : null}
              <div className="button-row">
                <button
                  type="button"
                  className="btn btn-outline"
                  disabled={busy !== null || inv.decision === 'declined'}
                  onClick={() => void answer(inv.enrollment_id, false, inv.batch_name)}
                >
                  {forChild ? t('invitation_child_no') : t('invitation_decline')}
                </button>
                <button
                  type="button"
                  className="btn btn-primary grow"
                  disabled={busy !== null}
                  onClick={() => void answer(inv.enrollment_id, true, inv.batch_name)}
                >
                  {forChild ? t('invitation_child_yes') : t('invitation_accept')}
                </button>
              </div>
            </article>
          )
        })}
      </div>
    )

  return (
    <>
      <TopBar title={t('invitations_title')} />
      {body}
      {snack ? <Snackbar text={snack} onDismiss={() => setSnack(null)} /> : null}
    </>
  )
}
