/**
 * Account area (every lens): inbox, edit profile, my children, delete
 * account. Each screen loads on first use; the unread count is small and
 * loaded with the shell, which shows it on the More tab.
 */
import { lazyScreen } from '../../../core/lazy'
import type { AccountRoute } from '../../family/area'

export { useUnreadCount, inboxChanged } from './unread'

/** Paths match `accountPaths` in features/family/reader.ts. */
export const accountRoutes: AccountRoute[] = [
  { path: '/inbox', element: lazyScreen(() => import('./Inbox'), 'Inbox') },
  { path: '/inbox/:notificationId', element: lazyScreen(() => import('./Inbox'), 'InboxItem') },
  { path: '/profile/edit', element: lazyScreen(() => import('./EditProfile'), 'EditProfile') },
  { path: '/profile/children', element: lazyScreen(() => import('./MyChildren'), 'MyChildren') },
  {
    path: '/profile/delete',
    element: lazyScreen(() => import('./DeleteAccount'), 'DeleteAccount'),
  },
]
