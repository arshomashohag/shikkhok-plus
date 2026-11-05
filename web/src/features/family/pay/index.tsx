/**
 * Paying area: send money (S3), a child's payments (G2), and fee history,
 * for both readers. Mounted under `/my/:seat/` and `/child/:seat/`; paths
 * are `familyPaths.pay`, `.payments` and `.fees`. Every screen loads on
 * first use.
 */
import { lazyComponent } from '../../../core/lazy'
import type { FamilyRoute } from '../area'
import type { Reader } from '../reader'
import './pay.css'

type ReaderProps = { reader: Reader }

const PayScreen = lazyComponent<ReaderProps, typeof import('./PayScreen')>(
  () => import('./PayScreen'),
  'PayScreen',
)
const PaymentsScreen = lazyComponent<ReaderProps, typeof import('./PaymentsScreen')>(
  () => import('./PaymentsScreen'),
  'PaymentsScreen',
)
const FamilyFees = lazyComponent<ReaderProps, typeof import('./FamilyFees')>(
  () => import('./FamilyFees'),
  'FamilyFees',
)

export const payRoutes: FamilyRoute[] = [
  { path: 'pay', element: (reader) => <PayScreen reader={reader} /> },
  { path: 'payments', element: (reader) => <PaymentsScreen reader={reader} /> },
  { path: 'fees', element: (reader) => <FamilyFees reader={reader} /> },
]
