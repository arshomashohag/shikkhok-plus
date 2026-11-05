/** Account area (every lens): inbox, edit profile, my children, delete account. */
import type { AccountRoute } from '../../family/area'
import { DeleteAccount } from './DeleteAccount'
import { EditProfile } from './EditProfile'
import { Inbox, InboxItem } from './Inbox'
import { MyChildren } from './MyChildren'

export { useUnreadCount, inboxChanged } from './unread'

/** Paths match `accountPaths` in features/family/reader.ts. */
export const accountRoutes: AccountRoute[] = [
  { path: '/inbox', element: <Inbox /> },
  { path: '/inbox/:notificationId', element: <InboxItem /> },
  { path: '/profile/edit', element: <EditProfile /> },
  { path: '/profile/children', element: <MyChildren /> },
  { path: '/profile/delete', element: <DeleteAccount /> },
]
