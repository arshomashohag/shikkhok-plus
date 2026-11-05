import type { ReactElement } from 'react'
import type { Reader } from './reader'

/**
 * A route a family area owns. `path` is relative to the seat prefix and
 * may be '' for the seat's own screen; the router mounts it under
 * `/my/:seat` for the student lens and `/child/:seat` for the guardian
 * lens, and the element reads `:seat` with useParams.
 */
export interface FamilyRoute {
  path: string
  element: (reader: Reader) => ReactElement
}

/** A route every lens has (inbox, profile). Absolute path. */
export interface AccountRoute {
  path: string
  element: ReactElement
}
