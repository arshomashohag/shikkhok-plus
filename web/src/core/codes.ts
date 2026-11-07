/**
 * Small helpers for authenticator and recovery codes, kept apart from
 * `ui/authenticator.tsx` so the sign-in screen can use them without
 * pulling the QR encoder into the app's entry chunk.
 */
import { toLatinDigits } from './money'

/** `JBSWY3DPEHPK3PXP` → `JBSW Y3DP EHPK 3PXP`, for typing by hand. */
export function groupSecret(secret: string): string {
  return (secret.replace(/\s+/g, '').match(/.{1,4}/g) ?? []).join(' ')
}

/** Six Western digits at most, from whatever was typed or pasted. */
export function sixDigits(value: string): string {
  return toLatinDigits(value).replace(/\D/g, '').slice(0, 6)
}

/** Copy to the clipboard; false when the browser refuses or has none. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) return false
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
