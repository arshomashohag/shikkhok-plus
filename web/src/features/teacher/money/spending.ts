/**
 * Expenses and the monthly summary: the calls, the mappers and the record
 * form's rules. Every total and the surplus-or-deficit verdict are the
 * server's; nothing here adds or compares money.
 */
import { request } from '../../../api/client'
import type { Schemas } from '../../../api/endpoints'
import { Money } from '../../../core/money'

export type ExpenseCategory = Schemas['ExpenseRequest']['category']

/** The categories in the order the form offers them. */
export const EXPENSE_CATEGORIES: readonly ExpenseCategory[] = [
  'exam_paper',
  'printing',
  'rent',
  'utilities',
  'materials',
  'transport',
  'salary',
  'other',
]

export const EXPENSE_WHAT_MAX = 120

export const listExpenses = (month: string) =>
  request<Schemas['ExpenseMonthResponse']>('GET', '/v1/expenses', { query: { month } })

export const recordExpense = (body: Schemas['ExpenseRequest']) =>
  request<Schemas['ExpenseResponse']>('POST', '/v1/expenses', { body })

export const voidExpense = (expenseId: string, reason: string | null) =>
  request<Schemas['ExpenseResponse']>(
    'POST',
    `/v1/expenses/${encodeURIComponent(expenseId)}/void`,
    { body: { reason } },
  )

export const readMoneySummary = (month: string) =>
  request<Schemas['MoneySummaryResponse']>('GET', '/v1/money/summary', { query: { month } })

export interface ExpenseRow {
  id: string
  category: ExpenseCategory
  what: string
  amount: Money
  spentOn: string
  payee: string | null
  voided: boolean
  voidReason: string | null
}

export interface ExpenseMonth {
  month: string
  total: Money
  byCategory: { category: ExpenseCategory; total: Money }[]
  rows: ExpenseRow[]
}

export function mapExpenseMonth(dto: Schemas['ExpenseMonthResponse']): ExpenseMonth {
  return {
    month: dto.month,
    total: Money.fromWire(dto.total),
    byCategory: dto.by_category.map((c) => ({
      category: c.category,
      total: Money.fromWire(c.total),
    })),
    rows: dto.expenses.map((e) => ({
      id: e.expense_id,
      category: e.category,
      what: e.what,
      amount: Money.fromWire(e.amount),
      spentOn: e.spent_on,
      payee: e.payee ?? null,
      voided: e.voided,
      voidReason: e.void_reason ?? null,
    })),
  }
}

export interface MoneySummary {
  collected: { monthly: Money; exam: Money; other: Money; total: Money }
  spentTotal: Money
  spentByCategory: { category: ExpenseCategory; total: Money }[]
  net: Money
  netKind: 'surplus' | 'deficit' | 'even'
  owedMonthly: Money
  owedExtra: Money
  fees: { id: string; label: string; collected: Money; spent: Money }[]
}

export function mapSummary(dto: Schemas['MoneySummaryResponse']): MoneySummary {
  return {
    collected: {
      monthly: Money.fromWire(dto.collected.monthly),
      exam: Money.fromWire(dto.collected.exam),
      other: Money.fromWire(dto.collected.other),
      total: Money.fromWire(dto.collected.total),
    },
    spentTotal: Money.fromWire(dto.spent_total),
    spentByCategory: dto.spent_by_category.map((c) => ({
      category: c.category,
      total: Money.fromWire(c.total),
    })),
    net: Money.fromWire(dto.net),
    netKind: dto.net_kind,
    owedMonthly: Money.fromWire(dto.owed_monthly),
    owedExtra: Money.fromWire(dto.owed_extra),
    fees: dto.extra_fees.map((f) => ({
      id: f.extra_fee_id,
      label: f.label,
      collected: Money.fromWire(f.collected),
      spent: Money.fromWire(f.spent),
    })),
  }
}

export interface ExpenseInput {
  category: ExpenseCategory
  what: string
  typed: string
  spentOn: string
  payee: string
  note: string
  /** An extra fee id, or '' for none. */
  extraFeeId: string
  clientMutationId: string
}

export function openExpense(clientMutationId: string, spentOn: string): ExpenseInput {
  return {
    category: 'printing',
    what: '',
    typed: '',
    spentOn,
    payee: '',
    note: '',
    extraFeeId: '',
    clientMutationId,
  }
}

/** The request for the form, or null while it cannot be sent. */
export function expenseBody(input: ExpenseInput): Schemas['ExpenseRequest'] | null {
  const amount = Money.fromTyped(input.typed)
  const what = input.what.trim()
  if (!amount || amount.isZero() || what === '' || input.spentOn === '') return null
  return {
    category: input.category,
    what: what.slice(0, EXPENSE_WHAT_MAX),
    amount: amount.wire,
    spent_on: input.spentOn,
    payee: input.payee.trim() || null,
    note: input.note.trim() || null,
    extra_fee_id: input.extraFeeId || null,
    client_mutation_id: input.clientMutationId,
  }
}

/** This month as `YYYY-MM`, and the months either side of one. */
export function currentMonth(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y ?? 2000, (m ?? 1) - 1 + by, 1)
  return currentMonth(d)
}
