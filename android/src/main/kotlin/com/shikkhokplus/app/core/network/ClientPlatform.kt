package com.shikkhokplus.app.core.network

import io.ktor.http.HeadersBuilder

/**
 * Which app this is, said on every request: `android` and the app's own
 * version, nothing else.
 *
 * **What it is for.** The server records which app an account uses
 * when it issues a token -- at sign-in and at every refresh -- so it can
 * answer "how many people use the Android app, and on which version".
 * Two headers answer that and nothing more is sent.
 *
 * **What it is not.** It is not a device identifier [TC-3, D-37]: the
 * platform is a literal and the version is `versionName`, the same
 * string for every install of a build. Nothing here reads the device,
 * the model, the SIM or a User-Agent.
 *
 * **Sent on every request rather than only on the two auth routes**,
 * because the token routes are reached three ways -- verify, the
 * cold-start refresh and the mid-session renewal in [SessionRenewal] --
 * and a header attached per route is a header one of them forgets. The
 * server reads it only where it issues a token and ignores it elsewhere.
 */
object ClientPlatform {
    /** The header naming the app. */
    const val PLATFORM_HEADER: String = "X-Client-Platform"

    /** The header carrying the app's version. */
    const val VERSION_HEADER: String = "X-Client-Version"

    /** This app's platform, as the server's two-value enum spells it. */
    const val PLATFORM: String = "android"

    /** The longest version the server stores. */
    private const val VERSION_MAX = 32

    /** The punctuation a version may carry besides letters and digits. */
    private const val VERSION_PUNCTUATION = ".+-"

    /**
     * Reduce a version name to what the server accepts.
     *
     * The server keeps `[0-9A-Za-z.+-]{1,32}` and drops anything else
     * whole, so a stray character from a CI-supplied `versionName` would
     * cost the version entirely. Removing the character and truncating
     * keeps the part that is a version.
     *
     * @param raw The build's `versionName`
     * @return The sanitised version, or null when nothing usable remains
     */
    fun version(raw: String): String? =
        raw
            .filter { it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it in VERSION_PUNCTUATION }
            .take(VERSION_MAX)
            .ifEmpty { null }

    /**
     * Write both headers onto a request, replacing any already there.
     *
     * @param headers The request's headers
     * @param version The sanitised version, or null to send none
     */
    fun applyTo(headers: HeadersBuilder, version: String?) {
        headers[PLATFORM_HEADER] = PLATFORM
        if (version != null) headers[VERSION_HEADER] = version
    }
}
