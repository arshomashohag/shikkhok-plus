/** Fee history, payment methods, collections and the dashboard: pure mappings. */
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { MoneyFormatError } from '../../../core/money'
import {
  filterOf,
  headlineMonth,
  mapBatchMonth,
  mapCollections,
  seatKind,
  visibleSeats,
} from './collections'
import { mapDashboard } from './dashboard'
import { CYCLE_WORD, HISTORY_FORMAT, mapFeeHistory, STRIP_WORD } from './fees'
import { dhakaPeriod, isPeriod, shiftPeriod } from './format'
import {
  canSave,
  emptyDraft,
  providerOptions,
  requestOf,
  rowOf,
  withKind,
  type MethodDraft,
} from './methods'

describe('fee history', () => {
  const dto: Schemas['FeeHistoryResponse'] = {
    cycles: [
      {
        period: '2026-09',
        charged: '1200.00',
        outstanding: '0.00',
        status: 'paid',
        due_date: '2026-09-10',
      },
      {
        period: '2026-11',
        charged: '1200.00',
        outstanding: '1200.00',
        status: 'unpaid',
        due_date: '2026-11-10',
      },
      {
        period: '2026-10',
        charged: '1200.00',
        outstanding: '400.00',
        status: 'partly_paid',
        due_date: '2026-10-10',
      },
    ],
    total_outstanding: '1600.00',
    month_states: [
      {
        period: '2026-10',
        state: 'checking',
        history_line: {
          amount: '400.00',
          channel: 'bKash',
          paid_on: '2026-11-04',
          status: 'pending',
          covered_names: ['Tasnim'],
          decision_note: null,
        },
      },
    ],
  }

  it('lists cycles newest first, with the server’s figures', () => {
    const h = mapFeeHistory(dto)
    if (h.kind !== 'loaded') throw new Error('expected loaded')
    expect(h.rows.map((r) => r.period)).toEqual(['2026-11', '2026-10', '2026-09'])
    expect(h.rows.map((r) => r.settled)).toEqual([false, false, true])
    expect(h.totalOutstanding.format()).toBe('৳1,600')
    expect(h.months[0]).toMatchObject({ kind: 'checking', line: { outcome: 'pending' } })
    expect(h.months[0]?.line?.coveredNames).toEqual(['Tasnim'])
  })

  it('says nothing has been charged rather than everything is paid', () => {
    expect(mapFeeHistory({ cycles: [], total_outstanding: '0.00' })).toEqual({ kind: 'empty' })
  })

  it('names a status it does not know as unknown, never settled, keeping the server’s figures', () => {
    const newer = {
      ...dto,
      cycles: [{ ...dto.cycles[0]!, status: 'forgiven' as 'paid' }, ...dto.cycles.slice(1)],
      month_states: [
        {
          ...dto.month_states![0]!,
          state: 'disputed' as 'paid',
          history_line: { ...dto.month_states![0]!.history_line!, status: 'held' as 'pending' },
        },
      ],
    }
    const h = mapFeeHistory(newer)
    if (h.kind !== 'loaded') throw new Error('expected loaded')
    const sept = h.rows.find((r) => r.period === '2026-09')
    expect(sept).toMatchObject({ status: 'unknown', settled: false })
    expect(sept?.outstanding.format()).toBe('৳0')
    expect(CYCLE_WORD[sept!.status]).toBe('web_status_unknown')
    expect(h.months[0]).toMatchObject({ kind: 'unknown', line: { outcome: 'unknown' } })
    expect(STRIP_WORD.unknown).toBe('web_status_unknown')
    expect(HISTORY_FORMAT.unknown).toBe('web_history_line_unknown')
    // The other rows are unaffected.
    expect(h.rows.filter((r) => r.status !== 'unknown')).toHaveLength(2)
  })

  it('still refuses a numeric amount: a broken contract, not a newer vocabulary', () => {
    const numeric = { ...dto, total_outstanding: 1600 as unknown as string }
    expect(() => mapFeeHistory(numeric)).toThrow(MoneyFormatError)
  })
})

describe('payment methods', () => {
  it('shows a bank account by its end only', () => {
    expect(
      rowOf({
        method_id: 'm1',
        kind: 'bank',
        provider: 'DBBL',
        account_name: 'M Rahman',
        account_number: '1234567890',
        branch_name: 'Dhanmondi',
        mobile_number: null,
        note: '  ',
      }),
    ).toEqual({
      methodId: 'm1',
      kind: 'bank',
      title: 'DBBL',
      detail: 'M Rahman · ••• 7890',
      extra: 'Dhanmondi',
      note: null,
    })
  })

  it('needs a service and a number for mobile, all four fields for a bank', () => {
    const mobile: MethodDraft = { ...emptyDraft('mobile'), provider: 'bKash' }
    expect(canSave(mobile)).toBe(false)
    expect(canSave({ ...mobile, mobileNumber: '01711000001' })).toBe(true)
    const bank: MethodDraft = {
      ...emptyDraft('bank'),
      provider: 'DBBL',
      accountName: 'A',
      accountNumber: '1',
    }
    expect(canSave(bank)).toBe(false)
    expect(canSave({ ...bank, branchName: 'B' })).toBe(true)
  })

  it('sends only the fields the kind takes, trimmed', () => {
    expect(
      requestOf({
        ...emptyDraft('mobile'),
        provider: ' Nagad ',
        mobileNumber: ' 01711000001 ',
        accountName: 'left over',
        note: ' ',
      }),
    ).toEqual({ kind: 'mobile', provider: 'Nagad', mobile_number: '01711000001', note: null })
    expect(
      requestOf({
        kind: 'bank',
        provider: 'DBBL',
        accountName: 'M Rahman',
        accountNumber: '123',
        branchName: 'Dhanmondi',
        mobileNumber: '017',
        note: 'Write the student’s name',
      }),
    ).toEqual({
      kind: 'bank',
      provider: 'DBBL',
      account_number: '123',
      account_name: 'M Rahman',
      branch_name: 'Dhanmondi',
      note: 'Write the student’s name',
    })
  })

  it('clears the service when the kind changes', () => {
    expect(withKind({ ...emptyDraft('mobile'), provider: 'bKash' }, 'bank').provider).toBe('')
  })

  it('suggests known services, then the typed one when it is new', () => {
    expect(providerOptions('')).toHaveLength(3)
    expect(providerOptions('nag')).toEqual([
      { kind: 'service', name: 'Nagad' },
      { kind: 'typed', text: 'nag' },
    ])
    expect(providerOptions('Nagad')).toEqual([{ kind: 'service', name: 'Nagad' }])
    expect(providerOptions('Upay')).toEqual([{ kind: 'typed', text: 'Upay' }])
  })
})

