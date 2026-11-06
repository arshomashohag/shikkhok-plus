/** Centre area: a centre's managers and teachers [0022]. */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'

export const centreRoutes: TeacherRoute[] = [
  { path: '/centre-members', element: lazyScreen(() => import('./Members'), 'Members') },
  { path: '/centre-staff', element: lazyScreen(() => import('./Staff'), 'Staff') },
]
