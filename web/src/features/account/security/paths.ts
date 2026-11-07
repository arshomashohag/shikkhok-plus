/** Where the two-step verification settings live. */
export const securityPaths = {
  twoStep: () => '/settings/security',
} as const

/** Route state that opens the screen straight into "Turn on". */
export interface TwoStepEntry {
  start?: boolean
}
