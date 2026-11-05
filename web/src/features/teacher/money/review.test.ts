/**
 * The approval sheet's rules and the request bodies they produce — the
 * money-moving part of the area, so every body is asserted exactly.
 */
import { describe, expect, it } from 'vitest'
import type { Schemas } from '../../../api/endpoints'
import { MoneyFormatError } from '../../../core/money'
import {
  asReportedBody,
  canDecide,
  mapPaymentDetail,
  openSheet,
  rejectionBody,
  sheetBody,
  sheetState,
  typeAmount,
  type SheetInput,
} from './review'

function wire(patch: Partial<Schemas['PaymentReviewResponse']> = {}) {
  return {
    submission_id: 's1',
    batch_name: 'Math · Batch B',
    children: [
      {
        claim_id: 'c1',
        enrollment_id: 'e1',
        display_name: 'Tasnim',
        owed: '1200.00',
        period: '2026-10',
        approved_amount: null,
      },
    ],
    comparison: 'matches',
    difference: '0.00',
    owed_together: '1200.00',
    total_amount: '1200.00',
    method: { kind: 'mobile', provider: 'bKash', mobile_number: '01711000001' },
    paid_on: '2026-11-04',
    status: 'pending',
    submitted_at: '2026-11-05T03:00:00Z',
    submitted_by: 'guardian',
    submitter_phone: '+8801911000003',
    transaction_id: 'BJK400Q1IL',
    ...patch,
  } as Schemas['PaymentReviewResponse']
}

const twoChildren = wire({
  children: [
    {
      claim_id: 'c1',
      enrollment_id: 'e1',
      display_name: 'Tasnim',
      owed: '1200.00',
      period: '2026-10',
      approved_amount: null,
    },
    {
      claim_id: 'c2',
      enrollment_id: 'e2',
      display_name: 'Ayan',
      owed: '800.00',
      period: '2026-10',
      approved_amount: null,
    },
  ],
  owed_together: '2000.00',
  total_amount: '1500.00',
  difference: '500.00',
  comparison: 'short',
})

const input = (typed: string, patch: Partial<SheetInput> = {}): SheetInput => ({
  typed,
  disposition: null,
  childId: null,
  note: '',
  ...patch,
})

describe('mapPaymentDetail', () => {
  it('keeps the server’s decision, sender and destination', () => {
    const d = mapPaymentDetail(
      wire({
        status: 'approved',
        decided_at: '2026-11-05T04:00:00Z',
        decision_note: 'Thanks',
        children: [
          {
            claim_id: 'c1',
            enrollment_id: 'e1',
            display_name: 'Tasnim',
            owed: '1200.00',
            period: '2026-10',
            approved_amount: '1200.00',
          },
        ],
      }),
    )
    expect(d.status).toBe('approved')
    expect(d.decisionNote).toBe('Thanks')
    expect(d.submitterRole).toBe('guardian')
    expect(d.method).toEqual({ kind: 'mobile', provider: 'bKash', number: '01711000001' })
    expect(d.approved.e1?.format()).toBe('৳1,200')
  })

  it('names a bank account, not a phone, for a bank payment', () => {
    const d = mapPaymentDetail(
      wire({ method: { kind: 'bank', provider: 'DBBL', account_number: '1234567890' } }),
    )
    expect(d.method.number).toBe('1234567890')
  })

  it('refuses a number where an approved amount belongs', () => {
    const broken = wire()
    broken.children[0]!.approved_amount = 1200 as unknown as string
    expect(() => mapPaymentDetail(broken)).toThrow(MoneyFormatError)
  })
})

describe('canDecide', () => {
  it('offers controls on a pending payment, or a decided one being changed', () => {
    expect(canDecide({ status: 'pending' }, false)).toBe(true)
    expect(canDecide({ status: 'approved' }, false)).toBe(false)
    expect(canDecide({ status: 'rejected' }, true)).toBe(true)
  })
})

