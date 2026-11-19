/** Public hub area: the owner's listing and their batches' listings [0036]. */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'

/**
 * Paths match `paths.hub`, `paths.hubBatches`, `paths.hubPreview`,
 * `paths.hubFeedback`, `paths.hubReviews`, `paths.hubEnquiries` and
 * `paths.hubEnquiry`. The Reviews and Join requests entries on the listing
 * editor are drawn only once `GET /v1/hub/reviews` and `GET /v1/hub/enquiries`
 * succeed, so with either switched off there is no row and no error [H4] [H5].
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
  {
    path: '/more/hub/enquiries',
    element: lazyScreen(() => import('./Enquiries'), 'OwnerEnquiries'),
  },
  {
    path: '/more/hub/enquiries/:enquiryId',
    element: lazyScreen(() => import('./Enquiries'), 'EnquiryDetail'),
  },
]
