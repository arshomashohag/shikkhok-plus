import { describe, expect, it } from 'vitest'
import { translate } from '../../i18n/i18n'
import {
  BODY_MAX,
  fieldProblem,
  mapList,
  mapThread,
  newQuestion,
  STATUS_CHIP,
  STATUS_KEY,
  SUBJECT_MAX,
  textLength,
} from './mappers'

const ticket = {
  ticket_id: 't1',
  subject: 'Cannot add a student',
  status: 'answered' as const,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-02T10:00:00Z',
  has_new_reply: true,
  preview: 'Try the number without +88',
}

describe('help mappers', () => {
  it('says each status in the asker’s words, and in both languages', () => {
    expect(translate('en', STATUS_KEY.open)).toBe('With support')
    expect(translate('en', STATUS_KEY.answered)).toBe('Answered')
    expect(translate('en', STATUS_KEY.closed)).toBe('Closed')
    for (const key of Object.values(STATUS_KEY)) {
      expect(translate('bn', key)).not.toBe(key)
      expect(translate('bn', key)).not.toBe(translate('en', key))
    }
    expect(new Set(Object.values(STATUS_CHIP)).size).toBe(3)
  })

  it('keeps the server’s new-reply flag and count, never a tally of its own', () => {
    const list = mapList({
      tickets: [ticket, { ...ticket, ticket_id: 't2', has_new_reply: false }],
      new_replies: 5,
    })
    expect(list.newReplies).toBe(5)
    expect(list.tickets.map((t) => t.newReply)).toEqual([true, false])
    expect(list.tickets[0]).toMatchObject({ id: 't1', status: 'answered', subject: ticket.subject })
  })

  it('marks which messages are support’s', () => {
    const thread = mapThread({
      ticket,
      messages: [
        { message_id: 'm1', author: 'requester', body: 'Help', created_at: ticket.created_at },
        { message_id: 'm2', author: 'support', body: 'Sure', created_at: ticket.updated_at },
      ],
    })
    expect(thread.messages.map((m) => m.fromSupport)).toEqual([false, true])
  })

  it('checks format only: blank, and over the server’s limits after trimming', () => {
    expect(fieldProblem('   ', SUBJECT_MAX)).toBe('required')
    expect(fieldProblem(' a ', SUBJECT_MAX)).toBeNull()
    expect(fieldProblem('x'.repeat(SUBJECT_MAX), SUBJECT_MAX)).toBeNull()
    expect(fieldProblem('x'.repeat(SUBJECT_MAX + 1), SUBJECT_MAX)).toBe('too_long')
    expect(fieldProblem(`  ${'x'.repeat(BODY_MAX)}  `, BODY_MAX)).toBeNull()
    // Bangla counts as the server counts it: one per code point.
    expect(textLength(' শিক্ষক ')).toBe([...'শিক্ষক'].length)
  })

  it('sends the question trimmed', () => {
    expect(newQuestion('  Subject ', '\nBody\n')).toEqual({ subject: 'Subject', body: 'Body' })
  })
})