describe('the sheet', () => {
  const one = mapPaymentDetail(wire())
  const two = mapPaymentDetail(twoChildren)

  it('opens on the reported amount', () => {
    expect(openSheet(two).typed).toBe('1500')
    expect(openSheet(mapPaymentDetail(wire({ total_amount: '1200.50' }))).typed).toBe('1200.50')
  })

  it('places the typed amount against what is owed together', () => {
    expect(sheetState(one, input('1200')).side).toBe('exact')
    expect(sheetState(one, input('800')).side).toBe('short')
    expect(sheetState(one, input('1500')).side).toBe('over')
    expect(sheetState(one, input('12a')).side).toBe('invalid')
  })

  it('shows the server’s difference only while the amount is the one reported', () => {
    expect(sheetState(two, input('1500')).shownDifference?.format()).toBe('৳500')
    expect(sheetState(two, input('1400')).shownDifference).toBeNull()
  })

  it('asks for a child only when several share the payment and something is left over or owed', () => {
    expect(sheetState(one, input('800')).needsChild).toBe(false)
    expect(sheetState(two, input('1500')).needsChild).toBe(true)
    expect(sheetState(two, input('2500')).needsChild).toBe(true)
    expect(sheetState(two, input('2000')).needsChild).toBe(false)
  })

  it('drops choices that no longer apply when the amount crosses sides', () => {
    const chosen = input('1500', { disposition: 'carried', childId: 'e2' })
    expect(typeAmount(two, chosen, '1400')).toMatchObject({ disposition: 'carried', childId: 'e2' })
    expect(typeAmount(two, chosen, '2500')).toMatchObject({ disposition: null, childId: null })
  })

  it('cannot be confirmed until every question is answered', () => {
    expect(sheetBody(two, input('1500'), false)).toBeNull()
    expect(sheetBody(two, input('1500', { disposition: 'carried' }), false)).toBeNull()
    expect(sheetBody(one, input('abc'), false)).toBeNull()
  })

  it('single child, short, carried', () => {
    expect(
      sheetBody(one, input('800', { disposition: 'carried', note: '  rest next month ' }), false),
    ).toEqual({
      received_amount: '800.00',
      shortfall_disposition: 'carried',
      carried_by_enrollment_id: null,
      credit_to_enrollment_id: null,
      note: 'rest next month',
      correcting: false,
    })
  })

  it('two children, short, carried by the one named', () => {
    expect(sheetBody(two, input('1500', { disposition: 'carried', childId: 'e2' }), false)).toEqual(
      {
        received_amount: '1500.00',
        shortfall_disposition: 'carried',
        carried_by_enrollment_id: 'e2',
        credit_to_enrollment_id: null,
        note: null,
        correcting: false,
      },
    )
  })

  it('two children, short, waived for the one named', () => {
    expect(sheetBody(two, input('1500', { disposition: 'waived', childId: 'e1' }), true)).toEqual({
      received_amount: '1500.00',
      shortfall_disposition: 'waived',
      carried_by_enrollment_id: 'e1',
      credit_to_enrollment_id: null,
      note: null,
      correcting: true,
    })
  })

  it('two children, over: the extra is credited to the one named, no disposition', () => {
    expect(sheetBody(two, input('2,500', { childId: 'e1' }), false)).toEqual({
      received_amount: '2500.00',
      shortfall_disposition: null,
      carried_by_enrollment_id: null,
      credit_to_enrollment_id: 'e1',
      note: null,
      correcting: false,
    })
  })

  it('two children, exact: nobody is named', () => {
    expect(sheetBody(two, input('২০০০'), false)).toEqual({
      received_amount: '2000.00',
      shortfall_disposition: null,
      carried_by_enrollment_id: null,
      credit_to_enrollment_id: null,
      note: null,
      correcting: false,
    })
  })
})

describe('one-tap bodies', () => {
  it('approves as reported only what the server says matches', () => {
    const matches = mapPaymentDetail(wire())
    expect(asReportedBody(matches, ' ok ', true)).toEqual({
      received_amount: '1200.00',
      note: 'ok',
      correcting: true,
    })
    expect(asReportedBody(mapPaymentDetail(twoChildren), '', false)).toBeNull()
  })

  it('rejects with the note, or none', () => {
    expect(rejectionBody('   ', false)).toEqual({ note: null, correcting: false })
    expect(rejectionBody('Wrong TrxID', true)).toEqual({ note: 'Wrong TrxID', correcting: true })
  })
})
