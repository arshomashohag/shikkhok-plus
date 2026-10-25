package com.shikkhokplus.app.core.queue

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The four states a queued write is in, and never a fifth [BR3.2].
 *
 * **Four, all distinct and all visible, is what separates this queue
 * from the one `project.md` forbids.** That NEVER protects against a
 * queue that LOOKS LIKE SUCCESS — a single state rendered as saved. Its
 * own source, NFR5, reads *"Permitted for the mid-class path only — the
 * topic log and attendance queue locally and sync when connectivity
 * returns"*, so the requirement was always scoped and the restatement
 * dropped the scope. BR3.1 records the reconciliation; this enum is the
 * mechanical half of it.
 *
 * **[QUEUED] is never rendered as [CONFIRMED]**, which is BR3.1's
 * violation_behaviour (a) and is asserted directly.
 *
 * **[FAILED] and [CONFLICTED] are different states with different
 * remedies**, which is BR3.6 and AC3.1.10. Collapsing them is the
 * defect the two-state implementation ships: `failed` means "try
 * again", and retrying a conflict as-is is guaranteed to be refused
 * again — or worse, invites a retry wrapper that strips the version and
 * overwrites the correction somebody else made.
 *
 * An exhaustive enum rather than a nullable flag or a boolean pair, so
 * a `when` over it fails to compile if a fifth state ever appears
 * rather than quietly rendering one of the existing four.
 *
 * **These names never reach the wire** [BR3.9]. The server cannot know
 * whether an item is queued on a device it has never heard from, so a
 * `queue_state` field would be a value the server has to invent and
 * which is wrong for every device except the one that just called. The
 * backend's schema gate asserts the absence; this type is client-side
 * vocabulary only.
 */
@Serializable
enum class QueueState {
    /**
     * On the phone, not sent. Rendered as saved-on-phone-not-yet-sent
     * and **never** as confirmed [BR3.1].
     */
    @SerialName("queued")
    QUEUED,

    /** The server has it, and said so. */
    @SerialName("confirmed")
    CONFIRMED,

    /**
     * The send did not succeed and retrying is the right remedy.
     *
     * A transport failure, or a refusal the server marked retryable.
     * Distinct from [CONFLICTED] because the remedy differs.
     */
    @SerialName("failed")
    FAILED,

    /**
     * The server refused it: somebody else wrote first [BR3.6].
     *
     * **Retrying as-is is wrong**, so no automatic retry is ever
     * scheduled for this state. The teacher is shown what they recorded
     * offline against what the record now says, and the offline entry is
     * retained until they explicitly re-apply or discard. Nothing is
     * merged, nothing silently applied, nothing silently discarded —
     * merging would mean inventing a rule for a student the two rosters
     * disagree about, which is a business decision a sync layer must not
     * make.
     */
    @SerialName("conflicted")
    CONFLICTED,
    ;

    /**
     * Whether the sync loop may send this item without being asked.
     *
     * **A property of the state, not a judgement at the call site** —
     * the same shape the backend's error taxonomy uses for `retryable`.
     * A sync loop deciding this itself is how [CONFLICTED] acquires an
     * automatic retry by accident.
     *
     * @return True only for the two states a send can help
     */
    fun isAutomaticallySendable(): Boolean = this == QUEUED || this == FAILED
}
