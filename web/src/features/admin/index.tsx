/**
 * Platform admin area, under `/admin`. Linked from nowhere: an
 * administrator bookmarks `/ui/admin`. Mounted for every signed-in
 * account whatever its lens, because who is an administrator is the
 * server's allowlist and nothing the client knows; everyone else is
 * refused by the server and sees "This area is for ShikkhokPlus
 * administrators".
 */
import { lazyScreen } from '../../core/lazy'
import type { AccountRoute } from '../family/area'

const load = () => import('./AdminArea')

/** Paths match `adminPaths`. */
export const adminRoutes: AccountRoute[] = [
  { path: '/admin', element: lazyScreen(load, 'AdminOverview') },
  { path: '/admin/teachers', element: lazyScreen(load, 'AdminTeachers') },
  { path: '/admin/help', element: lazyScreen(load, 'AdminRequesters') },
  { path: '/admin/help/tickets', element: lazyScreen(load, 'AdminTickets') },
  { path: '/admin/help/tickets/:ticketId', element: lazyScreen(load, 'AdminTicketView') },
]
