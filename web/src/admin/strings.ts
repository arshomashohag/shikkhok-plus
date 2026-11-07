/**
 * The admin app's own strings, in English and Bangla, added to the shared
 * bundles when this module is first imported. They live here rather than
 * in `src/i18n/web/` so that the main app, which globs that folder, never
 * ships them (`scripts/check-bundles.mjs` holds it to that).
 */
import { addStrings } from '../i18n/i18n'
import bn from './i18n/admin.bn.json'
import en from './i18n/admin.en.json'

export const ADMIN_EN: Record<string, string> = en
export const ADMIN_BN: Record<string, string> = bn

addStrings({ en: ADMIN_EN, bn: ADMIN_BN })
