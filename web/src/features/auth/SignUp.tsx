/**
 * Create an account. On success the server sends a code to the number,
 * and the person continues on the sign-in screen's code step.
 *
 * Validation here is **format only** — a name present, a mobile number's
 * shape, a 4-digit postcode. Whether the number may sign up is the
 * server's decision, shown through its `message_key`.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { signUp } from '../../api/endpoints'
import { ApiError } from '../../api/errors'
import { normalisePhone } from '../../core/format'
import { toLatinDigits } from '../../core/money'
import { AuthFrame } from './AuthFrame'
import { GraduationIcon, LayersIcon, TeacherIcon, UsersIcon } from '../../ui/icons'
import { useT } from '../../i18n/i18n'

type Role = 'teacher' | 'coaching' | 'student' | 'guardian'
type FieldName = 'centre' | 'name' | 'phone' | 'house' | 'road' | 'city' | 'postcode'

const ROLE_ICONS = {
  teacher: TeacherIcon,
  coaching: LayersIcon,
  student: GraduationIcon,
  guardian: UsersIcon,
} as const

export function SignUp() {
  const { t, message } = useT()
  const navigate = useNavigate()
  const [role, setRole] = useState<Role>('teacher')
  const [values, setValues] = useState<Record<FieldName, string>>({
    centre: '',
    name: '',
    phone: '',
    house: '',
    road: '',
    city: '',
    postcode: '',
  })
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    document.title = `${t('signup_title')} · ShikkhokPlus`
  }, [t])

  const set = (name: FieldName) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [name]: e.target.value }))

  function validate(): { phone: string; postcode: string } | null {
    const next: Partial<Record<FieldName, string>> = {}
    if (role === 'coaching' && !values.centre.trim()) next.centre = t('signup_centre_name_required')
    if (!values.name.trim()) next.name = t('signup_name_required')
    const phone = normalisePhone(values.phone)
    if (!phone) next.phone = t('phone_invalid')
    for (const f of ['house', 'road', 'city'] as const) {
      if (!values[f].trim()) next[f] = t('address_required')
    }
    const postcode = toLatinDigits(values.postcode.trim())
    if (!/^[0-9]{4}$/.test(postcode)) next.postcode = t('address_postcode_invalid')
    setErrors(next)
    return Object.keys(next).length === 0 && phone ? { phone, postcode } : null
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    const ok = validate()
    if (!ok) return
    setBusy(true)
    try {
      await signUp({
        role,
        self_name: values.name.trim(),
        phone: ok.phone,
        address_house: values.house.trim(),
        address_road: values.road.trim(),
        address_city: values.city.trim(),
        address_postcode: ok.postcode,
        ...(role === 'coaching' ? { centre_name: values.centre.trim() } : {}),
      })
      navigate('/signin', { replace: true, state: { phone: ok.phone } })
    } catch (err) {
      setFormError(err instanceof ApiError ? message(err.messageKey) : t('error_unexpected'))
      setBusy(false)
    }
  }

  const field = (name: FieldName, label: string, props: Record<string, string> = {}) => (
    <div className="field">
      <label htmlFor={`su-${name}`}>{label}</label>
      <input
        id={`su-${name}`}
        value={values[name]}
        onChange={set(name)}
        aria-invalid={errors[name] ? true : undefined}
        aria-describedby={errors[name] ? `su-${name}-error` : undefined}
        {...props}
      />
      {errors[name] ? (
        <span id={`su-${name}-error`} className="field-error">
          {errors[name]}
        </span>
      ) : null}
    </div>
  )

  return (
    <AuthFrame wide>
      <form onSubmit={onSubmit} noValidate>
        <h1>{t('signup_title')}</h1>
        <p className="meta">{t('signup_subhead')}</p>

        <fieldset className="field">
          <legend>{t('signup_role_label')}</legend>
          <div className="role-tiles" role="group">
            {(['teacher', 'coaching', 'student', 'guardian'] as const).map((r) => {
              const Icon = ROLE_ICONS[r]
              return (
                <button
                  key={r}
                  type="button"
                  className="role-tile"
                  aria-pressed={role === r}
                  onClick={() => setRole(r)}
                >
                  <Icon size={28} />
                  {t(`signup_role_${r}`)}
                </button>
              )
            })}
          </div>
          <span className="help">{t(`signup_role_help_${role}`)}</span>
        </fieldset>

        {role === 'coaching' ? field('centre', t('signup_centre_name_label')) : null}

        <div className="form-2">
          <div>
            {field('name', t('signup_name_label'), { autoComplete: 'name' })}
            <span className="help">{t('signup_name_help')}</span>
          </div>
          <div>
            {field('phone', t('signup_phone_label'), {
              type: 'tel',
              inputMode: 'tel',
              autoComplete: 'tel-national',
              placeholder: t('auth_phone_hint'),
            })}
            <span className="help">{t('signup_phone_help')}</span>
          </div>
          {field('house', t('address_house_label'), { autoComplete: 'address-line1' })}
          {field('road', t('address_road_label'), { autoComplete: 'address-line2' })}
          {field('city', t('address_city_label'), { autoComplete: 'address-level2' })}
          {field('postcode', t('address_postcode_label'), {
            inputMode: 'numeric',
            autoComplete: 'postal-code',
            maxLength: '4',
          })}
        </div>

        {formError ? (
          <div className="banner error" role="alert" style={{ marginTop: 16 }}>
            {formError}
          </div>
        ) : null}

        <div className="button-row">
          <button type="submit" className="btn btn-primary btn-money" disabled={busy}>
            {busy ? t('signup_submitting') : t('signup_submit_generic')}
          </button>
        </div>
        <p className="meta" style={{ marginTop: 24 }}>
          {t('signup_have_account')} <Link to="/signin">{t('signup_log_in')}</Link>
        </p>
      </form>
    </AuthFrame>
  )
}
