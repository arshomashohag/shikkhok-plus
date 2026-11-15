/**
 * Who is signed in, and which lens they are looking through.
 *
 * **A lens is computed by the server per request** [TC-11] [D-2]. `/v1/me`
 * reports which lenses the account has; this module only remembers which
 * one the person last chose to *look at*, so the right tabs open. That
 * choice shapes navigation and nothing else.
 *
 * States follow `SessionStateMapper.kt`: no lens (only invitations to
 * answer), one lens (open it), several (pick, once, remembered here).
 *
 * **Behind every lens, the username gate** [FR5.2]. A read saying
 * `username_required: true` publishes `username-required`, and `App`
 * renders the choose-username gate in place of every route. It lifts
 * only on a later read saying false, never on a write's answer alone.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { revokeSession } from '../api/client'
import { readMe, type Me, type Schemas } from '../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../api/errors'
import {
  clearTokens,
  onTokensChanged,
  readTokens,
  saveTokens,
  type TokenResponse,
} from '../api/tokens'
import { reconcileWorkspace, storeWorkspace } from '../api/workspace'

export type Lens = 'teacher' | 'class_teacher' | 'student' | 'guardian'

export interface LensOption {
  lens: Lens
  count: number
}

export type Session =
  | { state: 'signed-out' }
  | { state: 'resolving' }
  | { state: 'failed'; error: ApiError }
  | { state: 'username-required'; me: Me }
  | {
      state: 'ready'
      me: Me
      options: LensOption[]
      /** Null when the account holds no lens yet. */
      lens: Lens | null
      /** True when the person must pick before anything else opens. */
      choosing: boolean
      /**
       * The workspace teacher requests act on: a tutor's own or a centre
       * they manage. Null when there is none to act on.
       */
      workspace: string | null
    }

const LENS_KEY = 'sp.lens'
const LENSES: readonly Lens[] = ['teacher', 'class_teacher', 'student', 'guardian']

export function readLenses(entries: Schemas['LensEntry'][] | undefined): LensOption[] {
  return (entries ?? []).flatMap((e) => {
    const lens = e.kind.toLowerCase() as Lens
    return LENSES.includes(lens) ? [{ lens, count: e.count }] : []
  })
}

function storedLens(): Lens | null {
  try {
    const raw = window.localStorage.getItem(LENS_KEY)
    return LENSES.includes(raw as Lens) ? (raw as Lens) : null
  } catch {
    return null
  }
}

function storeLens(lens: Lens | null): void {
  try {
    if (lens) window.localStorage.setItem(LENS_KEY, lens)
    else window.localStorage.removeItem(LENS_KEY)
  } catch {
    // The choice lasts this visit only.
  }
}

/**
 * Decide the lens from what the server reported and what was last chosen.
 * Exported for tests: this is the session's state machine.
 */
export function resolveLens(
  options: LensOption[],
  remembered: Lens | null,
): { lens: Lens | null; choosing: boolean } {
  if (options.length === 0) return { lens: null, choosing: false }
  const [only] = options
  if (options.length === 1 && only) return { lens: only.lens, choosing: false }
  const kept = options.find((o) => o.lens === remembered)
  return kept ? { lens: kept.lens, choosing: false } : { lens: null, choosing: true }
}

/**
 * What one successful `/v1/me` read publishes: the choose-username gate
 * when the server says the account has no username yet, else the app
 * [FR5.2] [NFR3.14]. An absent flag (an older server) reads as false
 * [NFR6.3]. Nothing about the app — lens or workspace — is decided
 * behind the gate. Exported for tests: with {@link resolveLens}, this is
 * the session's state machine.
 *
 * @param workspaceOf Picks the workspace to act on; called only for `ready`
 */
export function sessionFromMe(
  me: Me,
  remembered: Lens | null,
  workspaceOf: (offered: readonly { owner_id: string }[]) => string | null = reconcileWorkspace,
): Session {
  if (me.username_required === true) return { state: 'username-required', me }
  const options = readLenses(me.lenses)
  return {
    state: 'ready',
    me,
    options,
    ...resolveLens(options, remembered),
    workspace: workspaceOf(me.workspaces ?? []),
  }
}

