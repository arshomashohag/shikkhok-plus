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
        // D1: signup and the acceptance decisions. Both are published
        // by the backend, so the cross-surface gate requires a string
        // for each before this app can build.
        "signup.number.already_registered" to
            R.string.signup_number_already_registered,
        "signup.temporarily_unavailable" to
            R.string.signup_temporarily_unavailable,
        // Staging only. The key exists in the published list, so the
        // cross-surface gate requires a string for it even though a
        // production build can never receive it.
        "staging.outbox.empty" to R.string.staging_outbox_empty,
        // D3: fees, claims and verification. Every key the backend
        // publishes needs a string here before this app builds, which
        // is what keeps a new raise site from shipping a backend that
        // is correct beside an app rendering a generic fallback -- a
        // failure that looks like a working error message and is
        // therefore never reported.
        "fees.not_available" to R.string.fees_not_available,
        "fees.resolution.not_set" to R.string.fees_resolution_not_set,
        "fees.claim.no_open_cycle" to R.string.fees_claim_no_open_cycle,
        "fees.claim.amount_not_positive" to
            R.string.fees_claim_amount_not_positive,
        "fees.claim.channel_unknown" to R.string.fees_claim_channel_unknown,
        "fees.claim.not_found" to R.string.fees_claim_not_found,
        "fees.verification.amount_negative" to
            R.string.fees_verification_amount_negative,
        "fees.verification.disposition_required" to
            R.string.fees_verification_disposition_required,
        "fees.verification.disposition_not_applicable" to
            R.string.fees_verification_disposition_not_applicable,
        "fees.verification.disposition_unknown" to
            R.string.fees_verification_disposition_unknown,
        "fees.verification.already_decided" to
            R.string.fees_verification_already_decided,
        // The four server-decided fee statuses [BR6.1]. The mapper
        // names these keys and the screen renders them; a fifth
        // status fails the mapper rather than rendering as a default.
        "fees.status.paid" to R.string.fees_status_paid,
        "fees.status.partly_paid" to R.string.fees_status_partly_paid,
        "fees.status.unpaid" to R.string.fees_status_unpaid,
        "fees.status.waived" to R.string.fees_status_waived,
        // The four claim statuses [BR6.3] and the two dispositions.
        "fees.claim.pending" to R.string.fees_claim_pending,
        "fees.claim.approved_full" to R.string.fees_claim_approved_full,
        "fees.claim.approved_partial" to R.string.fees_claim_approved_partial,
        "fees.claim.rejected" to R.string.fees_claim_rejected,
        "fees.claim.corrected" to R.string.fees_claim_corrected,
        "fees.disposition.carried" to R.string.fees_disposition_carried,
        "fees.disposition.waived" to R.string.fees_disposition_waived,
        // The destination copy shown where no number is set.
        "fees.destination.ask_teacher" to R.string.payment_ask_teacher,
        // The push reminder's own keys. The server names them and
        // never sends the text [TC-15, D-43].
        "fees.reminder.title" to R.string.fees_reminder_title,
        "fees.reminder.body" to R.string.fees_reminder_body,
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
