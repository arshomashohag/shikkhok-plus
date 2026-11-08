/**
 * Edit profile: name and the four-part address. The phone is the login
 * and cannot change. As Android: Save is offered only for a complete
 * address, a blank name is sent as "leave it", and the profile is read
 * from the server first so the form never starts from a stale copy.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { ApiError } from '../../../api/errors'
import type { Me } from '../../../api/endpoints'
import { formatPhone } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { readProfile, saveProfile } from './api'
import { isComplete, postalOf, postcodeIsValid, profileUpdate, type PostalAddress } from './mappers'
import './account.css'

export function EditProfile() {
  const { t } = useT()
  const { resource, reload } = useResource((signal) => readProfile(signal), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('edit_profile_title')} error={resource.error} onRetry={reload} />
  // Never edit over a profile that failed to refresh.
  else if (resource.error)
    body = <ErrorCard title={t('edit_profile_title')} error={resource.error} onRetry={reload} />
  else body = <ProfileForm me={resource.data} />

  return (
    <>
      <TopBar title={t('edit_profile_title')} back="/more" />
      {body}
    </>
  )
}

type Field = keyof PostalAddress

function ProfileForm({ me }: { me: Me }) {
  const { t, message } = useT()
  const navigate = useNavigate()
  const { refresh } = useReadySession()
  const [name, setName] = useState(me.self_name ?? '')
  const [address, setAddress] = useState<PostalAddress>(postalOf(me))
  const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const complete = isComplete(address)
  const fieldError = (f: Field): string | null => {
    if (!touched[f]) return null
    if (f === 'postcode')
      return postcodeIsValid(address.postcode) ? null : t('address_postcode_invalid')
    return address[f].trim() ? null : t('address_required')
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!complete) {
      setTouched({ house: true, road: true, city: true, postcode: true })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveProfile(profileUpdate(name, address))
      refresh()
      navigate('/more', { state: { saved: true } })
    } catch (err) {
      setError(
        err instanceof ApiError ? message(err.messageKey, err.details) : t('error_unexpected'),
      )
      setBusy(false)
    }
  }

  const input = (f: Field, label: string, props: React.InputHTMLAttributes<HTMLInputElement>) => {
    const err = fieldError(f)
    return (
      <div className="field">
        <label htmlFor={`pf-${f}`}>{label}</label>
        <input
          id={`pf-${f}`}
          value={address[f]}
          onChange={(e) => setAddress((a) => ({ ...a, [f]: e.target.value }))}
          onBlur={() => setTouched((x) => ({ ...x, [f]: true }))}
          aria-invalid={err ? true : undefined}
          aria-describedby={err ? `pf-${f}-error` : undefined}
          {...props}
        />
        {err ? (
          <span id={`pf-${f}-error`} className="field-error">
            {err}
          </span>
        ) : null}
      </div>
    )
  }

  return (
    <form className="card" onSubmit={onSubmit} noValidate>
      <div className="field" style={{ marginTop: 0 }}>
        <label htmlFor="pf-name">{t('profile_name_label')}</label>
        <input
          id="pf-name"
          value={name}
          maxLength={120}
          autoComplete="name"
          onChange={(e) => setName(e.target.value)}
        />
        <span className="help">{t('profile_teacher_name_note')}</span>
      </div>

      <fieldset className="field">
        <legend>{t('profile_address_label')}</legend>
        {input('house', t('address_house_label'), { autoComplete: 'address-line1' })}
        {input('road', t('address_road_label'), { autoComplete: 'address-line2' })}
        {input('city', t('address_city_label'), { autoComplete: 'address-level2' })}
        {input('postcode', t('address_postcode_label'), {
          autoComplete: 'postal-code',
          inputMode: 'numeric',
          maxLength: 4,
        })}
      </fieldset>

      <div className="field">
        <span className="label">{t('profile_phone_label')}</span>
        <span className="account-phone">{me.phone ? formatPhone(me.phone) : '—'}</span>
        <span className="help">
          {me.phone ? t('profile_phone_note') : t('web_contact_add_phone_why')}
        </span>
      </div>

      {me.email !== undefined ? (
        <div className="field">
          <span className="label">{t('web_auth_email_label')}</span>
          <span className="account-phone">{me.email ?? '—'}</span>
        </div>
      ) : null}

      {error ? (
        <div className="banner error" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      ) : null}

      <div className="button-row">
        <button type="submit" className="btn btn-primary btn-money" disabled={busy || !complete}>
          {busy ? t('profile_saving') : t('profile_save')}
        </button>
      </div>
    </form>
  )
}
