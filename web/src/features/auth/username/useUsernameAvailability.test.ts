/**
 * The availability checker under fake timers [NFR8.1] [NFR8.2] [NFR8.3]
 * [NFR2.1] [TSD-5]. Requests go through the real `request()`, `send()`
 * and `renew()`, against a stubbed `fetch`.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { checkMyUsername, checkUsername } from '../../../api/endpoints'
import { readTokens, saveTokens } from '../../../api/tokens'
import { json } from '../../../test/render'
import { useUsernameAvailability, type UsernameLookup } from './useUsernameAvailability'

interface LookupCall {
  username: string
  signal: AbortSignal | null | undefined
}
let lookups: LookupCall[] = []
let refreshes = 0
type Answer = (call: LookupCall) => Response | Promise<Response>
let answer: Answer = () => json(200, { status: 'available' })
let refreshAnswer: () => Promise<Response> = async () =>
  json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })

beforeEach(() => {
  vi.useFakeTimers()
  lookups = []
  refreshes = 0
  answer = () => json(200, { status: 'available' })
  refreshAnswer = async () =>
    json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      if (url.endsWith('/v1/auth/refresh')) {
        refreshes += 1
        return refreshAnswer()
      }
      const body = JSON.parse(init.body as string) as { username: string }
      const call = { username: body.username, signal: init.signal }
      lookups.push(call)
      return answer(call)
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.removeItem('sp.session')
})

function mount(lookup: UsernameLookup = checkUsername) {
  return renderHook(() => useUsernameAvailability(lookup))
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function type(hook: ReturnType<typeof mount>, text: string) {
  act(() => hook.result.current.edited(text))
}

const never = () => new Promise<Response>(() => undefined)

describe('debounce [NFR8.1]', () => {
  it('sends nothing at 499 ms of quiet and one lookup at 500 ms', async () => {
    const hook = mount()
    type(hook, 'nadia_k')
    expect(hook.result.current.state).toEqual({ kind: 'waiting' })
    await advance(499)
    expect(lookups).toHaveLength(0)
    await advance(1)
    expect(lookups).toEqual([expect.objectContaining({ username: 'nadia_k' })])
    expect(hook.result.current.state).toMatchObject({ kind: 'answered', status: 'available' })
  })

  it('an edit restarts the wait', async () => {
    const hook = mount()
    type(hook, 'nadia')
    await advance(400)
    type(hook, 'nadia_k')
    await advance(499)
    expect(lookups).toHaveLength(0)
    await advance(1)
    expect(lookups.map((l) => l.username)).toEqual(['nadia_k'])
  })

  it('sends nothing for empty or whitespace text, and goes back to idle', async () => {
    const hook = mount()
    type(hook, '   ')
    await advance(1000)
    type(hook, 'n')
    type(hook, '')
    await advance(1000)
    expect(lookups).toHaveLength(0)
    expect(hook.result.current.state).toEqual({ kind: 'idle' })
  })

  it('sends the trimmed text', async () => {
    const hook = mount()
    type(hook, '  Rahim.Uddin ')
    await advance(500)
    expect(lookups[0]!.username).toBe('Rahim.Uddin')
  })
})

describe('latest wins, answers remembered [NFR8.2]', () => {
  it('an edit while a lookup is held open aborts it, and its late answer never renders', async () => {
    let release: (r: Response) => void = () => undefined
    answer = (call) =>
      call.username === 'nadia'
        ? new Promise<Response>((resolve) => {
            release = resolve
          })
        : json(200, { status: 'unavailable' })
    const hook = mount()
    type(hook, 'nadia')
    await advance(500)
    expect(hook.result.current.state).toEqual({ kind: 'checking' })
    type(hook, 'nadia_k')
    expect(lookups[0]!.signal?.aborted).toBe(true)
    await act(async () => {
      release(json(200, { status: 'available' }))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(hook.result.current.state).toEqual({ kind: 'waiting' })
    await advance(500)
    expect(hook.result.current.state).toMatchObject({ status: 'unavailable' })
  })

  it('a remembered text makes no call', async () => {
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    type(hook, 'nadia')
    await advance(500)
    type(hook, 'nadia_k')
    await advance(500)
    expect(lookups.map((l) => l.username)).toEqual(['nadia_k', 'nadia'])
    expect(hook.result.current.state).toMatchObject({ kind: 'answered', status: 'available' })
  })
})

describe('the checker’s own 3 s bound [NFR8.3]', () => {
  it('a lookup that ignores its signal and never settles: could-not-check at 3,000 ms, not 2,999', async () => {
    answer = never
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    await advance(2999)
    expect(hook.result.current.state).toEqual({ kind: 'checking' })
    await advance(1)
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    expect(lookups[0]!.signal?.aborted).toBe(true)
  })

  it('signed in with a stale token and the refresh held for 5 s: could-not-check at 3 s, and the rotated pair is still stored', async () => {
    saveTokens({ access_token: 'A1', refresh_token: 'R1', expires_in: 10 })
    refreshAnswer = () =>
      new Promise<Response>((resolve) => {
        setTimeout(
          () => resolve(json(200, { access_token: 'A2', refresh_token: 'R2', expires_in: 900 })),
          5000,
        )
      })
    answer = () => json(200, { status: 'available' })
    const hook = mount(checkMyUsername)
    type(hook, 'nadia_k')
    await advance(500)
    expect(refreshes).toBe(1)
    await advance(2999)
    expect(hook.result.current.state).toEqual({ kind: 'checking' })
    await advance(1)
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    // The refresh is still out: nothing can end it, and nothing should.
    expect(readTokens()?.refresh).toBe('R1')
    await advance(2000)
    expect(readTokens()).toMatchObject({ access: 'A2', refresh: 'R2' })
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    expect(refreshes).toBe(1)
  })

  it('a retired lookup answering 200 after 3 s leaves could-not-check, and the next edit checks again', async () => {
    let release: (r: Response) => void = () => undefined
    answer = () =>
      new Promise<Response>((resolve) => {
        release = resolve
      })
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(3500)
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    await act(async () => {
      release(json(200, { status: 'available' }))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    answer = () => json(200, { status: 'available' })
    type(hook, 'nadia_k2')
    await advance(500)
    expect(lookups).toHaveLength(2)
    expect(hook.result.current.state).toMatchObject({ status: 'available' })
  })
})

describe('no automatic retry, and stop after a 429 [NFR2.1]', () => {
  it('after a transport failure there is no call until an edit', async () => {
    answer = () => Promise.reject(new TypeError('Failed to fetch'))
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    await advance(10_000)
    expect(lookups).toHaveLength(1)
    type(hook, 'nadia_k2')
    await advance(500)
    expect(lookups).toHaveLength(2)
  })

  it('a refusal other than 429 is could-not-check, and is not remembered', async () => {
    answer = () =>
      json(503, {
        error: { code: 'X', message_key: 'error.temporarily_unavailable', retryable: true },
      })
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    expect(hook.result.current.state).toEqual({ kind: 'could-not-check' })
    type(hook, 'nadia')
    await advance(500)
    type(hook, 'nadia_k')
    await advance(500)
    expect(lookups).toHaveLength(3)
  })

  it('after a 429 there is no call at all, even after edits and 500 ms of quiet', async () => {
    answer = () =>
      json(429, {
        error: { code: 'CEILING', message_key: 'auth.lookup.too_many', retryable: false },
      })
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    expect(hook.result.current.state).toEqual({ kind: 'stopped' })
    type(hook, 'something_else')
    await advance(500)
    type(hook, 'and_another')
    await advance(5000)
    expect(lookups).toHaveLength(1)
    expect(hook.result.current.state).toEqual({ kind: 'stopped' })
  })
})

describe('unmounting', () => {
  it('aborts the request in flight and sends nothing more', async () => {
    answer = never
    const hook = mount()
    type(hook, 'nadia_k')
    await advance(500)
    hook.unmount()
    expect(lookups[0]!.signal?.aborted).toBe(true)
    await advance(5000)
    expect(lookups).toHaveLength(1)
  })
})
