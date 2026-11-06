/**
 * Payroll's client-side shaping: the line's one-line summary and the two
 * request bodies. Every figure shown is the server's; nothing here adds,
 * multiplies or compares money.
 */
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'

export type SalaryLine = Schemas['SalaryLineResponse']
type Translate = (key: string, ...args: (string | number)[]) => string

/** How the base was reached, as the server reported it. */
export function basisLine(line: SalaryLine, t: Translate): string {
  const rate = Money.fromWire(line.rate).format()
  return line.basis === 'monthly'
    ? t('payroll_basis_monthly', rate)
    : t('payroll_basis_per_class', line.classes_held, rate)
}

/** The adjustment body, or null while it cannot be sent. */
export function adjustmentBody(
  kind: 'addition' | 'deduction',
  label: string,
  typed: string,
): Schemas['AdjustmentRequest'] | null {
  const amount = Money.fromTyped(typed)
  if (!amount || amount.isZero() || !label.trim()) return null
  return { kind, label: label.trim().slice(0, 80), amount: amount.wire }
}

/** The payment body, or null while it cannot be sent. */
export function paymentBody(
  typed: string,
  paidOn: string,
  note: string,
  key: string,
): Schemas['SalaryPaymentRequest'] | null {
  const amount = Money.fromTyped(typed)
  if (!amount || amount.isZero()) return null
  return {
    amount: amount.wire,
    paid_on: paidOn || null,
    note: note.trim() || null,
    client_mutation_id: key,
  }
}
