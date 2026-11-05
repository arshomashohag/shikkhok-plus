/**
 * Money area: payment detail and changing a decision, a seat's fee history
 * and progress, where students pay, and collections.
 */
import { lazyScreen } from '../../../core/lazy'
import type { TeacherRoute } from '../area'
import './money.css'

/** Paths as in `teacher/paths.ts`; `/seats/:id/progress` is local (money/paths.ts). */
export const moneyRoutes: TeacherRoute[] = [
  {
    path: '/verify/:submissionId',
    element: lazyScreen(() => import('./PaymentReview'), 'PaymentReviewScreen'),
  },
  {
    path: '/seats/:enrollmentId/fees',
    element: lazyScreen(() => import('./SeatFees'), 'SeatFees'),
  },
  {
    path: '/seats/:enrollmentId/progress',
    element: lazyScreen(() => import('./SeatProgress'), 'SeatProgress'),
  },
  {
    path: '/payment-methods',
    element: lazyScreen(() => import('./PaymentMethods'), 'PaymentMethods'),
  },
  {
    path: '/payment-methods/new',
    element: lazyScreen(() => import('./PaymentMethods'), 'NewPaymentMethod'),
  },
  {
    path: '/payment-methods/:methodId',
    element: lazyScreen(() => import('./PaymentMethods'), 'EditPaymentMethod'),
  },
  { path: '/collections', element: lazyScreen(() => import('./Collections'), 'Collections') },
  {
    path: '/batches/:batchId/month/:period',
    element: lazyScreen(() => import('./BatchMonth'), 'BatchMonthScreen'),
  },
]
