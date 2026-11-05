/**
 * Per-device display preferences: theme, text size, language and the
 * lens last chosen. These are conveniences kept in this browser only —
 * none of them is data, and none is sent anywhere. **The chosen lens is
 * a UI hint, never authorization** [D-2]: the server computes the lens
 * per request whatever this says.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { Lang } from './format'

export type ThemePref = 'system' | 'light' | 'dark'
export type TextScale = 'normal' | 'large' | 'largest'

export interface Prefs {
  theme: ThemePref
  textScale: TextScale
  lang: Lang
}

const KEY = 'sp.prefs'

function defaultLang(): Lang {
  const langs =
    typeof navigator === 'undefined' ? [] : (navigator.languages ?? [navigator.language])
  // Bangla-first, as the Android app: English only when the browser asks.
  return langs.some((l) => l?.toLowerCase().startsWith('en')) &&
    !langs.some((l) => l?.toLowerCase().startsWith('bn'))
    ? 'en'
    : 'bn'
}

export function readPrefs(): Prefs {
  const fallback: Prefs = { theme: 'system', textScale: 'normal', lang: defaultLang() }
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return fallback
    const p = JSON.parse(raw) as Partial<Prefs>
    return {
      theme: p.theme === 'light' || p.theme === 'dark' ? p.theme : 'system',
      textScale: p.textScale === 'large' || p.textScale === 'largest' ? p.textScale : 'normal',
      lang: p.lang === 'en' || p.lang === 'bn' ? p.lang : fallback.lang,
    }
  } catch {
    return fallback
  }
}

interface PrefsValue extends Prefs {
  update: (patch: Partial<Prefs>) => void
}

const PrefsContext = createContext<PrefsValue | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(readPrefs)

  const update = useCallback((patch: Partial<Prefs>) => {
    setPrefs((current) => {
      const next = { ...current, ...patch }
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next))
      } catch {
        // Private mode: the preference lasts this visit only.
      }
      return next
    })
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (prefs.theme === 'system') delete root.dataset.theme
    else root.dataset.theme = prefs.theme
    root.dataset.textScale = prefs.textScale
    root.lang = prefs.lang
  }, [prefs])

  const value = useMemo(() => ({ ...prefs, update }), [prefs, update])
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>
}

export function usePrefs(): PrefsValue {
  const value = useContext(PrefsContext)
  if (!value) throw new Error('usePrefs outside PrefsProvider')
  return value
}
