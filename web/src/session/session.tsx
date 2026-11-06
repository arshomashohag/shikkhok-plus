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
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { readMe, type Schemas } from '../api/endpoints'
import { ApiError, UNEXPECTED_KEY } from '../api/errors'
import {
  clearTokens,
  onTokensChanged,
  readTokens,
  saveTokens,
  type TokenResponse,
} from '../api/tokens'
import { reconcileWorkspace, storeWorkspace } from '../api/workspace'

export type Lens = 'teacher' | 'student' | 'guardian'

export interface LensOption {
  lens: Lens
  count: number
}

export type Session =
  | { state: 'signed-out' }
  | { state: 'resolving' }
  | { state: 'failed'; error: ApiError }
  | {
      state: 'ready'
      me: Schemas['MeResponse']
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
const LENSES: readonly Lens[] = ['teacher', 'student', 'guardian']

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

interface SessionValue {
  session: Session
  signIn: (tokens: TokenResponse) => void
  signOut: () => void
  chooseLens: (lens: Lens) => void
  /** Act on another workspace; every screen re-reads under it. */
  chooseWorkspace: (id: string) => void
  /** Re-read `/v1/me`, e.g. after accepting an invitation or creating a first batch. */
  refresh: () => void
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(() => readTokens() !== null)
  const [session, setSession] = useState<Session>(() =>
    readTokens() ? { state: 'resolving' } : { state: 'signed-out' },
  )
  const [nonce, setNonce] = useState(0)

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
      return
    }
    let live = true
    setSession((s) => (s.state === 'ready' ? s : { state: 'resolving' }))
    readMe().then(
      (me) => {
        if (!live) return
        const options = readLenses(me.lenses)
        setSession({
          state: 'ready',
          me,
          options,
          ...resolveLens(options, storedLens()),
          workspace: reconcileWorkspace(me.workspaces ?? []),
        })
      },
      (e: unknown) => {
        if (!live) return
        const error =
          e instanceof ApiError ? e : new ApiError(0, 'UNEXPECTED', UNEXPECTED_KEY, true)
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

  const signIn = useCallback((tokens: TokenResponse) => {
    saveTokens(tokens)
    setSignedIn(true)
    setNonce((n) => n + 1)
  }, [])

  const signOut = useCallback(() => {
    clearTokens()
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

  const refresh = useCallback(() => setNonce((n) => n + 1), [])

  // Opened offline: try again by itself the moment the connection returns.
  useEffect(() => {
    if (session.state !== 'failed') return
    window.addEventListener('online', refresh)
    return () => window.removeEventListener('online', refresh)
  }, [session.state, refresh])

  const value = useMemo(
    () => ({ session, signIn, signOut, chooseLens, chooseWorkspace, refresh }),
    [session, signIn, signOut, chooseLens, chooseWorkspace, refresh],
  )
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession outside SessionProvider')
  return value
}

/** The signed-in session; for screens that only render when ready. */
export function useReadySession() {
  const { session, ...rest } = useSession()
  if (session.state !== 'ready') throw new Error('useReadySession before the session is ready')
  return { session, ...rest }
}
