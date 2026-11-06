/** Exam and other fees: the mappers, the raise form's body, and "payment for". */
import { describe, expect, it } from 'vitest'
import { MoneyFormatError, Money } from '../../../core/money'
import { requestOf } from '../../family/pay/mappers'
import { chargedCount, mapFeeDetail, openRaise, raiseBody } from './extraFees'
import { openRecord, recordBody } from './record'
import { purposeFields, samePurpose, type FeeRef } from './review'

const summary = {
  extra_fee_id: 'fee-1',
  purpose: 'exam' as const,
  label: 'Half-yearly exam fee',
  exam_title: null,
  amount: '500.00',
  due_on: '2026-11-15',
  created_at: '2026-11-06T04:00:00Z',
  student_count: 3,
  paid_count: 1,
  waived_count: 1,
  owing_count: 1,
  charged_total: '800.00',
  collected_total: '500.00',
  owed_total: '300.00',
}

describe('mapFeeDetail', () => {
  it('keeps every figure the server computed, as Money', () => {
    const detail = mapFeeDetail({
      ...summary,
      students: [
        {
          enrollment_id: 'e1',
          display_name: 'Tania',
          charged: '500.00',
          paid: '200.00',
          owed: '300.00',
          status: 'partly_paid',
        },
      ],
    })
    expect(detail.owedTotal.wire).toBe('300.00')
    expect(detail.students[0]?.status).toBe('partly_paid')
    expect(detail.students[0]?.owed.wire).toBe('300.00')
  })

  it('fails loudly on a money value sent as a JSON number', () => {
    expect(() => mapFeeDetail({ ...summary, owed_total: 300 as never, students: [] })).toThrow(
      MoneyFormatError,
    )
  })
})

describe('raiseBody', () => {
  const students = ['e1', 'e2', 'e3']
  const filled = {
    ...openRaise('key-1', '2026-11-15'),
    label: '  Half-yearly exam fee  ',
    typed: '500',
  }

  it('sends the trimmed name, the amount as a string and the retry key', () => {
    expect(raiseBody(filled, students)).toEqual({
      purpose: 'exam',
      label: 'Half-yearly exam fee',
      exam_id: null,
      amount: '500.00',
      due_on: '2026-11-15',
      seat_amounts: [],
      excluded_enrollment_ids: [],
      client_mutation_id: 'key-1',
    })
  })

  it('sends a waiver as zero and a left-out student as excluded', () => {
    const body = raiseBody({ ...filled, seats: { e2: 'waive', e3: 'leave_out' } }, students)
    expect(body?.seat_amounts).toEqual([{ enrollment_id: 'e2', amount: '0.00' }])
    expect(body?.excluded_enrollment_ids).toEqual(['e3'])
    expect(chargedCount({ ...filled, seats: { e3: 'leave_out' } }, students)).toBe(2)
  })

  it('sends nothing without a name, an amount, or a student left to charge', () => {
    expect(raiseBody({ ...filled, label: '   ' }, students)).toBeNull()
    expect(raiseBody({ ...filled, typed: '' }, students)).toBeNull()
    const everyoneOut = { e1: 'leave_out', e2: 'leave_out', e3: 'leave_out' } as const
    expect(raiseBody({ ...filled, seats: everyoneOut }, students)).toBeNull()
  })

  it('links an exam only to an exam fee', () => {
    expect(raiseBody({ ...filled, examId: 'x1' }, students)?.exam_id).toBe('x1')
    expect(raiseBody({ ...filled, kind: 'other', examId: 'x1' }, students)?.exam_id).toBeNull()
  })
})

describe('payment for', () => {
  const fee: FeeRef = { id: 'fee-1', label: 'Exam', kind: 'exam', dueOn: '2026-11-15' }

  it('sends no purpose until the teacher chooses one', () => {
    expect(purposeFields(null)).toEqual({})
    expect(purposeFields('monthly')).toEqual({ purpose: 'monthly', extra_fee_id: null })
    expect(purposeFields('fee-1')).toEqual({ purpose: 'extra', extra_fee_id: 'fee-1' })
  })

  it('compares choices by what they name', () => {
    expect(samePurpose(null, null)).toBe(true)
    expect(samePurpose(fee, { ...fee })).toBe(true)
    expect(samePurpose(fee, null)).toBe(false)
  })

  it('records cash against a fee only when the sheet is opened for one', () => {
    const owed = Money.fromWire('500.00')
    const input = openRecord(owed, 'k')
    expect(recordBody(owed, input)?.purpose).toBeUndefined()
    expect(recordBody(owed, input, 'fee-1')).toMatchObject({
      purpose: 'extra',
      extra_fee_id: 'fee-1',
    })
  })

  it('pays the months with no purpose field, as an older app did', () => {
    const form = {
      amount: '500',
      paidOn: '2026-11-06',
      transactionId: '',
      fromAccount: '',
      note: '',
    }
    const monthly = requestOf(['e1'], { kind: 'cash' }, form).request
    const extra = requestOf(['e1'], { kind: 'cash' }, form, 'fee-1').request
    expect(monthly).not.toHaveProperty('purpose')
    expect(extra).toMatchObject({ purpose: 'extra', extra_fee_id: 'fee-1' })
  })
})
