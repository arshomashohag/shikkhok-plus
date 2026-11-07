/** Every admin URL. Bookmarked by the administrators; linked from nowhere else. */
import type { HelpStatus } from '../help/mappers'

const id = encodeURIComponent

export const adminPaths = {
  overview: () => '/admin',
  teachers: () => '/admin/teachers',
  people: () => '/admin/help',
  tickets: (filter: { status?: HelpStatus | null; ref?: string | null } = {}) => {
    const q = new URLSearchParams()
    if (filter.status) q.set('status', filter.status)
    if (filter.ref) q.set('ref', filter.ref)
    const qs = q.toString()
    return `/admin/help/tickets${qs ? `?${qs}` : ''}`
  },
  ticket: (ticketId: string) => `/admin/help/tickets/${id(ticketId)}`,
} as const
