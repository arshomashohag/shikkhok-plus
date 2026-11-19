/** Public hub area: the owner's listing and their batches' listings [0036]. */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'

/**
 * Paths match `paths.hub`, `paths.hubBatches`, `paths.hubPreview`,
 * `paths.hubFeedback` and `paths.hubReviews`. The Reviews screen's entry on
 * the listing editor is drawn only once `GET /v1/hub/reviews` succeeds, so
 * with reviews switched off there is no tab and no error [H4].
 */
export const hubRoutes: TeacherRoute[] = [
  { path: '/more/hub', element: lazyScreen(() => import('./Listing'), 'HubListing') },
  {
    path: '/more/hub/batches',
    element: lazyScreen(() => import('./BatchListings'), 'BatchListings'),
  },
  { path: '/more/hub/preview', element: lazyScreen(() => import('./Preview'), 'HubPreview') },
  {
    path: '/more/hub/feedback/:ownerId/:day',
    element: lazyScreen(() => import('./Feedback'), 'HubFeedback'),
  },
  { path: '/more/hub/reviews', element: lazyScreen(() => import('./Reviews'), 'OwnerReviews') },
]
