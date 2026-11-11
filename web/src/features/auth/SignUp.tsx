/**
 * Create an account, with a mobile number or an email address, and a
 * password. The server sends a code to the number or address; the code
 * buys a setup token, and the password chosen on the form is set with it
 * (`/v1/auth/password/setup`), which signs the person in.
 *
 * **The password is held in memory only**, in a ref, between the form and
 * the setup call: never in storage, never in the URL or route state, and
 * dropped as soon as it has been sent (or the person goes back). If the
 * server refuses it then — too common, say — the person chooses another
 * on the code flow's password step with the same token.
 *
 * Validation here is **format only** — a name present, a number's or an
 * address's shape, a 4-digit postcode, a password's length and that the
 * two copies match. Whether the account may sign up is the server's
 * decision, shown through its `message_key`.
 *
 * **Already added** [BR2.3, BR4.5, AC1.12.2]. When the number field is
 * left holding a well-formed mobile number, the form asks the server
 * once whether a teacher already recorded it — the same moment Android
 * asks (`SignupScreen` `onPhoneLeft`). A yes shows the notice and locks
 * the role to the seat's. The notice names neither the teacher nor the
 * batch, nor the person [C-06]: the response carries none of them, so
 * there is nothing here that could show one. An email address is never
 * looked up; the route answers for numbers only.
 *
 * The lookup is advisory. Its failure, or a yes without a role to lock,
 * shows nothing and never stands between the person and Send code.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
} from 'react'
import { Link } from 'react-router'
import {
  issueCode,
  lookupAlreadyAdded,
  setUpPassword,
  signUp,
  verifyCode,
  type Identifier,
  type Schemas,
} from '../../api/endpoints'
import { toLatinDigits } from '../../core/money'
import { useSession } from '../../session/session'
import { AuthFrame } from './AuthFrame'
import { ChoosePassword, setupFrom, setupLapsed, type PasswordSetup } from './ChoosePassword'
import {
  invalidKey,
  newPasswordProblem,
  readIdentifier,
  shownIdentifier,
  type IdentifierKind,
} from './identifier'
import {
  CodeEntry,
  describedBy,
  Field,
  identifierInputProps,
  KindToggle,
  PasswordInput,
  useFailureText,
} from './parts'
import { GraduationIcon, LayersIcon, TeacherIcon, UsersIcon } from '../../ui/icons'
import { useT } from '../../i18n/i18n'

type Role = 'teacher' | 'coaching' | 'student' | 'guardian'
type FieldName = 'centre' | 'name' | 'identifier' | 'house' | 'road' | 'city' | 'postcode'

type Step =
  | { step: 'form' }
  | {
      step: 'code'
      identifier: Identifier
      sentTo: string
      notice: string | null
      /** Bumped each time the step is shown again, so its field starts fresh. */
      round: number
    }
  | {
      step: 'choose'
      identifier: Identifier
      sentTo: string
      setup: PasswordSetup
      error: string | null
    }

/** The role a teacher's seat fixed for a number already added. */
export type AddedRole = 'teacher' | 'student' | 'guardian'

/**
 * Map the lookup's answer to the role to lock, or to no notice.
 *
 * `display_name` is deprecated and never a name [C-06], so it is not
 * read. A yes without a role is treated as no answer: locking the role
 * to a guess is worse than not locking it [BR4.5], and the lookup must
 * never block sign-up.
 */
export function alreadyAddedFrom(dto: Schemas['AlreadyAddedResponse']): AddedRole | null {
  return dto.already_added && dto.role ? dto.role : null
}

const ROLE_ICONS = {
  teacher: TeacherIcon,
  coaching: LayersIcon,
  student: GraduationIcon,
  guardian: UsersIcon,
} as const

