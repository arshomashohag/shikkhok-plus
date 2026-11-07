/**
 * The pieces of an authenticator setup both apps draw: the QR code with
 * the key in groups of four and Copy, the "Open in authenticator app"
 * link for a phone, and a list of recovery codes with Copy all.
 *
 * Both the admin app's log-in and the main app's two-step verification
 * settings use these, each with its own strings, so the words are passed
 * in rather than looked up here: the main app's bundle must carry no
 * admin string, and the admin app keeps its own wording.
 *
 * This module carries the QR encoder, so the main app imports it only
 * from its lazily loaded settings screen; the plain helpers the sign-in
 * screen needs are in `core/codes.ts`.
 */
import { useEffect, useState } from 'react'
import { copyText, groupSecret } from '../core/codes'
import { QrCode } from './QrCode'

export interface CopyLabels {
  /** "Copy" or "Copy all". */
  copy: string
  copied: string
  /** Shown when the browser refuses: select and copy by hand. */
  failed: string
}

/** A Copy button that says when it worked, and says so when it did not. */
export function CopyButton({ text, labels }: { text: string; labels: CopyLabels }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  return (
    <>
      <button
        type="button"
        className="btn btn-tonal btn-small"
        onClick={() => void copyText(text).then((ok) => setState(ok ? 'copied' : 'failed'))}
      >
        {state === 'copied' ? labels.copied : labels.copy}
      </button>
      {state === 'failed' ? (
        <span className="field-error copy-failed" role="alert">
          {labels.failed}
        </span>
      ) : null}
      {state === 'copied' ? (
        <span className="visually-hidden" role="status">
          {labels.copied}
        </span>
      ) : null}
    </>
  )
}

export interface SetupLabels extends CopyLabels {
  qr: string
  openApp: string
  keyLabel: string
}

/**
 * The QR code of `uri`, the "Open in authenticator app" link on a phone
 * (where the QR code would have to be scanned by the same phone), and
 * the key for typing in by hand.
 */
export function AuthenticatorSetup({
  secret,
  uri,
  labels,
  secretTestId,
}: {
  secret: string
  uri: string
  labels: SetupLabels
  secretTestId?: string
}) {
  return (
    <div className="enroll">
      <div className="qr-frame">
        <QrCode text={uri} label={labels.qr} />
      </div>
      <a className="btn btn-tonal mobile-only open-app" href={uri}>
        {labels.openApp}
      </a>
      <div className="secret">
        <span className="help">{labels.keyLabel}</span>
        <div className="secret-row">
          <code className="secret-key" data-testid={secretTestId}>
            {groupSecret(secret)}
          </code>
          <CopyButton text={secret} labels={labels} />
        </div>
      </div>
    </div>
  )
}

/** Ten recovery codes in two columns, numbered, with Copy all below. */
export function RecoveryCodeList({
  codes,
  label,
  copy,
}: {
  codes: string[]
  label: string
  copy: CopyLabels
}) {
  return (
    <>
      <ol className="recovery-codes" aria-label={label}>
        {codes.map((c) => (
          <li key={c} className="mono">
            {c}
          </li>
        ))}
      </ol>
      <div className="button-row recovery-codes-actions">
        <CopyButton text={codes.join('\n')} labels={copy} />
      </div>
    </>
  )
}

/**
 * While codes shown once are on screen, ask before a reload or a closed
 * tab loses them.
 */
export function useWarnBeforeUnload(active: boolean): void {
  useEffect(() => {
    if (!active) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [active])
}
