import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../api/endpoints'
import { MoneyFormatError } from '../../core/money'
import { duesChip, feeChipFor, mapDues, mapReview, mapToday } from './mappers'

function feeRow(patch: Partial<Schemas['RosterFeeRowResponse']>): Schemas['RosterFeeRowResponse'] {
  return {
    enrollment_id: 'e1',
    display_name: 'জান্নাতুল',
    outstanding: '3600.00',
    current_period: '2026-10',
    current_status: 'unpaid',
    days_overdue: null,
    due_date: '2026-10-10',
    verifying: null,
    state: null,
    history_line: null,
    ...patch,
  }
}

describe('feeChipFor — BatchDetailMapper.chipFor precedence', () => {
  it('a payment being checked outranks everything', () => {
    expect(feeChipFor(feeRow({ verifying: '800.00', days_overdue: 40 }))).toMatchObject({
      kind: 'verifying',
    })
  })
  it('then overdue, with the server’s day count', () => {
    expect(feeChipFor(feeRow({ days_overdue: 68 }))).toMatchObject({ kind: 'overdue', days: 68 })
  })
  it.each([
    ['partly_paid', 'partial'],
    ['paid', 'paid'],
    ['waived', 'waived'],
    ['unpaid', 'due'],
  ])('then the month status %s → %s', (status, kind) => {
    expect(
      feeChipFor(
        feeRow({ current_status: status as Schemas['RosterFeeRowResponse']['current_status'] }),
      )?.kind,
    ).toBe(kind)
  })
  it('shows nothing for no row or an unknown status', () => {
    expect(feeChipFor(undefined)).toBeNull()
    expect(feeChipFor(feeRow({ current_status: 'something_new' as 'paid' }))).toBeNull()
  })
})

describe('money crossing into a screen model', () => {
  const today: Schemas['TodayResponse'] = {
    date: '2026-10-17',
    has_batches: true,
    outstanding: { total: '48600.00', overdue: '31200.00', overdue_students: 12, batch_count: 7 },
    classes: [],
    to_verify: [],
    to_verify_count: 0,
  }

  it('maps the strings the server sends', () => {
    const model = mapToday(today)
    expect(model.outstanding.total.format()).toBe('৳48,600')
    expect(model.outstanding.overdue.format()).toBe('৳31,200')
  })

  it('refuses a number where money belongs, rather than showing it', () => {
    const broken = {
      ...today,
      outstanding: { ...today.outstanding, total: 48600 as unknown as string },
    }
    expect(() => mapToday(broken)).toThrow(MoneyFormatError)
  })

  it('maps a payment review without computing anything', () => {
    const review = mapReview({
      submission_id: 's1',
      batch_name: 'পদার্থবিজ্ঞান · Batch A',
      children: [
        {
          claim_id: 'c1',
          enrollment_id: 'e1',
          display_name: 'রাফসান',
          owed: '1200.00',
          period: '2026-10',
          approved_amount: null,
        },
      ],
      comparison: 'short',
      difference: '400.00',
      owed_together: '1200.00',
      total_amount: '800.00',
      method: { kind: 'mobile', provider: 'Nagad' },
      paid_on: '2026-10-16',
      status: 'pending',
      submitted_at: '2026-10-17T05:00:00Z',
      transaction_id: '7HQ2M0X9KD',
    } as Schemas['PaymentReviewResponse'])
    expect(review.comparison).toBe('short')
    expect(review.difference.format()).toBe('৳400')
    expect(review.channelLabel).toBe('Nagad')
  })
})

describe('dues', () => {
  it('keeps the server’s buckets and wears its day count', () => {
    const model = mapDues({
      summary: {
        count: 2,
        remindable: 1,
        total: '9600.00',
        late_total: '6000.00',
        groups: [{ bucket: 'over_30', count: 1, share: 63, total: '6000.00' }],
      },
      rows: [
        {
          enrollment_id: 'e1',
          display_name: 'A',
          batch_id: 'b1',
          batch_name: 'B',
          bucket: 'over_30',
          days_late: 68,
          outstanding: '6000.00',
          remindable: true,
        },
        {
          enrollment_id: 'e2',
          display_name: 'C',
          batch_id: 'b1',
          batch_name: 'B',
          bucket: 'not_late',
          days_late: null,
          outstanding: '3600.00',
          remindable: false,
        },
      ],
    } as Schemas['DuesResponse'])
    expect(duesChip(model.rows[0]!)).toEqual({ kind: 'overdue', days: 68, amount: null })
    expect(duesChip(model.rows[1]!)).toMatchObject({ kind: 'due' })
  })
})
