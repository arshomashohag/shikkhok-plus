/**
 * Whether two-step verification is on, and whether the server suggests
 * it, for the More entry's "Recommended" label and the home prompt.
 *
 * One small store shared by every subscriber, as the inbox's unread
 * count is: the settings screen records each answer it gets
 * ({@link setMfaStatus}), so turning it on there takes the prompt and the
 * label away at once. Read once per session and kept in memory only; a
 * sign-out forgets it. Who is recommended it is the server's decision
 * (teachers and centre members), never worked out here.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import { onTokensChanged } from '../../../api/tokens'

export type MfaStatus = Schemas['MfaStatusResponse']

export const readMfaStatus = () => request<MfaStatus>('GET', '/v1/me/mfa')

let status: MfaStatus | null = null
let inFlight: Promise<void> | null = null
/** Bumped on sign-out, so an answer for the last session is dropped. */
let generation = 0
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

function load(): Promise<void> {
  const asked = generation
  inFlight ??= readMfaStatus()
    .then(
      (s) => {
        if (asked === generation) status = s
      },
      () => {
        // Keep what was known: a label is not worth an error.
      },
    )
    .finally(() => {
      inFlight = null
      emit()
    })
  return inFlight
}

/** Record the status a screen just read or changed, without a second request. */
export function setMfaStatus(value: MfaStatus): void {
  status = value
  emit()
}

/** For tests and sign-out: forget it. */
export function resetMfaStatus(): void {
  generation += 1
  status = null
  emit()
}

if (typeof window !== 'undefined') {
  onTokensChanged((tokens) => {
    if (!tokens) resetMfaStatus()
  })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The status, or null before the first answer (or when it failed). */
export function useMfaStatus(): MfaStatus | null {
  const value = useSyncExternalStore(subscribe, () => status)
  useEffect(() => {
    if (status === null) void load()
  }, [])
  return value
}

/** True when the server suggests it and it is off: the label and the prompt. */
export function isSuggested(s: MfaStatus | null): boolean {
  return s !== null && s.recommended && !s.enabled
}
