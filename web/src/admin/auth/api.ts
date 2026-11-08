/**
 * The three admin sign-in calls, none of which takes a token: a code to
 * the number (by SMS) or the address (by email), then the authenticator
 * step the code unlocks.
 */
import type { Identifier, Schemas } from '../../api/endpoints'
import { adminRequest } from '../client'

/** Answers `{}` for everyone; a code goes only to an administrator. */
export const sendAdminCode = (identifier: Identifier) =>
  adminRequest<unknown>('POST', '/v1/admin/auth/otp', { body: identifier, anonymous: true })

/** Spends the code; the challenge says whether to set up or to verify. */
export const verifyAdminCode = (identifier: Identifier, code: string) =>
  adminRequest<Schemas['AdminChallengeResponse']>('POST', '/v1/admin/auth/verify', {
    body: { ...identifier, code },
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
