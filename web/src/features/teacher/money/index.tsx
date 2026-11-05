/**
 * Money area: payment detail and changing a decision, a seat's fee history
 * and progress, where students pay, and collections.
 */
import type { TeacherRoute } from '../area'
import { BatchMonthScreen } from './BatchMonth'
import { Collections } from './Collections'
import { PaymentReviewScreen } from './PaymentReview'
import { EditPaymentMethod, NewPaymentMethod, PaymentMethods } from './PaymentMethods'
import { SeatFees } from './SeatFees'
import { SeatProgress } from './SeatProgress'
import './money.css'

/** Paths as in `teacher/paths.ts`; `/seats/:id/progress` is local (money/paths.ts). */
export const moneyRoutes: TeacherRoute[] = [
  { path: '/verify/:submissionId', element: <PaymentReviewScreen /> },
  { path: '/seats/:enrollmentId/fees', element: <SeatFees /> },
  { path: '/seats/:enrollmentId/progress', element: <SeatProgress /> },
  { path: '/payment-methods', element: <PaymentMethods /> },
  { path: '/payment-methods/new', element: <NewPaymentMethod /> },
  { path: '/payment-methods/:methodId', element: <EditPaymentMethod /> },
  { path: '/collections', element: <Collections /> },
  { path: '/batches/:batchId/month/:period', element: <BatchMonthScreen /> },
]
