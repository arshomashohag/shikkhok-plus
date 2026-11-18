/**
 * The public site: where a published hub page lives.
 *
 * **Its origin is fixed at build time** (`VITE_SITE_URL`), as the API's is,
 * because the page's Content-Security-Policy names it too (vite.config.ts):
 * the owner's preview links its stylesheet there [R11]. Empty when the
 * build names no site, as a local build does; then no link to a public
 * page is offered rather than one to a guessed host.
 */
import type { Lang } from './format'

/** The site's origin with no trailing slash, or empty when the build names none. */
export function siteUrl(): string {
  return (import.meta.env.VITE_SITE_URL ?? '').replace(/\/+$/, '')
}

/**
 * Where an owner's published page lives on the site.
 *
 * @param locale The page's language
 * @param slug The owner's slug, as the server holds it
 * @returns The page's URL, or null when the build names no site
 */
export function publicPageUrl(locale: Lang, slug: string): string | null {
  const site = siteUrl()
  return site ? `${site}/hub/${locale}/t/${encodeURIComponent(slug)}` : null
}
