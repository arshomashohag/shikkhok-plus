/** Public hub area: the owner's listing and their batches' listings [0036]. */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'

/** Paths match `paths.hub` and `paths.hubBatches`. */
export const hubRoutes: TeacherRoute[] = [
  { path: '/more/hub', element: lazyScreen(() => import('./Listing'), 'HubListing') },
  {
    path: '/more/hub/batches',
    element: lazyScreen(() => import('./BatchListings'), 'BatchListings'),
  },
]
