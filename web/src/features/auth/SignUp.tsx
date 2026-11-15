/**
 * Create an account, with a username, a mobile number or an email
 * address, and a password. The server sends a code to the number or
 * address; the code buys a setup token, and the password chosen on the
 * form is set with it (`/v1/auth/password/setup`), which signs the
 * person in.
 *
 * **The username** [FR2.1] [functional-spec W1] is sent trimmed; blank is
 * the only rule the client holds. Its hint asks the server, after a
 * pause, whether the name could be had; it is guidance only and never
 * stands between the person and Send code [FR3.2].
 *
 * **Replace** [FR2.2] [W2]. If the name is taken while the code is being
 * confirmed, verify answers `409 account.username.unavailable`. This
 * screen keeps the code in a ref (memory only), swaps the code step for
 * the Replace step, and retries the verify with the same code and the
 * new name. A spent or expired code brings the code step back with its
 * message and the original send's Resend pacing.
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
 * **Already added** [BR2.3, BR4.5, AC1.12.2] [FR6.7]. When the phone or
 * email field is left holding a well-formed number or address, the form
 * asks the server once whether a teacher already recorded it — the same
 * moment Android asks (`SignupScreen` `onPhoneLeft`). A yes shows the
 * notice and locks the role to the seat's. The notice names neither the
 * teacher nor the batch, nor the person [C-06]: the response carries
 * none of them, so there is nothing here that could show one. An email
 * address is looked up too, since teachers record students by email.
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
  checkUsername,
  issueCode,
  lookupAlreadyAdded,
  setUpPassword,
  signUp,
  verifyCode,
  type Identifier,
  type Schemas,
  type VerifyResponse,
} from '../../api/endpoints'
import { ApiError } from '../../api/errors'
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
  RESEND_AFTER_S,
  useFailureText,
} from './parts'
import { isCodeSpent, isNameTakenMeanwhile, ReplaceUsernameStep } from './ReplaceUsernameStep'
import { GraduationIcon, LayersIcon, TeacherIcon, UsersIcon } from '../../ui/icons'
import { UsernameField } from './username/UsernameField'
import { useUsernameAvailability } from './username/useUsernameAvailability'
import { useT } from '../../i18n/i18n'

type Role = 'teacher' | 'coaching' | 'student' | 'guardian'
type FieldName =
  'centre' | 'name' | 'identifier' | 'username' | 'house' | 'road' | 'city' | 'postcode'

/**
 * Whether a server refusal of the account belongs under Username: every
 * `account.username.*` key, the 409 `unavailable` included [FR2.1].
 */
export function isUsernameKey(messageKey: string): boolean {
  return messageKey.startsWith('account.username.')
}

