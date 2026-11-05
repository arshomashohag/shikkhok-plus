/**
 * Installability and updates.
 *
 * * **Install**: Chromium browsers fire `beforeinstallprompt` once the
 *   page qualifies (manifest, icons, service worker). We keep the event
 *   and offer "Install app" in More and the side rail; Safari and Firefox
 *   use their own menu, so the entry simply does not appear there.
 * * **Update**: `registerType: 'prompt'` — a new version waits until the
 *   person reloads, so it never swaps code under a half-filled form.
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
import { registerSW } from 'virtual:pwa-register'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

interface PwaValue {
  canInstall: boolean
  installed: boolean
  install: () => Promise<void>
  updateReady: boolean
  applyUpdate: () => void
  dismissUpdate: () => void
}

const PwaContext = createContext<PwaValue | null>(null)

function isStandalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.matchMedia?.('(display-mode: window-controls-overlay)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

export function PwaProvider({ children }: { children: ReactNode }) {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [installed, setInstalled] = useState(isStandalone)
  const [updateReady, setUpdateReady] = useState(false)
  const [update, setUpdate] = useState<((reload?: boolean) => Promise<void>) | null>(null)

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setDeferred(e as BeforeInstallPromptEvent)
    }
    const onInstalled = () => {
      setInstalled(true)
      setDeferred(null)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  useEffect(() => {
    if (!('serviceWorker' in navigator) || import.meta.env.DEV) return
    const updateSW = registerSW({
      onNeedRefresh: () => setUpdateReady(true),
    })
    setUpdate(() => updateSW)
  }, [])

  const install = useCallback(async () => {
    if (!deferred) return
    await deferred.prompt()
    await deferred.userChoice
    setDeferred(null)
  }, [deferred])

  const applyUpdate = useCallback(() => {
    void update?.(true)
  }, [update])

  const value = useMemo(
    () => ({
      canInstall: deferred !== null && !installed,
      installed,
      install,
      updateReady,
      applyUpdate,
      dismissUpdate: () => setUpdateReady(false),
    }),
    [deferred, installed, install, updateReady, applyUpdate],
  )
  return <PwaContext.Provider value={value}>{children}</PwaContext.Provider>
}

export function usePwa(): PwaValue {
  const value = useContext(PwaContext)
  if (!value) throw new Error('usePwa outside PwaProvider')
  return value
}
