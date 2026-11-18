/**
 * "Preview as public": the owner's page as it would read once published,
 * drafts included, opened in a tab of its own from the listing editor.
 *
 * **The page is the server's, and it runs nothing here.** The HTML comes
 * from an authenticated read (`GET /v1/hub/listing/preview`) and is shown
 * through `<iframe srcdoc>` with `sandbox=""` — every restriction on, no
 * `allow-*` token — so the document gets an opaque origin, no script, no
 * form, no popup and no top-level navigation, whatever it holds. It is
 * never given a URL of its own: the read needs the session's token, which
 * a frame `src` could not carry.
 *
 * The frame inherits this page's Content-Security-Policy, whose
 * `style-src` names the site's origin (vite.config.ts), because the
 * preview links its stylesheet there: this host serves no `/hub-assets/`
 * [R11]. A link clicked inside the frame loads inside the frame, where
 * the public page's own `frame-ancestors 'none'` refuses it, so nothing
 * leaves the preview.
 */
import { useSearchParams } from 'react-router'
import { readHubPreview } from '../../../api/endpoints'
import type { Lang } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { ErrorCard, Loading, TopBar } from '../../../ui/components'
import { paths } from '../paths'

const LOCALES: readonly Lang[] = ['bn', 'en']

const LANGUAGE_NAME: Record<Lang, string> = {
  bn: 'settings_language_bangla',
  en: 'settings_language_english',
}

export function HubPreview() {
  const { t, lang } = useT()
  const [params, setParams] = useSearchParams()
  const asked = params.get('locale')
  const locale: Lang = asked === 'en' || asked === 'bn' ? asked : lang
  const { resource, reload } = useResource((signal) => readHubPreview(locale, signal), [locale])
  const title = t('hub_preview_as_public')

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={4} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={title} error={resource.error} onRetry={reload} />
  else
    body = (
      <iframe
        title={title}
        className="hub-preview-frame"
        sandbox=""
        srcDoc={resource.data}
        referrerPolicy="no-referrer"
      />
    )

  return (
    <>
      <TopBar title={title} back={paths.hub()} />
      <div className="segmented" role="group" aria-label={title} style={{ marginBottom: 12 }}>
        {LOCALES.map((l) => (
          <button
            key={l}
            type="button"
            lang={l}
            aria-pressed={l === locale}
            onClick={() => setParams({ locale: l }, { replace: true })}
          >
            {t(LANGUAGE_NAME[l])}
          </button>
        ))}
      </div>
      {body}
    </>
  )
}
