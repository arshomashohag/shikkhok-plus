/**
 * Two-step verification (every lens). The settings screen, with the QR
 * code's encoder, loads on first use; the entry row, the home prompt and
 * the small status store they share are in the shell's chunk.
 */
import { lazyScreen } from '../../../core/lazy'
import type { AccountRoute } from '../../family/area'
import { securityPaths } from './paths'

export { MfaEntry } from './MfaEntry'
export { MfaPrompt } from './MfaPrompt'
export { securityPaths } from './paths'

export const securityRoutes: AccountRoute[] = [
  { path: securityPaths.twoStep(), element: lazyScreen(() => import('./TwoStep'), 'TwoStep') },
]
