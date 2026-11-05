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
import webEn from './web.en.json'
import webBn from './web.bn.json'
import type { Lang } from '../core/format'

type Entry = string | { one?: string; other?: string; [q: string]: string | undefined }
type Bundle = Record<string, Entry>

export const BUNDLES: Record<Lang, Bundle> = {
  en: { ...(en as Bundle), ...webEn },
  bn: { ...(bn as Bundle), ...webBn },
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
export function translateMessage(lang: Lang, messageKey: string): string {
  const resource = MESSAGE_KEYS[messageKey]
  return resource ? translate(lang, resource) : translate(lang, 'error_unexpected')
}

export interface Translator {
  lang: Lang
  t: (key: string, ...args: (string | number)[]) => string
  plural: (key: string, count: number, ...args: (string | number)[]) => string
  message: (messageKey: string) => string
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
  const message = useCallback((k: string) => translateMessage(lang, k), [lang])
  const value = useMemo(() => ({ lang, t, plural, message }), [lang, t, plural, message])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useT(): Translator {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useT outside I18nProvider')
  return value
}