interface SessionValue {
  session: Session
  signIn: (tokens: TokenResponse) => void
  signOut: () => void
  chooseLens: (lens: Lens) => void
  /** Act on another workspace; every screen re-reads under it. */
  chooseWorkspace: (id: string) => void
  /** Re-read `/v1/me`, e.g. after accepting an invitation or creating a first batch. */
  refresh: () => void
  /**
   * Re-read `/v1/me` and settle when that read (or a newer one that
   * superseded it) settles, whatever it published. The gate waits on
   * this rather than inferring a read's end from a changed account.
   */
  reread: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(() => readTokens() !== null)
  const [session, setSession] = useState<Session>(() =>
    readTokens() ? { state: 'resolving' } : { state: 'signed-out' },
  )
  const [nonce, setNonce] = useState(0)
  /** The newest read asked for; mirrors `nonce` so a `reread()` knows its own. */
  const asked = useRef(0)
  /** The newest read that settled (or was made moot by signing out). */
  const [settledAt, setSettledAt] = useState(0)
  /** Pending `reread()` callers, each with the read it waits for. */
  const waiting = useRef<{ at: number; resolve: () => void }[]>([])

  // Sign-out in another tab, or a refresh the server refused, ends it here.
  useEffect(
    () =>
      onTokensChanged((tokens) => {
        setSignedIn(tokens !== null)
      }),
    [],
  )

  useEffect(() => {
    if (!signedIn) {
      setSession({ state: 'signed-out' })
      // No read is coming: every pending reread() is moot.
      setSettledAt(asked.current)
      return
    }
    let live = true
    // A re-read keeps what is on screen, the gate included, so it never
    // flashes the loader [NFR8.6].
    setSession((s) =>
      s.state === 'ready' || s.state === 'username-required' ? s : { state: 'resolving' },
    )
    readMe().then(
      (me) => {
        if (!live) return
        setSession(sessionFromMe(me, storedLens()))
        setSettledAt(nonce)
      },
      (e: unknown) => {
        if (!live) return
        const error =
          e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
        setSettledAt(nonce)
        if (error.status === 401) {
          clearTokens()
          return
        }
        setSession({ state: 'failed', error })
      },
    )
    return () => {
      live = false
    }
  }, [signedIn, nonce])

  // Settle each `reread()` once what its read published is on screen, so
  // the caller sees the result rendered, or finds itself unmounted.
  useEffect(() => {
    const due = waiting.current.filter((w) => w.at <= settledAt)
    waiting.current = waiting.current.filter((w) => w.at > settledAt)
    for (const w of due) w.resolve()
  }, [settledAt, session])

  const refresh = useCallback(() => {
    asked.current += 1
    setNonce(asked.current)
  }, [])

  const reread = useCallback(
    () =>
      new Promise<void>((resolve) => {
        refresh()
        waiting.current.push({ at: asked.current, resolve })
      }),
    [refresh],
  )

  const signIn = useCallback(
    (tokens: TokenResponse) => {
      saveTokens(tokens)
      setSignedIn(true)
      refresh()
    },
    [refresh],
  )

  const signOut = useCallback(() => {
    const held = readTokens()
    clearTokens()
    if (held) void revokeSession(held.refresh)
    storeLens(null)
    storeWorkspace(null)
  }, [])

  const chooseWorkspace = useCallback((id: string) => {
    storeWorkspace(id)
    setSession((s) => (s.state === 'ready' ? { ...s, workspace: id } : s))
  }, [])

  const chooseLens = useCallback((lens: Lens) => {
    storeLens(lens)
    setSession((s) => (s.state === 'ready' ? { ...s, lens, choosing: false } : s))
  }, [])

  // Opened offline: try again by itself the moment the connection returns.
  useEffect(() => {
    if (session.state !== 'failed') return
    window.addEventListener('online', refresh)
    return () => window.removeEventListener('online', refresh)
  }, [session.state, refresh])

  const value = useMemo(
    () => ({ session, signIn, signOut, chooseLens, chooseWorkspace, refresh, reread }),
    [session, signIn, signOut, chooseLens, chooseWorkspace, refresh, reread],
  )
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession outside SessionProvider')
  return value
}

/** The session when one is ready, else null; never throws. */
export function useOptionalSession(): Extract<Session, { state: 'ready' }> | null {
  const value = useContext(SessionContext)
  return value?.session.state === 'ready' ? value.session : null
}

/** The signed-in session; for screens that only render when ready. */
export function useReadySession() {
  const { session, ...rest } = useSession()
  if (session.state !== 'ready') throw new Error('useReadySession before the session is ready')
  return { session, ...rest }
}
