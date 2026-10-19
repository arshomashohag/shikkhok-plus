package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.R

/**
 * Resolves a server `message_key` to a local string resource.
 *
 * **The server names which string to show; it never sends the string.**
 * A server-sent English message cannot be localized by the client, and
 * in a Bangla-first UI that guarantees untranslated English error text
 * in front of a teacher [TC-15, D-43].
 *
 * An unknown key falls back to a generic message rather than showing
 * the key itself. Showing the raw key would be a worse failure than a
 * vague message: it is untranslatable, it looks broken, and it leaks
 * the server's internal vocabulary.
 */
object MessageKeys {
    private val resources: Map<String, Int> = mapOf(
        "error.network.unreachable" to R.string.error_network_unreachable,
        "error.unexpected" to R.string.error_unexpected,
        "auth.otp.not_valid" to R.string.auth_otp_not_valid,
        "auth.otp.temporarily_unavailable" to
            R.string.auth_otp_temporarily_unavailable,
        "auth.token.not_valid" to R.string.auth_token_not_valid,
        // U4: batches, enrollment seats and the guardian's children.
        "batch.not_found" to R.string.batch_not_found,
        "batch.create.subject_required" to
            R.string.batch_create_subject_required,
        "enrollment.remove.claimed" to R.string.enrollment_remove_claimed,
        "enrollment.remove.erased" to R.string.enrollment_remove_erased,
        "authz.lens.not_available" to R.string.authz_lens_not_available,
        "roster.status.dormant" to R.string.roster_status_dormant,
        "roster.status.active" to R.string.roster_status_active,
        "roster.status.inactive" to R.string.roster_status_inactive,
        // Staging only. The key exists in the published list, so the
        // cross-surface gate requires a string for it even though a
        // production build can never receive it.
        "staging.outbox.empty" to R.string.staging_outbox_empty,
    )

    /**
     * Resolve one key.
     *
     * @param key The server's `message_key`
     * @return The string resource id to render
     */
    fun resolve(key: String): Int =
        resources[key] ?: R.string.error_unexpected

    /**
     * Report whether a key is known.
     *
     * Exposed so a test can assert the map covers every key the server
     * can actually send, rather than discovering a gap in front of a
     * user.
     *
     * @param key The key to check
     * @return True when the key maps to a specific string
     */
    fun isKnown(key: String): Boolean = resources.containsKey(key)

    /** Every key this client can render specifically. */
    val knownKeys: Set<String> get() = resources.keys
}
