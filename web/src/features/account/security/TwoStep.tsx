/**
 * Settings → Two-step verification: whether it is on, and turning it on,
 * turning it off and getting new recovery codes.
 *
 * - **Turn on**: a new secret as a QR code and as a key in groups of
 *   four, with "Open in authenticator app" on a phone; then the app's
 *   first code; then ten recovery codes, **shown once**, with Copy all,
 *   until "I've saved them" (a reload or a closed tab asks first).
 * - **Turn off**: an authenticator code or a recovery code. Not offered
 *   when the server says it is required for the account.
 * - **New recovery codes**: an authenticator code; the new codes are
 *   shown once, the same way.
 *
 * Nothing here is stored: the secret and the codes live in this screen's
 * state and go with it. Every change is the server's; the screen shows
 * the status it answers with.
 */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ApiError } from '../../../api/errors'
import { formatDayOf } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  AuthenticatorSetup,
  RecoveryCodeList,
  useWarnBeforeUnload,
  type CopyLabels,
} from '../../../ui/authenticator'
import { sixDigits } from '../../../core/codes'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { ShieldIcon, WarningIcon } from '../../../ui/icons'
import { beginSetup, confirmSetup, renewCodes, turnOff, type Proof } from './api'
import type { TwoStepEntry } from './paths'
import { readMfaStatus, setMfaStatus, type MfaStatus } from './status'

type Flow =
  | { kind: 'status'; notice: string | null }
  | { kind: 'setup'; secret: string; uri: string }
  | { kind: 'codes'; codes: string[]; renewed: boolean }
  | { kind: 'turn-off' }
  | { kind: 'renew' }

/** At or below this many codes left, the screen says to get new ones. */
const FEW_CODES = 2

function useFailure() {
  const { t, message } = useT()
  return useCallback(
    (e: unknown) =>
      e instanceof ApiError ? message(e.messageKey, e.details) : t('error_unexpected'),
    [t, message],
  )
}

export function TwoStep() {
  const { t } = useT()
  const failure = useFailure()
  const location = useLocation()
  const navigate = useNavigate()
  const { resource, reload } = useResource(readMfaStatus, [])
  const [flow, setFlow] = useState<Flow>({ kind: 'status', notice: null })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const autoStarted = useRef(false)

  // Every answer reaches the More entry and the home prompt too.
  const status = resource.state === 'loaded' ? resource.data : null
  useEffect(() => {
    if (status) setMfaStatus(status)
  }, [status])

  const start = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const setup = await beginSetup()
      setFlow({ kind: 'setup', secret: setup.secret, uri: setup.otpauth_uri })
    } catch (e) {
      setError(failure(e))
      if (e instanceof ApiError && e.messageKey === 'mfa.already_enabled') reload()
    } finally {
      setBusy(false)
    }
  }, [failure, reload])

  // "Turn on" from the home prompt opens straight into the setup, once.
  const wantsStart = (location.state as TwoStepEntry | null)?.start === true
  useEffect(() => {
    if (!wantsStart || !status || autoStarted.current) return
    autoStarted.current = true
    navigate(location.pathname, { replace: true, state: null })
    if (!status.enabled) void start()
  }, [wantsStart, status, start, navigate, location.pathname])

  const done = (notice: string) => {
    setFlow({ kind: 'status', notice })
    setError(null)
    reload()
  }

  const title = t('web_mfa_title')
  if (resource.state === 'loading')
    return (
      <>
        <TopBar title={title} back="/more" />
        <Loading rows={2} />
      </>
    )
  if (resource.state === 'failed')
    return (
      <>
        <TopBar title={title} back="/more" />
        <ErrorCard title={t('error_unexpected')} error={resource.error} onRetry={reload} />
      </>
    )

  let body
  switch (flow.kind) {
    case 'setup':
      body = (
        <SetupStep
          key={flow.secret}
          secret={flow.secret}
          uri={flow.uri}
          onConfirmed={(codes) => setFlow({ kind: 'codes', codes, renewed: false })}
          onCancel={() => setFlow({ kind: 'status', notice: null })}
        />
      )
      break
    case 'codes':
      body = (
        <CodesStep
          codes={flow.codes}
          renewed={flow.renewed}
          onSaved={() => done(t(flow.renewed ? 'web_mfa_codes_renewed' : 'web_mfa_turned_on'))}
        />
      )
      break
    case 'turn-off':
      body = (
        <ProofStep
          title={t('web_mfa_off_title')}
          body={t('web_mfa_off_body')}
          submit={t('web_mfa_turn_off')}
          allowRecovery
          danger
          onProof={async (proof) => {
            setMfaStatus(await turnOff(proof))
            done(t('web_mfa_turned_off'))
          }}
          onCancel={() => setFlow({ kind: 'status', notice: null })}
        />
      )
      break
    case 'renew':
      body = (
        <ProofStep
          title={t('web_mfa_renew_title')}
          body={t('web_mfa_renew_body')}
          submit={t('web_mfa_renew_submit')}
          onProof={async (proof) => {
            if (!('code' in proof)) return
            const { recovery_codes } = await renewCodes(proof.code)
            setFlow({ kind: 'codes', codes: recovery_codes, renewed: true })
          }}
          onCancel={() => setFlow({ kind: 'status', notice: null })}
        />
      )
      break
    case 'status':
      body = (
        <StatusCard
          status={resource.data}
          notice={flow.notice}
          error={error}
          busy={busy}
          onTurnOn={() => void start()}
          onTurnOff={() => {
            setError(null)
            setFlow({ kind: 'turn-off' })
          }}
          onRenew={() => {
            setError(null)
            setFlow({ kind: 'renew' })
          }}
        />
      )
      break
  }

  return (
    <>
      <TopBar title={title} back="/more" />
      {body}
    </>
  )
}

