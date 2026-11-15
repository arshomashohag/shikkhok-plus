/** Where the account's security settings live. */
export const securityPaths = {
  twoStep: () => '/settings/security',
  /** Set a first password, or change it. */
  password: () => '/settings/password',
  /** Add the phone number or email address the account lacks. */
  addContact: (kind: 'phone' | 'email') => `/settings/contact/${kind}`,
  /** The username, and changing it [FR7.1]. */
  username: () => '/settings/username',
  /** The account's phone and email: view, add, replace, remove [FR8.1]. */
  contacts: () => '/settings/contacts',
  /** Replace the account's phone or email with a new one [FR8.2]. */
  replaceContact: (kind: 'phone' | 'email') => `/settings/contact/${kind}/replace`,
} as const

/** Route state that opens the screen straight into "Turn on". */
export interface TwoStepEntry {
  start?: boolean
}

/** Route state Settings shows as a confirmation, after a change. */
export interface SettingsNotice {
  notice?: string
}