export function SignUp() {
  const { t } = useT()
  const failure = useFailureText()
  const { signIn } = useSession()
  const [step, setStep] = useState<Step>({ step: 'form' })
  const [role, setRole] = useState<Role>('teacher')
  const [kind, setKind] = useState<IdentifierKind>('phone')
  const [values, setValues] = useState<Record<FieldName, string>>({
    centre: '',
    name: '',
    identifier: '',
    house: '',
    road: '',
    city: '',
    postcode: '',
  })
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** The chosen password, from submitting the form until it is sent. Memory only. */
  const held = useRef<string | null>(null)
  /** The role a teacher's seat fixed for the number typed, while it applies. */
  const [added, setAdded] = useState<AddedRole | null>(null)
  // Each complete number is asked about once; the answer (or `null` for
  // no notice, including a failed lookup) is remembered for the visit.
  const answers = useRef(new Map<string, AddedRole | null>())
  // The number the field holds now, so a late answer about a number the
  // person has since changed is dropped rather than shown beside it.
  const current = useRef<string | null>(null)

  useEffect(() => {
    document.title = `${t('signup_title')} · ShikkhokPlus`
  }, [t])

  // Leaving the screen drops it too.
  useEffect(
    () => () => {
      held.current = null
    },
    [],
  )

  const set = (name: FieldName) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [name]: e.target.value }))

  function apply(answer: AddedRole | null) {
    setAdded(answer)
    if (answer) setRole(answer)
  }

  /** A new number: an answer about the previous one stops applying. */
  function onIdentifierChange(e: { target: { value: string } }) {
    set('identifier')(e)
    const identifier = kind === 'phone' ? readIdentifier('phone', e.target.value) : null
    current.current = identifier && 'phone' in identifier ? identifier.phone : null
    setAdded(null)
  }

  /** Leaving the number field: ask about a complete mobile number, once. */
  async function onIdentifierLeft() {
    if (kind !== 'phone') return
    const identifier = readIdentifier('phone', values.identifier)
    const phone = identifier && 'phone' in identifier ? identifier.phone : null
    current.current = phone
    if (!phone) return
    if (answers.current.has(phone)) {
      apply(answers.current.get(phone) ?? null)
      return
    }
    // Reserved before the request, so a second blur while it is in
    // flight does not ask again.
    answers.current.set(phone, null)
    let answer: AddedRole | null = null
    try {
      answer = alreadyAddedFrom(await lookupAlreadyAdded(phone))
    } catch {
      // Advisory only: a refused or unreachable lookup shows no notice
      // and leaves the form as it was. Sign-up itself reports its own
      // failures when the person submits.
      answer = null
    }
    answers.current.set(phone, answer)
    if (current.current === phone) apply(answer)
  }

  function validate(): { identifier: Identifier; postcode: string } | null {
    const next: Partial<Record<FieldName, string>> = {}
    if (role === 'coaching' && !values.centre.trim()) next.centre = t('signup_centre_name_required')
    if (!values.name.trim()) next.name = t('signup_name_required')
    const identifier = readIdentifier(kind, values.identifier)
    if (!identifier) next.identifier = t(invalidKey(kind))
    for (const f of ['house', 'road', 'city'] as const) {
      if (!values[f].trim()) next[f] = t('address_required')
    }
    const postcode = toLatinDigits(values.postcode.trim())
    if (!/^[0-9]{4}$/.test(postcode)) next.postcode = t('address_postcode_invalid')
    const problem = newPasswordProblem(password, confirm)
    setPasswordError(problem ? t(problem) : null)
    setErrors(next)
    return Object.keys(next).length === 0 && !problem && identifier
      ? { identifier, postcode }
      : null
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    const ok = validate()
    if (!ok) return
    setBusy(true)
    try {
      const created = await signUp({
        role,
        self_name: values.name.trim(),
        ...ok.identifier,
        address_house: values.house.trim(),
        address_road: values.road.trim(),
        address_city: values.city.trim(),
        address_postcode: ok.postcode,
        ...(role === 'coaching' ? { centre_name: values.centre.trim() } : {}),
      })
      // From here the password lives only in the ref, until it is sent.
      held.current = password
      setPassword('')
      setConfirm('')
      setStep({
        step: 'code',
        identifier: ok.identifier,
        sentTo: created.code_sent_to || shownIdentifier(ok.identifier),
        notice: null,
        round: 0,
      })
    } catch (err) {
      setFormError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  /** Spend the code, then set the held password with the token it bought. */
  async function verify(identifier: Identifier, sentTo: string, code: string) {
    const setup = setupFrom(await verifyCode(identifier, code), identifier)
    const chosen = held.current
    if (setup.mfaRequired || chosen === null) {
      held.current = null
      setStep({ step: 'choose', identifier, sentTo, setup, error: null })
      return
    }
    try {
      const tokens = await setUpPassword({ token: setup.token, password: chosen })
      held.current = null
      signIn(tokens)
    } catch (err) {
      held.current = null
      if (setupLapsed(err)) {
        setStep({
          step: 'code',
          identifier,
          sentTo,
          notice: t('web_auth_setup_expired_resend'),
          round: Date.now(),
        })
        return
      }
      // Refused on policy (too common, say): choose another with the same token.
      setStep({ step: 'choose', identifier, sentTo, setup, error: failure(err) })
    }
  }

  const backToForm = useCallback(() => {
    held.current = null
    setStep({ step: 'form' })
    setFormError(null)
  }, [])

  // The setup token lapsed on the password step: a new code buys a new one.
  const restart = useCallback(
    (expired: boolean) =>
      setStep((current) =>
        current.step === 'choose'
          ? {
              step: 'code',
              identifier: current.identifier,
              sentTo: current.sentTo,
              notice: expired ? t('web_auth_setup_expired_resend') : null,
              round: Date.now(),
            }
          : current,
      ),
    [t],
  )

  if (step.step === 'choose')
    return (
      <AuthFrame>
        <ChoosePassword
          key={step.setup.token}
          setup={step.setup}
          initialError={step.error}
          onDone={signIn}
          onRestart={restart}
        />
      </AuthFrame>
    )

  if (step.step === 'code') {
    const { identifier, sentTo, notice, round } = step
    return (
      <AuthFrame>
        <div>
          <h1>{t('auth_code_label')}</h1>
          <p className="meta">
            {t('phone' in identifier ? 'web_auth_signup_sent_phone' : 'web_auth_signup_sent_email')}{' '}
            <strong>{'phone' in identifier ? shownIdentifier(identifier) : sentTo}</strong>
          </p>
          {notice ? (
            <div className="banner info" role="status" style={{ marginTop: 16 }}>
              {notice}
            </div>
          ) : null}
          <CodeEntry
            key={round}
            verify={(code) => verify(identifier, sentTo, code)}
            resend={async () => {
              await issueCode(identifier)
            }}
          >
            <button type="button" className="btn btn-text" onClick={backToForm}>
              {t('web_auth_signup_back')}
            </button>
          </CodeEntry>
        </div>
      </AuthFrame>
    )
  }

  const field = (
    name: FieldName,
    label: string,
    props: InputHTMLAttributes<HTMLInputElement> = {},
  ) => (
    <div className="field">
      <label htmlFor={`su-${name}`}>{label}</label>
      <input
        id={`su-${name}`}
        value={values[name]}
        onChange={name === 'identifier' ? onIdentifierChange : set(name)}
        onBlur={name === 'identifier' ? () => void onIdentifierLeft() : undefined}
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
        <p className="meta">{t('web_auth_signup_subhead')}</p>

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
                  disabled={added !== null && added !== r}
                  onClick={() => setRole(r)}
                >
                  <Icon size={28} />
                  {t(`signup_role_${r}`)}
                </button>
              )
            })}
          </div>
          <span className="help">{t(`signup_role_help_${role}`)}</span>
          {added ? <span className="help">{t('signup_role_locked_note')}</span> : null}
        </fieldset>

        {role === 'coaching' ? field('centre', t('signup_centre_name_label')) : null}

        {/* Always in the page, so the notice is announced when it fills. */}
        <div role="status">
          {added ? (
            <div className="banner" style={{ marginTop: 16 }}>
              <div>
                <strong>{t('signup_already_added_title')}</strong>
                <div>{t('signup_already_added_body')}</div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="form-2">
          <div>
            {field('name', t('signup_name_label'), { autoComplete: 'name' })}
            <span className="help">{t('signup_name_help')}</span>
          </div>
          <div>
            <KindToggle
              kind={kind}
              onKind={(k) => {
                setKind(k)
                setValues((v) => ({ ...v, identifier: '' }))
                current.current = null
                setAdded(null)
                setErrors((e) => ({ ...e, identifier: undefined }))
              }}
            />
            {field(
              'identifier',
              t(kind === 'phone' ? 'signup_phone_label' : 'web_auth_email_label'),
              {
                name: 'username',
                ...identifierInputProps(kind, 'username'),
                ...(kind === 'phone' ? { placeholder: t('auth_phone_hint') } : {}),
              },
            )}
            <span className="help">
              {t(kind === 'phone' ? 'web_auth_signup_phone_help' : 'web_auth_signup_email_help')}
            </span>
          </div>
          {field('house', t('address_house_label'), { autoComplete: 'address-line1' })}
          {field('road', t('address_road_label'), { autoComplete: 'address-line2' })}
          {field('city', t('address_city_label'), { autoComplete: 'address-level2' })}
          {field('postcode', t('address_postcode_label'), {
            inputMode: 'numeric',
            autoComplete: 'postal-code',
            maxLength: 4,
          })}
        </div>

        <div className="form-2">
          <Field
            id="su-password"
            label={t('web_auth_password_label')}
            help={t('web_auth_password_rule')}
            error={passwordError}
          >
            <PasswordInput
              id="su-password"
              value={password}
              onChange={setPassword}
              autoComplete="new-password"
              invalid={Boolean(passwordError)}
              describedBy={describedBy('su-password', true, Boolean(passwordError))}
            />
          </Field>
          <Field id="su-confirm" label={t('web_auth_confirm_password')}>
            <PasswordInput
              id="su-confirm"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
            />
          </Field>
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
