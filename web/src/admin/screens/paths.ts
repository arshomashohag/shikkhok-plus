/** Every admin URL, at the root of the admin host. */
import type { HelpStatus } from '../../features/help/mappers'

const id = encodeURIComponent

export const adminPaths = {
  overview: () => '/',
  teachers: () => '/teachers',
  people: () => '/help',
  tickets: (filter: { status?: HelpStatus | null; ref?: string | null } = {}) => {
    const q = new URLSearchParams()
    if (filter.status) q.set('status', filter.status)
    if (filter.ref) q.set('ref', filter.ref)
    const qs = q.toString()
    return `/help/tickets${qs ? `?${qs}` : ''}`
  },
  ticket: (ticketId: string) => `/help/tickets/${id(ticketId)}`,
} as const
