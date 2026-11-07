/**
 * The three admin sign-in calls, none of which takes a token: an SMS code
 * to the number, then the authenticator step the SMS code unlocks.
 */
import type { Schemas } from '../../api/endpoints'
import { adminRequest } from '../client'

/** Answers `{}` for every number; a code goes only to an administrator's. */
export const sendAdminCode = (phone: string) =>
  adminRequest<unknown>('POST', '/v1/admin/auth/otp', { body: { phone }, anonymous: true })

/** Spends the SMS code; the challenge says whether to set up or to verify. */
export const verifyAdminCode = (phone: string, code: string) =>
  adminRequest<Schemas['AdminChallengeResponse']>('POST', '/v1/admin/auth/verify', {
    body: { phone, code },
    anonymous: true,
  })

/** Exactly one of an authenticator code and a recovery code. */
export const finishAdminSignIn = (
  challenge: string,
  proof: { code: string } | { recovery_code: string },
) =>
  adminRequest<Schemas['AdminSessionResponse']>('POST', '/v1/admin/auth/mfa', {
    body: { challenge, ...proof },
    anonymous: true,
  })
