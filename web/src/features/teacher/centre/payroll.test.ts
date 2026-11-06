/** Payroll's request bodies and summary line. */
import { describe, expect, it } from 'vitest'
import { adjustmentBody, basisLine, paymentBody, type SalaryLine } from './payroll'

const line: SalaryLine = {
  line_id: 'l1',
  staff_id: 's1',
  staff_name: 'Sumi',
  centre_name: 'Udoy',
  period: '2026-11',
  basis: 'per_class',
  rate: '500.00',
  classes_held: 13,
  base: '6500.00',
  owed: '6500.00',
  paid: '0.00',
  remaining: '6500.00',
  status: 'draft',
  adjustments: [],
  payments: [],
}
const t = (key: string, ...args: (string | number)[]) => `${key}(${args.join(',')})`

describe('basisLine', () => {
  it('names the count and the rate for per-class, the rate for monthly', () => {
    expect(basisLine(line, t)).toBe('payroll_basis_per_class(13,৳500)')
    expect(basisLine({ ...line, basis: 'monthly', rate: '8000.00' }, t)).toBe(
      'payroll_basis_monthly(৳8,000)',
    )
  })
})

describe('adjustmentBody', () => {
  it('sends the trimmed label and the amount as a string', () => {
    expect(adjustmentBody('deduction', ' Advance ', '1000')).toEqual({
      kind: 'deduction',
      label: 'Advance',
      amount: '1000.00',
    })
  })

  it('sends nothing without a label or with a zero amount', () => {
    expect(adjustmentBody('addition', ' ', '100')).toBeNull()
    expect(adjustmentBody('addition', 'Bonus', '0')).toBeNull()
  })
})

describe('paymentBody', () => {
  it('carries the retry key, and blanks as null', () => {
    expect(paymentBody('3000', '', ' ', 'k1')).toEqual({
      amount: '3000.00',
      paid_on: null,
      note: null,
      client_mutation_id: 'k1',
    })
    expect(paymentBody('', '2026-11-06', '', 'k1')).toBeNull()
  })
})
