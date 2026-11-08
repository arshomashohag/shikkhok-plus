/**
 * Settings kept in this browser: theme, text size and language; and the
 * account's sign-in settings, which are the server's: the password,
 * adding a phone number or email address, and two-step verification.
 */
import { useLocation } from 'react-router'
import { usePrefs, type TextScale, type ThemePref } from '../../core/prefs'
import { useT } from '../../i18n/i18n'
import { Section, TopBar } from '../../ui/components'
import { useOnline } from '../../core/useResource'
import { AccountEntries, MfaEntry } from './security'
import type { SettingsNotice } from './security/paths'

export function Settings() {
  const { t } = useT()
  const prefs = usePrefs()
  const online = useOnline()
  const notice = (useLocation().state as SettingsNotice | null)?.notice ?? null
  const themes: [ThemePref, string][] = [
    ['system', 'settings_same_as_phone'],
    ['light', 'settings_theme_light'],
    ['dark', 'settings_theme_dark'],
  ]
  const scales: [TextScale, string][] = [
    ['normal', 'settings_same_as_phone'],
    ['large', 'settings_text_large'],
    ['largest', 'settings_text_largest'],
  ]
  return (
    <>
      <TopBar title={t('settings_title')} back="/more" />
      {notice ? (
        <div className="banner" role="status" style={{ marginBottom: 12 }}>
          {notice}
        </div>
      ) : null}
      <Section title={t('web_section_language')}>
        <div className="segmented" role="group" aria-label={t('web_language')}>
          <button
            type="button"
            aria-pressed={prefs.lang === 'bn'}
            onClick={() => prefs.update({ lang: 'bn' })}
            lang="bn"
          >
            বাংলা
          </button>
          <button
            type="button"
            aria-pressed={prefs.lang === 'en'}
            onClick={() => prefs.update({ lang: 'en' })}
            lang="en"
          >
            English
          </button>
        </div>
      </Section>
      <Section title={t('settings_section_theme')}>
        <div className="segmented" role="group" aria-label={t('settings_section_theme')}>
          {themes.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={prefs.theme === value}
              onClick={() => prefs.update({ theme: value })}
            >
              {t(label)}
            </button>
          ))}
        </div>
      </Section>
      <Section title={t('settings_section_text')}>
        <div className="segmented" role="group" aria-label={t('settings_section_text')}>
          {scales.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={prefs.textScale === value}
              onClick={() => prefs.update({ textScale: value })}
            >
              {t(label)}
            </button>
          ))}
        </div>
      </Section>
      <Section title={t('more_section_account')}>
        <ul className="card flush list">
          <AccountEntries offline={online ? null : t('more_needs_connection')} />
          <MfaEntry offline={online ? null : t('more_needs_connection')} />
        </ul>
      </Section>
    </>
  )
}
