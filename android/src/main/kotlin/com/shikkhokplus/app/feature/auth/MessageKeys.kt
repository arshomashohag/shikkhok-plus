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
        // A number that is not a Bangladeshi mobile, refused by the
        // server's canonicalisation on any route that takes a number.
        "phone.invalid" to R.string.phone_invalid,
        "schedule.duplicate_slot" to R.string.schedule_duplicate_slot,
        "enrollment.student_already_in_batch" to R.string.enrollment_student_already_in_batch,
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
        // D4: classes, attendance and the write queue.
        //
        // The three server-decided session statuses [BR1.6]. A fourth
        // status fails the mapper rather than rendering as a default --
        // and the default would render a cancelled class as one going
        // ahead.
        "session.status.scheduled" to R.string.session_status_scheduled,
        "session.status.held" to R.string.session_status_held,
        "session.status.cancelled" to R.string.session_status_cancelled,
        // **The four queue states** [BR3.2]. These are CLIENT-side
        // vocabulary and reach no response schema [BR3.9] -- the
        // server cannot know whether an item is queued on a device it
        // has never heard from. They are resolved through this map
        // because the screen renders them the same way it renders a
        // server-named key, not because the server sends them.
        //
        // `failed` and `conflicted` carry deliberately different
        // sentences: AC3.1.10 requires the two to be distinguishable,
        // and one wording for both would leave a teacher repeating a
        // request that cannot succeed.
        "queue.state.queued" to R.string.queue_state_queued,
        "queue.state.confirmed" to R.string.queue_state_confirmed,
        "queue.state.failed" to R.string.queue_state_failed,
        "queue.state.conflicted" to R.string.queue_state_conflicted,
        // **The two version conflicts, one per queued path** [BR3.10].
        // Descriptive, and permitted to be, because each is reached
        // only AFTER the lens check -- an unreachable session is
        // refused with the shared NOT_AVAILABLE first, so neither ever
        // reaches a stranger.
        //
        // Two keys rather than one because there are two queued paths
        // guarding two different columns [BR2.1]: attendance against
        // `attendance_version`, the topic log against `topic_version`.
        // The remedy is the same for both -- look at what changed,
        // never retry as-is -- and the copy differs because the thing
        // that changed differs.
        "error.attendance_version_conflict" to
            R.string.attendance_version_conflict,
        "error.topic_version_conflict" to R.string.topic_version_conflict,
        // D4: the four result states [BR4.3]. Two of them are derived
        // server-side rather than typed, and the wordings keep them
        // apart: conflating `not_entered` with `absent` publishes an
        // absence the teacher never recorded, on a shared marksheet.
        "mark.state.marked" to R.string.mark_state_marked,
        "mark.state.absent" to R.string.mark_state_absent,
        "mark.state.not_entered" to R.string.mark_state_not_entered,
        "mark.state.joined_after" to R.string.mark_state_joined_after,
        // **The shared refusal** [BR3.10, security-design § 2.3]. It
        // must read identically whether the thing does not exist or is
        // simply not yours, because the pair of those two IS the
        // oracle -- a caller who can tell them apart can probe ids.
        // The copy therefore names no resource, no owner and no
        // reason, and it must not be "improved" into something more
        // helpful.
        //
        // This is also what a family sees when the marksheet toggle is
        // off [BR5.4]: `app/marks/views.py` refuses that case through
        // the same `refuse()` rather than a distinct code, so the
        // toggle cannot be distinguished from an unreachable seat.
        "teaching.not_available" to R.string.teaching_not_available,
        // The state-based refusals. Each is a ConflictError: the
        // request is well-formed and the current state forbids it, so
        // retrying it unchanged cannot succeed.
        "teaching.batch.inactive" to R.string.teaching_batch_inactive,
        "teaching.session.cancelled" to R.string.teaching_session_cancelled,
        "teaching.session.already_exists" to
            R.string.teaching_session_already_exists,
        "teaching.announcement.deleted" to
            R.string.teaching_announcement_deleted,
        "teaching.seat.not_on_roster" to R.string.teaching_seat_not_on_roster,
        // One replay key, spent on the other queued path. The two
        // paths share one replay store, so the same id cannot mean
        // two different writes from one account.
        "teaching.mutation_id.already_used" to
            R.string.teaching_mutation_id_already_used,
        // Marks. `marks.out_of_range` carries the exam's total in its
        // details, NOT the value submitted [NFR24.14] -- the string
        // here names neither, because the server's `details` are not
        // interpolated into it.
        "marks.out_of_range" to R.string.marks_out_of_range,
        "marks.state_mismatch" to R.string.marks_state_mismatch,
        "marks.result_state.not_enterable" to
            R.string.marks_result_state_not_enterable,
        "marks.exam.total_invalid" to R.string.marks_exam_total_invalid,
        "marks.exam.total_below_recorded" to
            R.string.marks_exam_total_below_recorded,
        // D6: the one deletion refusal that is NOT contentless. Every
        // other refusal on the deletion path discloses nothing, because
        // a stranger could be asking; this one is reached only after
        // the caller has proven they own the number, and a contentless
        // refusal would leave a teacher concluding the feature is
        // broken rather than that they must deal with their classes.
        "governance.deletion.owns_batches" to
            R.string.governance_deletion_owns_batches,
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
