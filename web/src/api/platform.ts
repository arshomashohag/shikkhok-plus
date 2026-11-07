/**
 * Which app this is, sent on every request.
 *
 * The server records the platform and version an account last used from
 * these two headers when it signs in or renews its token, so the
 * administrators can see how many people use the web client and which
 * versions are still about. They identify the app build, never the
 * person or the device [TC-3]: the same two values go out from every
 * browser running this release.
 */

export const PLATFORM_HEADER = 'X-Client-Platform'
export const VERSION_HEADER = 'X-Client-Version'

/** The characters and length the server accepts for a version. */
const VERSION_CHARS = /[^0-9A-Za-z.+-]/g
const VERSION_MAX = 32

/**
 * The version as the server accepts it: `[0-9A-Za-z.+-]{1,32}`.
 *
 * @param raw The package version injected at build time
 */
export function clientVersion(raw: string = __APP_VERSION__): string {
  return raw.replace(VERSION_CHARS, '').slice(0, VERSION_MAX) || '0'
}

/** The two headers, ready to spread into a request's headers. */
export const CLIENT_HEADERS: Readonly<Record<string, string>> = Object.freeze({
  [PLATFORM_HEADER]: 'web',
  [VERSION_HEADER]: clientVersion(),
})
