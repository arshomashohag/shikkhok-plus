/**
 * The account's phone and email as the contacts screen and its Settings
 * row show them [FR8.1]. Pure: every display choice is made here and no
 * component makes one.
 *
 * Remove is offered for every present contact; nothing reads a count
 * [FR11.3] [NFR3.13]. Whether the last one may go is the server's answer
 * (`account.contact.last_one`).
 */
import type { Me } from '../../../api/endpoints'
import { formatPhone } from '../../../core/format'

export type ContactKind = 'phone' | 'email'

/** One card: the shown value, or null when the account has none of this kind. */
export interface ContactCard {
  kind: ContactKind
  contact: string | null
}

/** Phone first, then email; the phone formatted for display. */
export function contactCards(me: Me): [ContactCard, ContactCard] {
  return [
    { kind: 'phone', contact: me.phone ? formatPhone(me.phone) : null },
    { kind: 'email', contact: me.email ?? null },
  ]
}

/** The Settings row's subtitle: the present contacts, phone first, or null for none. */
export function contactsSummary(me: Me): string | null {
  const present = contactCards(me).flatMap((c) => (c.contact ? [c.contact] : []))
  return present.length > 0 ? present.join(' · ') : null
}

/** The other kind, for "Add another" after `last_one`. */
export function otherKind(kind: ContactKind): ContactKind {
  return kind === 'phone' ? 'email' : 'phone'
}
