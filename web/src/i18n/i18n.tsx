/**
 * Strings, in Bangla and English. [TC-15] [D-43]
 *
 * The bundles are the Android app's, generated (`npm run gen:strings`),
 * plus a short web-only set for things a phone app never says (install,
 * update, language). **No user-facing string is written in a component**;
 * every one goes through {@link useT}.
 */
import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react'
import en from './generated/strings.en.json'
import bn from './generated/strings.bn.json'
import messageKeys from './generated/message-keys.json'

/**
 * Web-only strings, one file per area (`web/<area>.<lang>.json`), so
 * areas built in parallel never edit the same file. Keys start `web_`.
 */
const WEB = import.meta.glob<Record<string, string>>('./web/*.json', {
  eager: true,
  import: 'default',
})
function webStrings(lang: Lang): Record<string, string> {
  return Object.entries(WEB)
    .filter(([path]) => path.endsWith(`.${lang}.json`))
    .reduce<Record<string, string>>((all, [, strings]) => ({ ...all, ...strings }), {})
}
export const WEB_EN = webStrings('en')
export const WEB_BN = webStrings('bn')
import type { Lang } from '../core/format'

type Entry = string | { one?: string; other?: string; [q: string]: string | undefined }
type Bundle = Record<string, Entry>

export const BUNDLES: Record<Lang, Bundle> = {
  en: { ...(en as Bundle), ...WEB_EN },
  bn: { ...(bn as Bundle), ...WEB_BN },
}

/**
 * Add a separately built app's own strings — the admin app's
 * (`src/admin/strings.ts`) — before its first render. Kept out of the
 * `web/*.json` glob above so the main app's bundle never carries them.
 */
export function addStrings(extra: Record<Lang, Record<string, string>>): void {
  Object.assign(BUNDLES.en, extra.en)
  Object.assign(BUNDLES.bn, extra.bn)
}

/** Server `message_key` → string resource name. */
export const MESSAGE_KEYS: Record<string, string> = messageKeys

function fill(template: string, args: readonly (string | number)[]): string {
  return template.replace(/\{(\d)\}/g, (whole, n: string) => {
    const value = args[Number.parseInt(n, 10) - 1]
    return value === undefined ? whole : String(value)
  })
}

/** Look up and fill a string, falling back to English, then to the key. */
export function translate(lang: Lang, key: string, ...args: (string | number)[]): string {
  const entry = BUNDLES[lang][key] ?? BUNDLES.en[key]
  if (entry === undefined) return key
  if (typeof entry === 'string') return fill(entry, args)
  return fill(entry.other ?? Object.values(entry)[0] ?? key, args)
}

/** Choose a plural form. Bangla and English both need only one/other. */
export function translatePlural(
  lang: Lang,
  key: string,
  count: number,
  ...args: (string | number)[]
): string {
  const entry = BUNDLES[lang][key] ?? BUNDLES.en[key]
  if (entry === undefined) return key
  if (typeof entry === 'string') return fill(entry, [count, ...args])
  const form = new Intl.PluralRules(lang).select(count)
  return fill(entry[form] ?? entry.other ?? key, [count, ...args])
}

/** The text for a server error's `message_key`. */
/**
 * Server messages whose string has placeholders, and the `details` that
 * fill them, in placeholder order. The server names the string and sends
 * the values; this is the one place that joins the two, so no screen has
 * to remember that "{1} tries left" needs `attempts_left`.
 *
 * `fallback` is shown when a value is missing (an older server, or a
 * path that sends no details), so a person never reads a raw `{1}`.
 */
const MESSAGE_ARGS: Record<string, { details: readonly string[]; fallback: string }> = {
  'auth.otp.wrong': { details: ['attempts_left'], fallback: 'web_auth_otp_wrong_no_count' },
}

export function translateMessage(
  lang: Lang,
  messageKey: string,
  details?: Readonly<Record<string, string>> | null,
): string {
  const resource = MESSAGE_KEYS[messageKey]
  if (!resource) return translate(lang, 'error_unexpected')
  const wanted = MESSAGE_ARGS[messageKey]
  if (!wanted) return translate(lang, resource)
  const args = wanted.details.map((name) => details?.[name])
  if (args.some((value) => value === undefined || value === '')) {
    return translate(lang, wanted.fallback)
  }
  return translate(lang, resource, ...(args as string[]))
}

export interface Translator {
  lang: Lang
  t: (key: string, ...args: (string | number)[]) => string
  plural: (key: string, count: number, ...args: (string | number)[]) => string
  message: (messageKey: string, details?: Readonly<Record<string, string>> | null) => string
}

const I18nContext = createContext<Translator | null>(null)

export function I18nProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  const t = useCallback(
    (key: string, ...args: (string | number)[]) => translate(lang, key, ...args),
    [lang],
  )
  const plural = useCallback(
    (key: string, count: number, ...args: (string | number)[]) =>
      translatePlural(lang, key, count, ...args),
    [lang],
  )
  const message = useCallback(
    (k: string, details?: Readonly<Record<string, string>> | null) =>
      translateMessage(lang, k, details),
    [lang],
  )
  const value = useMemo(() => ({ lang, t, plural, message }), [lang, t, plural, message])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useT(): Translator {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useT outside I18nProvider')
  return value
}
