import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { Money, MoneyFormatError } from '../../../core/money'
import {
  attemptFor,
  childPayBatches,
  dhakaToday,
  firstName,
  initialBatch,
  initialSelection,
  joinNames,
  mapPayments,
  myPayBatches,
  nextPayable,
  outcomeOf,
  requestOf,
  suggestedAmount,
  toggleSeat,
  type PayChoice,
  type PayForm,
} from './mappers'

const bkash: Schemas['PaymentMethodResponse'] = {
  method_id: 'm-bkash',
  kind: 'mobile',
  provider: 'bKash',
  mobile_number: '01711000001',
  account_name: null,
  account_number: null,
  branch_name: null,
  note: null,
}
const bank: Schemas['PaymentMethodResponse'] = {
  ...bkash,
  method_id: 'm-bank',
  kind: 'bank',
  provider: 'DBBL',
  mobile_number: null,
  account_number: '1234567',
}
const form = (patch: Partial<PayForm> = {}): PayForm => ({
  amount: '1200',
  paidOn: '2026-11-04',
  transactionId: '',
  fromAccount: '',
  note: '',
  ...patch,
})
const mobile: PayChoice = { kind: 'method', method: bkash }

describe('seats and batches', () => {
  const home = {
    children: [
      {
        key: 'k1',
        display_name: 'তাসনিম জাহান',
        batch_count: 2,
        batches: [
          { enrollment_id: 't-a', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
          { enrollment_id: 't-b', batch_name: 'Math B', teacher_display_name: 'Mahfuz' },
        ],
      },
      {
        key: 'k2',
        display_name: 'আয়ান রহমান',
        batch_count: 1,
        batches: [
          { enrollment_id: 'y-a', batch_name: 'Physics A', teacher_display_name: 'Mahfuz' },
        ],
      },
    ],
  } as Schemas['GuardianHomeResponse']

  it('groups a guardian’s children by batch, so siblings pay together', () => {
    const batches = childPayBatches(home)
    expect(batches.map((b) => [b.name, b.seats.map((s) => s.childName)])).toEqual([
      ['Physics A', ['তাসনিম জাহান', 'আয়ান রহমান']],
      ['Math B', ['তাসনিম জাহান']],
    ])
  })

  it('opens on the seat from the URL, alone; otherwise every seat in the first batch', () => {
    const batches = childPayBatches(home)
    expect(initialBatch(batches, 't-b')?.name).toBe('Math B')
    const physics = initialBatch(batches, 'y-a')!
    expect(initialSelection(physics, 'y-a')).toEqual(['y-a'])
    expect(initialSelection(physics, null)).toEqual(['t-a', 'y-a'])
    expect(initialBatch(batches, 'unknown')?.name).toBe('Physics A')
    expect(initialBatch([], 'x')).toBeNull()
  })

  it('toggles a sibling in batch order and never empties the choice', () => {
    const physics = childPayBatches(home)[0]!
    expect(toggleSeat(physics, ['y-a'], 't-a')).toEqual(['t-a', 'y-a'])
    expect(toggleSeat(physics, ['t-a', 'y-a'], 't-a')).toEqual(['y-a'])
    expect(toggleSeat(physics, ['y-a'], 'y-a')).toEqual(['y-a'])
  })

  it('a student’s own seats carry no child name', () => {
    const batches = myPayBatches([
      { enrollment_id: 'e1', batch_name: 'Physics A', teacher_display_name: null },
    ] as Schemas['StudentBatchResponse'][])
    expect(batches[0]).toMatchObject({
      teacherName: null,
      seats: [{ enrollmentId: 'e1', childName: null }],
    })
  })
})

describe('requestOf — the payment the form describes', () => {
  it('a mobile payment quotes the transaction ID and no account', () => {
    expect(requestOf(['e1'], mobile, form({ transactionId: ' bjk400q1il ' })).request).toEqual({
      enrollment_ids: ['e1'],
      payment_method_id: 'm-bkash',
      cash: false,
      amount: '1200.00',
      paid_on: '2026-11-04',
      transaction_id: 'bjk400q1il',
      from_account: null,
      note: null,
    })
  })

  it('a bank payment names the paying account and no transaction ID', () => {
    const r = requestOf(
      ['e1', 'e2'],
      { kind: 'method', method: bank },
      form({ fromAccount: '9876', note: ' for Oct ' }),
    )
    expect(r.request).toMatchObject({
      enrollment_ids: ['e1', 'e2'],
      payment_method_id: 'm-bank',
      transaction_id: null,
      from_account: '9876',
      note: 'for Oct',
    })
  })

  it('cash quotes neither and names no method', () => {
    expect(requestOf(['e1'], { kind: 'cash' }, form({ amount: '৳১,২০০' })).request).toMatchObject({
      payment_method_id: null,
      cash: true,
      amount: '1200.00',
      transaction_id: null,
      from_account: null,
    })
  })

  it('an incomplete form has no request and no complaint', () => {
    for (const f of [
      form({ amount: '' }),
      form({ amount: '12.345' }),
      form({ paidOn: '' }),
      form(),
    ]) {
      expect(requestOf(['e1'], mobile, f)).toEqual({ request: null, problem: null })
    }
    expect(requestOf(['e1'], { kind: 'method', method: bank }, form())).toEqual({
      request: null,
      problem: null,
    })
    expect(requestOf([], { kind: 'cash' }, form()).request).toBeNull()
  })

  it('a too-short transaction ID is named, not just refused', () => {
    expect(requestOf(['e1'], mobile, form({ transactionId: 'BJK40' }))).toEqual({
      request: null,
      problem: 'transaction_id_short',
    })
  })
})

describe('attemptFor — a retry cannot submit twice', () => {
  const request = requestOf(['e1'], mobile, form({ transactionId: 'BJK400Q1IL' })).request!
  let n = 0
  const fresh = () => `id-${++n}`

  it('keeps the mutation id while the payment is unchanged', () => {
    const first = attemptFor(null, request, fresh)
    expect(attemptFor(first, { ...request }, fresh)).toBe(first)
  })

  it('takes a new id once any detail changes', () => {
    const first = attemptFor(null, request, fresh)
    const second = attemptFor(first, { ...request, amount: '1000.00' }, fresh)
    expect(second.clientMutationId).not.toBe(first.clientMutationId)
  })
})

describe('small things', () => {
  it('suggests the owed figure only when something is owed', () => {
    expect(suggestedAmount(Money.fromWire('1500.00'))).toBe('1500')
    expect(suggestedAmount(Money.fromWire('1500.50'))).toBe('1500.50')
    expect(suggestedAmount(Money.fromWire('0.00'))).toBe('')
  })
  it('words outcomes, names and the first name', () => {
    expect(outcomeOf('approved')).toBe('approved')
    expect(outcomeOf('rejected')).toBe('rejected')
    expect(outcomeOf('pending')).toBe('pending')
    expect(joinNames(['A'], 'and')).toBe('A')
    expect(joinNames(['A', 'B', 'C'], 'ও')).toBe('A, B ও C')
    expect(firstName('তাসনিম জাহান')).toBe('তাসনিম')
  })
  it('dates "today" in Dhaka, not UTC', () => {
    // 20:30 UTC on the 4th is 02:30 on the 5th in Dhaka.
    expect(dhakaToday(new Date('2026-11-04T20:30:00Z'))).toBe('2026-11-05')
  })
})

describe('payments (G2)', () => {
  const dto = {
    display_name: 'তাসনিম জাহান',
    year: 2026,
    paid_this_year: '26400.00',
    months: [
      {
        period: '2026-10',
        lines: [
          {
            enrollment_id: 'e1',
            batch_name: 'Chemistry',
            amount: '1200.00',
            state: 'verifying',
            due_date: '2026-10-10',
            sent_on: '2026-10-15',
            decided_on: null,
            channel: 'Nagad',
          },
        ],
      },
    ],
  } as Schemas['PaymentsResponse']

  it('maps lines with money as Money', () => {
    const model = mapPayments(dto)
    expect(model.paidThisYear.format()).toBe('৳26,400')
    expect(model.months[0]?.lines[0]).toMatchObject({
      state: 'verifying',
      sentOn: '2026-10-15',
      channel: 'Nagad',
    })
  })

  it('refuses a line state it does not know, and a number where money belongs', () => {
    const odd = structuredClone(dto)
    odd.months![0]!.lines[0]!.state = 'refunded' as 'paid'
    expect(() => mapPayments(odd)).toThrow(MoneyFormatError)
    const number = { ...dto, paid_this_year: 26400 as unknown as string }
    expect(() => mapPayments(number)).toThrow(MoneyFormatError)
  })

  it('leads with the first payable the server ordered', () => {
    expect(nextPayable({ payable: [], waiting: [] })).toBeNull()
    const next = nextPayable({
      payable: [
        {
          enrollment_id: 'e1',
          batch_name: 'Math',
          period: '2026-10',
          amount_due: '1500.00',
          total_due: '6000.00',
          later_periods: 3,
          days_late: 92,
          due_date: '2026-10-05',
        },
      ],
    })
    expect(next?.totalDue.format()).toBe('৳6,000')
    expect(next?.laterPeriods).toBe(3)
  })
})
