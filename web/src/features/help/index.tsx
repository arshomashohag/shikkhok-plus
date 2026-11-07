/**
 * Help centre (every signed-in account, whatever its lens): the
 * questions asked, a new question and one question's thread. Each
 * screen loads on first use; More shows the count of new replies.
 */
import { lazyScreen } from '../../core/lazy'
import type { AccountRoute } from '../family/area'

export { useNewReplies } from './newReplies'
export { helpPaths } from './paths'

/** Paths match `helpPaths`. */
export const helpRoutes: AccountRoute[] = [
  { path: '/help', element: lazyScreen(() => import('./HelpList'), 'HelpList') },
  { path: '/help/new', element: lazyScreen(() => import('./NewQuestion'), 'NewQuestion') },
  { path: '/help/:ticketId', element: lazyScreen(() => import('./HelpThread'), 'HelpThread') },
]
