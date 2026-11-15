/**
 * The username availability checker, shared by sign-up, the Replace
 * step, the gate and rename [FR3.1] [FR3.2] [functional-spec § 3.1].
 *
 * - **Debounce** [NFR8.1]: a lookup is sent only after 500 ms with no
 *   edit; every edit restarts the wait; empty or whitespace sends nothing.
 * - **Latest wins** [NFR8.2]: one request in flight; a newer edit aborts
 *   the older, marking it superseded *before* aborting, so an abort is
 *   never read as a failure. Answers are remembered per trimmed text for
 *   the life of the mounted form.
 * - **Its own 3 s bound** [NFR8.3]: at 3 s the checker itself marks the
 *   request timed out, publishes could-not-check, retires it and aborts
 *   it — without waiting for it to settle, because a signed-in lookup may
 *   be waiting on a token renewal that no abort can end (and must not:
 *   NFR8.7).
 * - **No automatic retry, and stop after a 429** [NFR2.1]: a failure
 *   waits for the next edit; a 429 ends checking for this form.
 *
 * The settle step's first check is "this request is still the current
 * one, else drop". The error's type is never consulted to tell an abort
 * from a failure: the checker decides from its own flags.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { mapAvailability, type Availability } from './availability'

/** Quiet time before asking [NFR8.1]. */
export const DEBOUNCE_MS = 500
/** The longest a lookup is waited for [NFR8.3]. */
export const BOUND_MS = 3000

export type UsernameLookup = (
  username: string,
  signal: AbortSignal,
) => Promise<Schemas['UsernameAvailabilityResponse']>

interface InFlight {
  text: string
  controller: AbortController
  superseded: boolean
  timedOut: boolean
  bound: number
}

/** True for the answer that ends checking for this form. */
function isTooMany(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 429 || e.messageKey === 'auth.lookup.too_many')
}

export function useUsernameAvailability(lookup: UsernameLookup): {
  state: Availability
  edited: (text: string) => void
} {
  const [state, setState] = useState<Availability>({ kind: 'idle' })
  const lookupRef = useRef(lookup)
  const debounce = useRef<number | null>(null)
  const current = useRef<InFlight | null>(null)
  const answers = useRef(new Map<string, Availability>())
  const stopped = useRef(false)

  useEffect(() => {
    lookupRef.current = lookup
  }, [lookup])

  /** Retire whatever is in flight; it will never publish anything. */
  const supersede = useCallback(() => {
    const request = current.current
    if (!request) return
    request.superseded = true
    current.current = null
    window.clearTimeout(request.bound)
    request.controller.abort('superseded')
  }, [])

  const settle = useCallback((request: InFlight, outcome: { ok: unknown } | { error: unknown }) => {
    if (current.current !== request) return // retired: superseded or timed out
    current.current = null
    window.clearTimeout(request.bound)
    if (request.timedOut || request.superseded) return
    if ('ok' in outcome) {
      const answer = mapAvailability(outcome.ok as Schemas['UsernameAvailabilityResponse'])
      if (answer.kind === 'answered') answers.current.set(request.text, answer)
      setState(answer)
      return
    }
    if (isTooMany(outcome.error)) {
      stopped.current = true
      setState({ kind: 'stopped' })
      return
    }
    setState({ kind: 'could-not-check' })
  }, [])

  const start = useCallback(
    (text: string) => {
      const remembered = answers.current.get(text)
      if (remembered) {
        setState(remembered)
        return
      }
      const controller = new AbortController()
      const request: InFlight = { text, controller, superseded: false, timedOut: false, bound: 0 }
      request.bound = window.setTimeout(() => {
        if (current.current !== request) return
        request.timedOut = true
        current.current = null
        setState({ kind: 'could-not-check' })
        controller.abort('timeout')
      }, BOUND_MS)
      current.current = request
      setState({ kind: 'checking' })
      lookupRef.current(text, controller.signal).then(
        (ok) => settle(request, { ok }),
        (error: unknown) => settle(request, { error }),
      )
    },
    [settle],
  )

  const edited = useCallback(
    (text: string) => {
      if (debounce.current !== null) window.clearTimeout(debounce.current)
      debounce.current = null
      supersede()
      if (stopped.current) {
        setState({ kind: 'stopped' })
        return
      }
      const trimmed = text.trim()
      if (!trimmed) {
        setState({ kind: 'idle' })
        return
      }
      setState({ kind: 'waiting' })
      debounce.current = window.setTimeout(() => {
        debounce.current = null
        start(trimmed)
      }, DEBOUNCE_MS)
    },
    [start, supersede],
  )

  // Leaving the form ends the wait and the request.
  useEffect(
    () => () => {
      if (debounce.current !== null) window.clearTimeout(debounce.current)
      supersede()
    },
    [supersede],
  )

  return { state, edited }
}
