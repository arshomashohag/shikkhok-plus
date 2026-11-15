/**
 * The consent sheet a listing is published through. It says what becomes
 * public and that the owner can unpublish at any time, and Publish stays
 * disabled until the box is ticked. The version sent is the one the
 * server named in its last answer, never one this client knows.
 */
import { useState } from 'react'
import { useT } from '../../../i18n/i18n'
import { Sheet } from '../../../ui/components'
import { failureText, FailureBanner } from './hubUi'

export function PublishSheet({
  consentVersion,
  onPublish,
  onClose,
}: {
  /** `consent_version_current` from the listing the person is looking at. */
  consentVersion: string
  onPublish: (consentVersion: string) => Promise<void>
  onClose: () => void
}) {
  const { t, message } = useT()
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function publish() {
    setBusy(true)
    setFailure(null)
    try {
      await onPublish(consentVersion)
    } catch (e) {
      setFailure(failureText(e, t, message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title={t('web_hub_publish_title')} onClose={onClose}>
      <p style={{ marginTop: 0 }}>{t('web_hub_publish_intro')}</p>
      <ul>
        <li>{t('web_hub_publish_item_profile')}</li>
        <li>{t('web_hub_publish_item_contact')}</li>
        <li>{t('web_hub_publish_item_batches')}</li>
      </ul>
      <p>{t('web_hub_publish_never')}</p>
      <p>{t('web_hub_publish_unpublish')}</p>
      <label className="row" style={{ cursor: 'pointer' }}>
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        <span className="grow">{t('web_hub_publish_agree')}</span>
      </label>
      {failure ? <FailureBanner text={failure} /> : null}
      <div className="button-row">
        <button type="button" className="btn btn-outline" onClick={onClose}>
          {t('action_cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary grow"
          disabled={!agreed || busy}
          onClick={() => void publish()}
        >
          {t('web_hub_publish_confirm')}
        </button>
      </div>
    </Sheet>
  )
}
