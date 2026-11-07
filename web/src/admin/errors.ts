/**
 * The two refusals every admin screen and the log-in words specially.
 * Kept apart from the screens' mappers so the log-in, which is in the
 * first chunk, does not pull those in.
 */
import type { ApiError } from '../api/errors'

/** True when the server refused because this account is not an administrator. */
export function isNotAdmin(error: ApiError): boolean {
  return error.status === 403
}

/**
 * True when the request did not come through the admin edge: the server
 * answers a 404 with the not-available key off the admin hostname or
 * from a network not on its list, and a 404 with no envelope at all
 * means something in front of the API had no such route. A missing
 * ticket is a 404 too, but with its own key, and is not this.
 */
export function isUnavailable(error: ApiError): boolean {
  return (
    error.status === 404 &&
    (error.messageKey === 'authz.lens.not_available' || error.code === 'UNEXPECTED')
  )
}
