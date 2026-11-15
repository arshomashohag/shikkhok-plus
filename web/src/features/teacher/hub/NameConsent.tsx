/**
 * "Show my name on the centre's public listing": one toggle per accepted
 * centre membership of the signed-in account. The membership list and
 * each current choice are the server's; the toggle asks, and shows the
 * server's answer. A failed write leaves the box as it was and offers
 * Retry (TC-8). Renders nothing for an account with no centre.
 */
import { useState } from 'react'
import { listCentreMemberships, setPublicNameConsent, type Schemas } from '../../../api/endpoints'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { Section } from '../../../ui/components'
import { failureText, FailureBanner } from './hubUi'

type Membership = Schemas['CentreMembershipResponse']

function Row({ m }: { m: Membership }) {
  const { t, message } = useT()
  const [consent, setConsent] = useState(m.public_name_consent)
  const [wanted, setWanted] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function send(next: boolean) {
    setBusy(true)
    setFailure(null)
    setWanted(next)
    try {
      await setPublicNameConsent(m.centre_id, next)
      setConsent(next)
      setWanted(null)
    } catch (e) {
      // The box stays at what the server last said.
      setFailure(`${t('web_hub_consent_failed')} ${failureText(e, t, message)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li>
      <div className="row">
        <span className="grow">
          <span className="title" style={{ overflowWrap: 'anywhere' }}>
            {m.centre_name}
          </span>
          <br />
          <label className="meta" style={{ cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={consent}
              disabled={busy}
              onChange={(e) => void send(e.target.checked)}
            />{' '}
            {t('web_hub_consent_toggle')}
          </label>
        </span>
      </div>
      {failure ? (
        <FailureBanner
          text={failure}
          onRetry={wanted === null ? undefined : () => void send(wanted)}
        />
      ) : null}
    </li>
  )
}

export function NameConsent() {
  const { t } = useT()
  const { resource } = useResource((signal) => listCentreMemberships(signal), [])
  if (resource.state !== 'loaded' || resource.data.length === 0) return null
  return (
    <Section title={t('web_hub_consent_title')}>
      <ul className="card flush list">
        {resource.data.map((m) => (
          <Row key={m.member_id} m={m} />
        ))}
      </ul>
      <p className="meta">{t('web_hub_consent_help')}</p>
    </Section>
  )
}