describe('collections', () => {
  const report = mapCollections({
    months: [
      {
        period: '2026-09',
        charged: '3000.00',
        collected: '3000.00',
        charged_bar: 100,
        collected_bar: 100,
        in_progress: false,
      },
      {
        period: '2026-10',
        charged: '3000.00',
        collected: '1200.00',
        charged_bar: 100,
        collected_bar: 40,
        in_progress: false,
      },
      {
        period: '2026-11',
        charged: '3000.00',
        collected: '0.00',
        charged_bar: 100,
        collected_bar: 0,
        in_progress: true,
      },
    ],
    outstanding: '4800.00',
    owing_students: 4,
  })

  it('leads with the latest finished month unless one is chosen', () => {
    expect(headlineMonth(report.months, null)?.period).toBe('2026-10')
    expect(headlineMonth(report.months, '2026-09')?.period).toBe('2026-09')
    expect(headlineMonth(report.months, '2020-01')?.period).toBe('2026-10')
    expect(headlineMonth([], null)).toBeNull()
  })

  it('classes each seat as the server reported it', () => {
    const row = (state: string, days: number | null = null) =>
      ({ state, days_overdue: days }) as Schemas['RosterFeeRowResponse']
    expect(seatKind(row('unpaid', 12))).toBe('overdue')
    expect(seatKind(row('unpaid'))).toBe('due')
    expect(seatKind(row('checking'))).toBe('checking')
    expect(seatKind(row('something'))).toBe('none')
    expect(filterOf('waived')).toBe('paid')
    expect(filterOf('none')).toBeNull()
  })

  it('filters a month’s seats without recounting them', () => {
    const month = mapBatchMonth({
      period: '2026-10',
      charged: '3600.00',
      collected: '1200.00',
      counts: { paid: 1, checking: 1, owed: 1 },
      seats: [
        { enrollment_id: 'a', display_name: 'A', outstanding: '0.00', state: 'paid' },
        {
          enrollment_id: 'b',
          display_name: 'B',
          outstanding: '1200.00',
          state: 'checking',
          verifying: '1200.00',
        },
        {
          enrollment_id: 'c',
          display_name: 'C',
          outstanding: '1200.00',
          state: 'unpaid',
          days_overdue: 25,
        },
        { enrollment_id: 'd', display_name: 'D', outstanding: '0.00', state: null },
      ] as Schemas['RosterFeeRowResponse'][],
    })
    expect(month.counts).toEqual({ paid: 1, checking: 1, owed: 1 })
    expect(visibleSeats(month.seats, 'all')).toHaveLength(4)
    expect(visibleSeats(month.seats, 'owed').map((s) => s.enrollmentId)).toEqual(['c'])
    expect(visibleSeats(month.seats, 'checking')[0]?.verifying?.format()).toBe('৳1,200')
  })
})

describe('dashboard', () => {
  it('keeps the server’s percentages and direction', () => {
    const d = mapDashboard({
      tiles: {
        attendance_percent: 90,
        present: 9,
        held: 10,
        exam_average_percent: null,
        direction: 'up',
        owed: '1200.00',
      },
      attendance_by_month: [
        { period: '2026-10', held: 0, present: 0, percent: null, in_progress: false },
      ],
      exams: [],
      fee_months: [{ period: '2026-10', state: 'paid' }],
    })
    expect(d.attendancePercent).toBe(90)
    expect(d.direction).toBe('up')
    expect(d.owed.format()).toBe('৳1,200')
    expect(d.attendance[0]?.percent).toBeNull()
    expect(d.feeMonths[0]).toMatchObject({ kind: 'paid', line: null })
  })
})

describe('periods', () => {
  it('walks months across years', () => {
    expect(shiftPeriod('2026-01', -1)).toBe('2025-12')
    expect(shiftPeriod('2026-12', 1)).toBe('2027-01')
    expect(shiftPeriod('2026-10', 0)).toBe('2026-10')
  })

  it('knows the month in Dhaka, not UTC', () => {
    // 20:30 UTC on 31 Oct is 02:30 on 1 Nov in Dhaka.
    expect(dhakaPeriod(new Date('2026-10-31T20:30:00Z'))).toBe('2026-11')
  })

  it('accepts only a real period', () => {
    expect(isPeriod('2026-10')).toBe(true)
    expect(isPeriod('2026-13')).toBe(false)
    expect(isPeriod('oct')).toBe(false)
  })
})
