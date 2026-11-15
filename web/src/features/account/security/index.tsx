/**
 * Account security (every lens): two-step verification, the password,
 * the username, and the account's phone and email (view, add, replace,
 * remove). The settings screens load on first use; the entry rows, the
 * home prompts and the small status store they share are in the shell's
 * chunk.
 */
import { lazyScreen } from '../../../core/lazy'
import type { AccountRoute } from '../../family/area'
import { securityPaths } from './paths'

export { MfaEntry } from './MfaEntry'
export { MfaPrompt } from './MfaPrompt'
export { PasswordPrompt } from './PasswordPrompt'
export { AccountEntries } from './AccountEntries'
export { securityPaths } from './paths'

export const securityRoutes: AccountRoute[] = [
  { path: securityPaths.twoStep(), element: lazyScreen(() => import('./TwoStep'), 'TwoStep') },
  {
    path: securityPaths.password(),
    element: lazyScreen(() => import('./Password'), 'Password'),
  },
  {
    path: securityPaths.addContact('phone'),
    element: lazyScreen(() => import('./AddContact'), 'AddPhone'),
  },
  {
    path: securityPaths.addContact('email'),
    element: lazyScreen(() => import('./AddContact'), 'AddEmail'),
  },
  {
    path: securityPaths.username(),
    element: lazyScreen(() => import('../username/UsernameScreen'), 'UsernameScreen'),
  },
  {
    path: securityPaths.contacts(),
    element: lazyScreen(() => import('../contacts/ContactsScreen'), 'ContactsScreen'),
  },
  {
    path: securityPaths.replaceContact('phone'),
    element: lazyScreen(() => import('../contacts/ReplaceContact'), 'ReplacePhone'),
  },
  {
    path: securityPaths.replaceContact('email'),
    element: lazyScreen(() => import('../contacts/ReplaceContact'), 'ReplaceEmail'),
  },
]
