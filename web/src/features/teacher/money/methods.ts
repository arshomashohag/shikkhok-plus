/**
 * Where students pay: the teacher's payment methods, as rows and as an
 * editable draft (`PaymentMethodsViewModel.kt`, `MethodEditorViewModel.kt`).
 *
 * Validation is format only — a mobile method needs a service and a
 * number, a bank method its four fields. Whether the method is acceptable
 * is the server's call, shown through its message key.
 */
import type { Schemas } from '../../../api/endpoints'

export type MethodKind = 'mobile' | 'bank'

export interface MethodRow {
  methodId: string
  kind: MethodKind
  title: string
  detail: string
  extra: string | null
  note: string | null
}

/** The services offered first; any other name may be typed. */
export const DEFAULT_SERVICES: readonly string[] = ['bKash', 'Nagad', 'Rocket']

export function rowOf(m: Schemas['PaymentMethodResponse']): MethodRow {
  const note = m.note?.trim() ? m.note : null
  if (m.kind === 'mobile') {
    return {
      methodId: m.method_id,
      kind: 'mobile',
      title: m.provider ?? '',
      detail: m.mobile_number ?? '',
      extra: null,
      note,
    }
  }
  // The full account number is the teacher's own and on their own screen,
  // but a list row shows only its end, as Android's does.
  const last = (m.account_number ?? '').slice(-4)
  return {
    methodId: m.method_id,
    kind: 'bank',
    title: m.provider ?? '',
    detail: `${m.account_name ?? ''} · ••• ${last}`,
    extra: m.branch_name?.trim() ? m.branch_name : null,
    note,
  }
}

export interface MethodDraft {
  kind: MethodKind
  provider: string
  mobileNumber: string
  accountNumber: string
  accountName: string
  branchName: string
  note: string
}

export function emptyDraft(kind: MethodKind): MethodDraft {
  return {
    kind,
    provider: '',
    mobileNumber: '',
    accountNumber: '',
    accountName: '',
    branchName: '',
    note: '',
  }
}

export function draftOf(m: Schemas['PaymentMethodResponse']): MethodDraft {
  return {
    kind: m.kind,
    provider: m.provider ?? '',
    mobileNumber: m.mobile_number ?? '',
    accountNumber: m.account_number ?? '',
    accountName: m.account_name ?? '',
    branchName: m.branch_name ?? '',
    note: m.note ?? '',
  }
}

/** Switching kind clears the service, which belongs to one kind. */
export function withKind(draft: MethodDraft, kind: MethodKind): MethodDraft {
  return kind === draft.kind ? draft : { ...draft, kind, provider: '' }
}

export function canSave(d: MethodDraft): boolean {
  const filled = (s: string) => s.trim() !== ''
  return d.kind === 'mobile'
    ? filled(d.provider) && filled(d.mobileNumber)
    : filled(d.provider) && filled(d.accountNumber) && filled(d.accountName) && filled(d.branchName)
}

/** The request body: only the fields the kind takes, trimmed. */
export function requestOf(d: MethodDraft): Schemas['PaymentMethodRequest'] {
  const note = d.note.trim() || null
  return d.kind === 'mobile'
    ? { kind: 'mobile', provider: d.provider.trim(), mobile_number: d.mobileNumber.trim(), note }
    : {
        kind: 'bank',
        provider: d.provider.trim(),
        account_number: d.accountNumber.trim(),
        account_name: d.accountName.trim(),
        branch_name: d.branchName.trim(),
        note,
      }
}

/**
 * The service suggestions under the field (`providerOptions`): the known
 * services matching what is typed, then "Use “…”" when it is new.
 */
export function providerOptions(
  typed: string,
): ({ kind: 'service'; name: string } | { kind: 'typed'; text: string })[] {
  const text = typed.trim()
  const lower = text.toLowerCase()
  const matches = DEFAULT_SERVICES.filter((s) => s.toLowerCase().includes(lower)).map((name) => ({
    kind: 'service' as const,
    name,
  }))
  const exact = DEFAULT_SERVICES.some((s) => s.toLowerCase() === lower)
  return text === '' || exact ? matches : [...matches, { kind: 'typed' as const, text }]
}
