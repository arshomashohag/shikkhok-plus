/**
 * What the username availability hint can say [FR3.1] [FR3.2].
 *
 * Only the server's four answers are shown, and `unavailable` never says
 * whether a name is taken or held [NFR1.3] [ADR-007]: there is no state
 * that could tell them apart. An answer the client does not know renders
 * as "could not check" [NFR6.3]. No state blocks submitting the form.
 */
import type { Schemas } from '../../../api/endpoints'

export type AvailabilityStatus = 'available' | 'unavailable' | 'invalid' | 'reserved'

export type Availability =
  | { kind: 'idle' }
  | { kind: 'waiting' }
  | { kind: 'checking' }
  | { kind: 'answered'; status: AvailabilityStatus; messageKey: string | null }
  | { kind: 'could-not-check' }
  /** After a 429: renders as could-not-check, and nothing more is sent. */
  | { kind: 'stopped' }

const STATUSES: readonly string[] = ['available', 'unavailable', 'invalid', 'reserved']

/** The hint for one 200 answer. Pure. */
export function mapAvailability(
  response: Pick<Schemas['UsernameAvailabilityResponse'], 'message_key'> & { status: string },
): Availability {
  if (!STATUSES.includes(response.status)) return { kind: 'could-not-check' }
  return {
    kind: 'answered',
    status: response.status as AvailabilityStatus,
    messageKey: response.message_key ?? null,
  }
}

/**
 * The text the hint shows, or null where the field's help line stays.
 *
 * @param t The string lookup
 * @param message The server-message lookup, for an `invalid` answer's key
 */
export function availabilityText(
  state: Availability,
  t: (key: string) => string,
  message: (messageKey: string) => string,
): string | null {
  switch (state.kind) {
    case 'idle':
    case 'waiting':
      return null
    case 'checking':
      return t('username_checking')
    case 'could-not-check':
    case 'stopped':
      return t('username_could_not_check')
    case 'answered':
      if (state.status === 'available') return t('username_available')
      if (state.status === 'unavailable') return t('account_username_unavailable')
      if (state.status === 'reserved') return t('account_username_reserved')
      return state.messageKey ? message(state.messageKey) : t('username_could_not_check')
  }
}
