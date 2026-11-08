/**
 * The two ways a person names their account — a mobile number or an
 * email address — and the one password rule a client may check.
 *
 * Validation here is **format only** [TC-9]: a number's shape, an email
 * address's shape, a password's length. Whether the account exists, the
 * address may be used, or a password is too common is the server's
 * decision, shown through its `message_key`.
 */
import type { Identifier } from '../../api/endpoints'
import { formatPhone, normalisePhone } from '../../core/format'

export type IdentifierKind = 'phone' | 'email'

/** The server's limits, in Unicode code points. */
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 128

/** The server's limit on an email address. */
const EMAIL_MAX = 254

/**
 * Turn what was typed into an {@link Identifier}, or null when its shape
 * is wrong. A phone number is normalised as before; an email address is
 * trimmed and lowercased, as the server does.
 */
export function readIdentifier(kind: IdentifierKind, typed: string): Identifier | null {
  if (kind === 'phone') {
    const phone = normalisePhone(typed)
    return phone ? { phone } : null
  }
  const email = typed.trim().toLowerCase()
  if (email.length > EMAIL_MAX || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return null
  return { email }
}

/** The string resource for an identifier of `kind` whose shape is wrong. */
export function invalidKey(kind: IdentifierKind): string {
  return kind === 'phone' ? 'phone_invalid' : 'web_auth_email_invalid'
}

/** How an identifier is shown back to the person. */
export function shownIdentifier(identifier: Identifier): string {
  return 'phone' in identifier ? formatPhone(identifier.phone) : identifier.email
}

/**
 * The string resource for a new password the server would refuse on
 * length alone, or null. Length is counted in code points, as the server
 * counts it, so a Bangla password is not measured in UTF-16 halves.
 */
export function passwordLengthProblem(password: string): string | null {
  const length = [...password].length
  if (length < PASSWORD_MIN) return 'web_auth_password_short'
  if (length > PASSWORD_MAX) return 'web_auth_password_long'
  return null
}

/** Length first, then whether the confirmation matches; null when both are fine. */
export function newPasswordProblem(password: string, confirm: string): string | null {
  return (
    passwordLengthProblem(password) ?? (password === confirm ? null : 'web_auth_password_mismatch')
  )
}
