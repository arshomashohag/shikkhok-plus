/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

/** The web client's version, from package.json, set at build time. */
declare const __APP_VERSION__: string

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** The public site's https origin, where published hub pages live. */
  readonly VITE_SITE_URL?: string
  /** The hub photo bucket's regional S3 endpoint; the CSP admits it. */
  readonly VITE_MEDIA_ORIGIN?: string
}
