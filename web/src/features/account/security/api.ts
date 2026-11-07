/**
 * The two-step verification settings' calls. Each needs a connection and
 * a signed-in session; the status read is in `status.ts`, which the
 * shell's entry row shares.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'

export type Proof = { code: string } | { recovery_code: string }

/** A new secret for an authenticator app (409 `mfa.already_enabled`). */
export const beginSetup = () => request<Schemas['MfaSetupResponse']>('POST', '/v1/me/mfa/setup')

/** Turn it on with the app's first code; the answer is ten recovery codes, shown once. */
export const confirmSetup = (code: string) =>
  request<Schemas['MfaRecoveryCodesResponse']>('POST', '/v1/me/mfa/confirm', { body: { code } })

/** Turn it off (409 `mfa.not_enabled` or `mfa.required_for_admin`). */
export const turnOff = (proof: Proof) =>
  request<Schemas['MfaStatusResponse']>('POST', '/v1/me/mfa/disable', { body: proof })

/** Ten new recovery codes; the old ones stop working. */
export const renewCodes = (code: string) =>
  request<Schemas['MfaRecoveryCodesResponse']>('POST', '/v1/me/mfa/recovery-codes', {
    body: { code },
  })
