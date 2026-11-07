import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/errors'
import { translate } from '../../i18n/i18n'
import {
  filterWorkspaces,
  isNotAdmin,
  mapAdminTicket,
  mapRequester,
  mapWorkspaces,
  platformUsage,
  requesterDetail,
  requesterLabel,
  share,
  statusParam,
  workspaceName,
} from './mappers'

const t = (key: string, ...args: (string | number)[]) => translate('en', key, ...args)

describe('requester labels: the administrator boundary [TC-14]', () => {
  it('names a teacher, and a centre member with their centre', () => {
    const teacher = mapRequester({ ref: 'a1b2c3d4e5', roles: ['teacher'], name: 'Karim Uddin' })
    expect(requesterLabel(teacher, t)).toBe('Karim Uddin')
    expect(requesterDetail(teacher, t)).toBe('Teacher · #A1B2C3D4E5')

    const member = mapRequester({
      ref: 'ffff000011',
      roles: ['centre_member'],
      name: 'Nasrin',
      centre: 'Alo Coaching',
    })
    expect(requesterLabel(member, t)).toBe('Nasrin · Alo Coaching')
  })

  it('shows a student or guardian only as role and reference', () => {
    const student = mapRequester({ ref: 'a1b2c3d4e5', roles: ['student'] })
    expect(requesterLabel(student, t)).toBe('Student · #A1B2C3D4E5')
    expect(requesterDetail(student, t)).toBeNull()
    const both = mapRequester({ ref: '0123456789', roles: ['guardian', 'student'] })
    expect(requesterLabel(both, t)).toBe('Student, Guardian · #0123456789')
  })

  it('drops a name that arrives for someone who is only a student or guardian', () => {
    const leaked = mapRequester({
      ref: 'a1b2c3d4e5',
      roles: ['guardian'],
      name: 'Rokeya Jahan',
      centre: 'Alo Coaching',
    })
    expect(leaked.name).toBeNull()
    expect(leaked.centre).toBeNull()
    expect(requesterLabel(leaked, t)).not.toContain('Rokeya')
    expect(requesterLabel(leaked, t)).toBe('Guardian · #A1B2C3D4E5')
  })

  it('says so when the account holds no role now', () => {
    expect(requesterLabel(mapRequester({ ref: 'abcabcabca', roles: [] }), t)).toBe(
      'No role now · #ABCABCABCA',
    )
  })

  it('maps a ticket with an unknown platform', () => {
    const ticket = mapAdminTicket({
      ticket_id: 't1',
      subject: 'S',
      status: 'open',
      platform: null,
      created_at: '2026-11-01T00:00:00Z',
      updated_at: '2026-11-01T00:00:00Z',
      message_count: 2,
      preview: 'p',
      requester: { ref: 'a1b2c3d4e5', roles: ['student'] },
    })
    expect(ticket.platform).toBeNull()
    expect(ticket.requester.name).toBeNull()
  })
})

describe('workspaces', () => {
  const list = mapWorkspaces({
    workspaces: [
      {
        workspace_id: 'w1',
        kind: 'teacher',
        name: 'Karim Uddin',
        platforms: ['android'],
        joined_at: '2026-10-01T00:00:00Z',
        ref: 'a1b2c3d4e5',
      },
      {
        workspace_id: 'w2',
        kind: 'centre',
        name: null,
        platforms: [],
        joined_at: '2026-10-02T00:00:00Z',
      },
      {
        workspace_id: 'w3',
        kind: 'teacher',
        name: null,
        platforms: ['web', 'android'],
        joined_at: '2026-10-03T00:00:00Z',
      },
    ],
  })

  it('labels unnamed teachers and centres', () => {
    expect(list.map((w) => workspaceName(w, t))).toEqual([
      'Karim Uddin',
      'Unnamed centre',
      'Unnamed teacher',
    ])
    expect(list[1]!.lastSeenAt).toBeNull()
    expect(list[1]!.ref).toBeNull()
  })

  it('filters on the name only, ignoring case and spaces', () => {
    expect(filterWorkspaces(list, '  karim ').map((w) => w.id)).toEqual(['w1'])
    expect(filterWorkspaces(list, '')).toHaveLength(3)
    expect(filterWorkspaces(list, 'nobody')).toEqual([])
  })
})

describe('overview helpers', () => {
  it('fills an app the server has not reported with zeros', () => {
    const usage = platformUsage({
      platforms: [{ platform: 'web', accounts: 3, active_7_days: 2, active_30_days: 3 }],
    } as Parameters<typeof platformUsage>[0])
    expect(usage).toEqual([
      { platform: 'android', accounts: 0, active7: 0, active30: 0 },
      { platform: 'web', accounts: 3, active7: 2, active30: 3 },
    ])
  })

  it('gives a bar width in whole percent, and 0 with no total', () => {
    expect(share(1, 3)).toBe(33)
    expect(share(3, 3)).toBe(100)
    expect(share(5, 0)).toBe(0)
    expect(share(0, 10)).toBe(0)
  })

  it('reads only known statuses from the address', () => {
    expect(statusParam('open')).toBe('open')
    expect(statusParam('closed')).toBe('closed')
    expect(statusParam('bogus')).toBeNull()
    expect(statusParam(null)).toBeNull()
  })

  it('treats a 403 as not an administrator', () => {
    expect(isNotAdmin(new ApiError(403, 'FORBIDDEN', 'authz.lens.not_available', false))).toBe(true)
    expect(isNotAdmin(new ApiError(500, 'UNEXPECTED', 'error.unexpected', true))).toBe(false)
  })
})