type Step =
  | { step: 'form' }
  | {
      step: 'code'
      identifier: Identifier
      sentTo: string
      notice: string | null
      /** Bumped each time the step is shown again, so its field starts fresh. */
      round: number
      /** When the current code was sent (epoch ms), for Resend's pacing. */
      sentAt: number
      /** Why the step is showing again, after a Replace retry spent the code. */
      error: string | null
    }
  | {
      step: 'replace'
      identifier: Identifier
      sentTo: string
      sentAt: number
      /** The username typed in the form, which the body names. */
      name: string
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

/** One key per number or address, so a phone and an email never share an answer. */
function lookupKey(identifier: Identifier | null): string | null {
  if (!identifier) return null
  return 'phone' in identifier ? `phone:${identifier.phone}` : `email:${identifier.email}`
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
  /** The person's own pick, kept apart from any lock so clearing the lock restores it. */
  const [chosenRole, setChosenRole] = useState<Role>('teacher')
  const [kind, setKind] = useState<IdentifierKind>('phone')
  const [values, setValues] = useState<Record<FieldName, string>>({
    centre: '',
    name: '',
    identifier: '',
    username: '',
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
  /**
   * The code verify accepted before saying the name was taken, held for
   * the Replace retry. Memory only: never state, route state or storage.
   */
  const heldCode = useRef<string | null>(null)
  /** The username the account is being created with, for the password manager. */
  const chosenName = useRef<string>('')
  /** The role a teacher's seat fixed for the number typed, while it applies. */
  const [added, setAdded] = useState<AddedRole | null>(null)
  // Each complete number is asked about once; the answer (or `null` for
  // no notice, including a failed lookup) is remembered for the visit.
  const answers = useRef(new Map<string, AddedRole | null>())
  // The number the field holds now, so a late answer about a number the
  // person has since changed is dropped rather than shown beside it.
  const current = useRef<string | null>(null)
  // The seat's role while the notice applies, else the person's own pick
  // (as Android's `prefilled?.lockedRole ?: chosenRole`).
  const role: Role = added ?? chosenRole
  const availability = useUsernameAvailability(checkUsername)

  useEffect(() => {
    document.title = `${t('signup_title')} · ShikkhokPlus`
  }, [t])

  // Leaving the screen drops it too.
  useEffect(
    () => () => {
      held.current = null
      heldCode.current = null
    },
    [],
  )

  const set = (name: FieldName) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [name]: e.target.value }))

  /** A username edit: the old refusal stops applying, and the hint re-checks. */
  function onUsernameChange(value: string) {
    setValues((v) => ({ ...v, username: value }))
    setErrors((e) => ({ ...e, username: undefined }))
    availability.edited(value)
  }

  /** A new number or address: an answer about the previous one stops applying. */
  function onIdentifierChange(e: { target: { value: string } }) {
    set('identifier')(e)
    current.current = lookupKey(readIdentifier(kind, e.target.value))
    setAdded(null)
  }

  /** Leaving the field: ask about a well-formed number or address, once. */
  async function onIdentifierLeft() {
    const identifier = readIdentifier(kind, values.identifier)
    const key = lookupKey(identifier)
    current.current = key
    if (!identifier || !key) return
    if (answers.current.has(key)) {
      setAdded(answers.current.get(key) ?? null)
      return
    }
    // Reserved before the request, so a second blur while it is in
    // flight does not ask again.
    answers.current.set(key, null)
    let answer: AddedRole | null = null
    try {
      answer = alreadyAddedFrom(await lookupAlreadyAdded(identifier))
    } catch {
      // Advisory only: a refused or unreachable lookup shows no notice
      // and leaves the form as it was. Sign-up itself reports its own
      // failures when the person submits.
      answer = null
    }
    answers.current.set(key, answer)
    if (current.current === key) setAdded(answer)
  }

  function validate(): { identifier: Identifier; postcode: string } | null {
    const next: Partial<Record<FieldName, string>> = {}
    if (role === 'coaching' && !values.centre.trim()) next.centre = t('signup_centre_name_required')
    if (!values.name.trim()) next.name = t('signup_name_required')
    const identifier = readIdentifier(kind, values.identifier)
    if (!identifier) next.identifier = t(invalidKey(kind))
    // Non-blank is the only username rule the client holds [FR11.3].
    if (!values.username.trim()) next.username = t('signup_username_required')
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
        username: values.username.trim(),
        ...ok.identifier,
        address_house: values.house.trim(),
        address_road: values.road.trim(),
        address_city: values.city.trim(),
        address_postcode: ok.postcode,
        ...(role === 'coaching' ? { centre_name: values.centre.trim() } : {}),
      })
      // From here the password lives only in the ref, until it is sent.
      held.current = password
      chosenName.current = values.username.trim()
      setPassword('')
      setConfirm('')
      setStep({
        step: 'code',
        identifier: ok.identifier,
        sentTo: created.code_sent_to || shownIdentifier(ok.identifier),
        notice: null,
        round: 0,
        sentAt: Date.now(),
        error: null,
      })
    } catch (err) {
      // A username refusal lands under the field; everything typed stays.
      if (err instanceof ApiError && isUsernameKey(err.messageKey))
        setErrors((e) => ({ ...e, username: failure(err) }))
      else setFormError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  /**
   * Spend the code from the code step. A name taken meanwhile is not a
   * failure of the code: the code is held, Replace opens, and this
   * resolves, so the code step never shows the 409 [W2 step 4].
   */
  async function verify(identifier: Identifier, sentTo: string, sentAt: number, code: string) {
    let answer: VerifyResponse
    try {
      answer = await verifyCode(identifier, code)
    } catch (err) {
      if (!isNameTakenMeanwhile(err)) throw err
      heldCode.current = code
      setStep({ step: 'replace', identifier, sentTo, sentAt, name: values.username.trim() })
      return
    }
    await finish(identifier, sentTo, answer)
  }

  /**
   * Retry the verify with the held code and the replacement name. A spent
   * or expired code forgets the held one and shows the code step again,
   * with why and the original Resend pacing; every other refusal is the
   * Replace step's to show [W2 step 6].
   */
  async function verifyWithReplacement(
    identifier: Identifier,
    sentTo: string,
    sentAt: number,
    username: string,
  ) {
    const code = heldCode.current ?? ''
    let answer: VerifyResponse
    try {
      answer = await verifyCode(identifier, code, username)
    } catch (err) {
      if (!isCodeSpent(err)) throw err
      heldCode.current = null
      setStep({
        step: 'code',
        identifier,
        sentTo,
        notice: null,
        round: Date.now(),
        sentAt,
        error: failure(err),
      })
      return
    }
    heldCode.current = null
    chosenName.current = username
    await finish(identifier, sentTo, answer)
  }

  /** Set the held password with the token the code bought. */
  async function finish(identifier: Identifier, sentTo: string, answer: VerifyResponse) {
    const setup = setupFrom(answer, identifier, chosenName.current || undefined)
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
          // As before this unit: the step shown again paces a fresh minute.
          sentAt: Date.now(),
          error: null,
        })
        return
      }
      // Refused on policy (too common, say): choose another with the same token.
      setStep({ step: 'choose', identifier, sentTo, setup, error: failure(err) })
    }
  }

  // Back forgets the held password and the held code [W2 step 7].
  const backToForm = useCallback(() => {
    held.current = null
    heldCode.current = null
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
              // As before this unit: the step shown again paces a fresh minute.
              sentAt: Date.now(),
              error: null,
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

  if (step.step === 'replace') {
    const { identifier, sentTo, sentAt, name } = step
    return (
      <AuthFrame>
        <ReplaceUsernameStep
          name={name}
          submit={(username) => verifyWithReplacement(identifier, sentTo, sentAt, username)}
          onBack={backToForm}
        />
      </AuthFrame>
    )
  }

  if (step.step === 'code') {
    const { identifier, sentTo, notice, round, sentAt, error } = step
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
            initialError={error}
            resendAvailableAt={sentAt + RESEND_AFTER_S * 1000}
            verify={(code) => verify(identifier, sentTo, sentAt, code)}
            resend={async () => {
              await issueCode(identifier)
              // A new code: Replace, if it comes, paces from this one.
              setStep((s) => (s.step === 'code' ? { ...s, sentAt: Date.now() } : s))
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
                  onClick={() => setChosenRole(r)}
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
        <div role="status" data-testid="signup-already-added">
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
                // The username field below is what a password manager files
                // the account under; this is a contact being confirmed.
                ...identifierInputProps(kind, 'contact'),
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

        {/* The hint is guidance; Send code is never gated on it [FR3.2]. */}
        <UsernameField
          id="su-username"
          label={t('signup_username_label')}
          help={t('signup_username_help')}
          value={values.username}
          onChange={onUsernameChange}
          availability={availability.state}
          error={errors.username}
        />

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
