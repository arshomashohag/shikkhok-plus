/** Paying area: submit payment (S3), a seat's payments (G2), fee history. */
import type { FamilyRoute } from '../area'
import { FamilyFees } from './FamilyFees'
import { PayScreen } from './PayScreen'
import { PaymentsScreen } from './PaymentsScreen'

export const payRoutes: FamilyRoute[] = [
  { path: 'pay', element: (reader) => <PayScreen reader={reader} /> },
  { path: 'payments', element: (reader) => <PaymentsScreen reader={reader} /> },
  { path: 'fees', element: (reader) => <FamilyFees reader={reader} /> },
]