// ----------------------------------------------------------------- status

function StatusCard({
  status,
  notice,
  error,
  busy,
  onTurnOn,
  onTurnOff,
  onRenew,
}: {
  status: MfaStatus
  notice: string | null
  error: string | null
  busy: boolean
  onTurnOn: () => void
  onTurnOff: () => void
  onRenew: () => void
}) {
  const { t, lang } = useT()
  const few = status.enabled && status.recovery_codes_left <= FEW_CODES
  return (
    <>
      {notice ? (
        <div className="banner" role="status" style={{ marginBottom: 12 }}>
          {notice}
        </div>
      ) : null}
      <div className="card mfa-status">
        <div className="mfa-status-head">
          <span className={status.enabled ? 'mfa-badge on' : 'mfa-badge'} aria-hidden="true">
            <ShieldIcon size={24} />
          </span>
          <div className="grow">
            <div className="title">
              {t(status.enabled ? 'web_mfa_status_on' : 'web_mfa_status_off')}
            </div>
            {status.enabled && status.enabled_at ? (
              <div className="meta">
                {t('web_mfa_on_since', formatDayOf(status.enabled_at, lang))}
              </div>
            ) : null}
          </div>
          {status.required ? (
            <span className="chip chip-neutral">{t('web_mfa_required')}</span>
          ) : status.recommended && !status.enabled ? (
            <span className="chip chip-recommended">{t('web_mfa_recommended')}</span>
          ) : null}
        </div>
        <p className="meta">{t('web_mfa_intro')}</p>
        {status.required ? <p className="meta">{t('web_mfa_required_body')}</p> : null}
        {status.enabled ? (
          few ? (
            <div className="banner error" role="status">
              <WarningIcon />
              <span>{t('web_mfa_codes_low', status.recovery_codes_left)}</span>
            </div>
          ) : (
            <p className="meta">{t('web_mfa_codes_left', status.recovery_codes_left)}</p>
          )
        ) : null}
        {error ? (
          <div className="banner error" role="alert" style={{ marginTop: 12 }}>
            {error}
          </div>
        ) : null}
        <div className="button-row">
          {status.enabled ? (
            <>
              <button type="button" className="btn btn-outline" onClick={onRenew}>
                {t('web_mfa_new_codes')}
              </button>
              {status.required ? null : (
                <button type="button" className="btn btn-danger" onClick={onTurnOff}>
                  {t('web_mfa_turn_off')}
                </button>
              )}
            </>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-money"
              disabled={busy}
              onClick={onTurnOn}
            >
              {t('web_mfa_turn_on')}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ setup

function SetupStep({
  secret,
  uri,
  onConfirmed,
  onCancel,
}: {
  secret: string
  uri: string
  onConfirmed: (codes: string[]) => void
  onCancel: () => void
}) {
  const { t } = useT()
  const failure = useFailure()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLInputElement>(null)
  const copy = useCopyLabels('web_mfa_copy')

  useEffect(() => {
    if (!busy) ref.current?.focus({ preventScroll: true })
  }, [busy])

  async function confirm(value: string) {
    setBusy(true)
    setError(null)
    try {
      onConfirmed((await confirmSetup(value)).recovery_codes)
    } catch (e) {
      setError(failure(e))
      setCode('')
      setBusy(false)
    }
  }

  function onChange(value: string) {
    const digits = sixDigits(value)
    setCode(digits)
    if (digits.length === 6 && !busy) void confirm(digits)
  }

  return (
    <div className="card">
      <h2 className="mfa-step-title">{t('web_mfa_setup_title')}</h2>
      <p className="meta">{t('web_mfa_setup_body')}</p>
      <AuthenticatorSetup
        secret={secret}
        uri={uri}
        secretTestId="mfa-secret"
        labels={{
          ...copy,
          qr: t('web_mfa_qr_label'),
          openApp: t('web_mfa_open_app'),
          keyLabel: t('web_mfa_key_label'),
        }}
      />
      <div className="field">
        <label htmlFor="mfa-confirm">{t('web_mfa_confirm_label')}</label>
        <input
          ref={ref}
          id="mfa-confirm"
          name="totp"
          className="otp-input"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          disabled={busy}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby="mfa-confirm-help"
        />
        <span id="mfa-confirm-help" className="help">
          {busy ? t('auth_checking_code') : t('auth_code_auto_checks')}
        </span>
        {error ? (
          <span className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
      <div className="button-row">
        <button type="button" className="btn btn-text" disabled={busy} onClick={onCancel}>
          {t('action_cancel')}
        </button>
      </div>
    </div>
  )
}

function useCopyLabels(copyKey: string): CopyLabels {
  const { t } = useT()
  return { copy: t(copyKey), copied: t('web_mfa_copied'), failed: t('web_mfa_copy_failed') }
}

// ------------------------------------------------------------------ codes

function CodesStep({
  codes,
  renewed,
  onSaved,
}: {
  codes: string[]
  renewed: boolean
  onSaved: () => void
}) {
  const { t } = useT()
  const copy = useCopyLabels('web_mfa_copy_all')
  // Shown once: a reload or a closed tab asks first.
  useWarnBeforeUnload(true)
  return (
    <div className="card">
      <h2 className="mfa-step-title">{t('web_mfa_codes_title')}</h2>
      {renewed ? <p className="meta">{t('web_mfa_codes_renewed')}</p> : null}
      <div className="banner error" role="alert" style={{ marginTop: 12 }}>
        <WarningIcon />
        <span>{t('web_mfa_codes_warning')}</span>
      </div>
      <p className="meta">{t('web_mfa_codes_where')}</p>
      <RecoveryCodeList codes={codes} label={t('web_mfa_codes_label')} copy={copy} />
      <div className="button-row">
        <button type="button" className="btn btn-primary btn-money" onClick={onSaved}>
          {t('web_mfa_codes_saved')}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ proof

/** Turn off, or new codes: prove the factor with a code (or a recovery code). */
function ProofStep({
  title,
  body,
  submit,
  allowRecovery,
  danger,
  onProof,
  onCancel,
}: {
  title: string
  body: string
  submit: string
  allowRecovery?: boolean
  danger?: boolean
  onProof: (proof: Proof) => Promise<void>
  onCancel: () => void
}) {
  const { t } = useT()
  const failure = useFailure()
  const [recoveryMode, setRecoveryMode] = useState(false)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!busy) ref.current?.focus({ preventScroll: true })
  }, [busy, recoveryMode])

  const typed = recoveryMode ? value.trim().toUpperCase() : value
  const ready = recoveryMode ? typed.length > 0 : typed.length === 6

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    setError(null)
    try {
      await onProof(recoveryMode ? { recovery_code: typed } : { code: typed })
    } catch (err) {
      const wrongRecovery =
        recoveryMode && err instanceof ApiError && err.messageKey === 'mfa.code_wrong'
      setError(wrongRecovery ? t('web_mfa_recovery_wrong') : failure(err))
      if (!recoveryMode) setValue('')
      setBusy(false)
    }
  }

  const id = recoveryMode ? 'mfa-proof-recovery' : 'mfa-proof-code'
  return (
    <form className="card" onSubmit={(e) => void onSubmit(e)} noValidate>
      <h2 className="mfa-step-title">{title}</h2>
      <p className="meta">{body}</p>
      <div className="field">
        <label htmlFor={id}>
          {t(recoveryMode ? 'web_mfa_recovery_label' : 'web_mfa_code_label')}
        </label>
        {recoveryMode ? (
          <input
            ref={ref}
            key="recovery"
            id={id}
            name="recovery_code"
            className="mono recovery-input"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="ABCDE-FGHJK"
            maxLength={24}
            value={value}
            disabled={busy}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={error ? true : undefined}
          />
        ) : (
          <input
            ref={ref}
            key="code"
            id={id}
            name="totp"
            className="otp-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={value}
            disabled={busy}
            onChange={(e) => setValue(sixDigits(e.target.value))}
            aria-invalid={error ? true : undefined}
          />
        )}
        {error ? (
          <span className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
      <div className="button-row">
        <button
          type="submit"
          className={danger ? 'btn btn-destructive' : 'btn btn-primary'}
          disabled={busy || !ready}
        >
          {busy ? t('auth_checking_code') : submit}
        </button>
        <button type="button" className="btn btn-text" disabled={busy} onClick={onCancel}>
          {t('action_cancel')}
        </button>
      </div>
      {allowRecovery ? (
        <div className="button-row">
          <button
            type="button"
            className="btn btn-text"
            disabled={busy}
            onClick={() => {
              setRecoveryMode((r) => !r)
              setValue('')
              setError(null)
            }}
          >
            {recoveryMode ? t('web_mfa_use_app') : t('web_mfa_use_recovery')}
          </button>
        </div>
      ) : null}
    </form>
  )
}
