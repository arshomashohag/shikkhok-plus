package com.shikkhokplus.app.core.queue

import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.util.UUID

/**
 * Which of the two mid-class paths a queued write targets [BR3.1].
 *
 * **Exactly two, and the closed set is the rule.** NFR5 permits
 * offline writes for the mid-class path only, which FR3.6 defines as
 * attendance AND the topic log. A third member here would be a third
 * path queueing, which BR3.1's violation_behaviour (b) asserts against:
 * every other write requires connectivity and surfaces an explicit
 * retry prompt rather than queueing.
 *
 * The version each path guards is named on the enum rather than left to
 * the call site, because they are different columns —
 * `attendance_version` and `topic_version` — carrying the same
 * refuse-on-conflict rule [BR2.1].
 */
@Serializable
enum class QueueTarget {
    /** A whole roster for one session [BR3.3]. */
    @SerialName("attendance")
    ATTENDANCE,

    /** One session's subject and topic [BR2.1]. */
    @SerialName("topic")
    TOPIC,
}

/**
 * One seat's presence as the teacher recorded it offline.
 *
 * **No name and no phone number** [security-design § 7.1]. The queue
 * file holds enrollment ids, booleans, a version number and two UUIDs —
 * nothing else — which is what makes the recorded decision not to
 * encrypt it [§ 7.2] defensible rather than lazy. A display name here
 * would turn a roster of opaque ids into identifying data and reopen
 * that decision.
 *
 * @property enrollmentId The seat, which is the teacher-facing key
 * @property present Whether the student was there
 */
@Serializable
data class AttendanceEntry(
    @SerialName("enrollment_id") val enrollmentId: String,
    val present: Boolean,
)

/**
 * What a queued write carries, as it sits on the device.
 *
 * **The payload is the whole roster, never one seat** [BR3.5]. A
 * per-student write leaves attendance half-saved after a mid-roster
 * connection drop, and a retry cannot reconcile that on screen
 * [AC3.1.5]. The server applies it in one transaction; the queue
 * carries it as one item for the same reason.
 *
 * @property id This item's own identity on the device, stable across
 *   restarts so the screen can address a specific queued write.
 *
 *   **Distinct from [clientMutationId]**, deliberately. The mutation id
 *   is the server's replay key and changes on every re-apply [BR3.7];
 *   this one names the row the teacher is looking at and does not.
 * @property target Which of the two permitted paths this is
 * @property sessionId The session the write applies to
 * @property baseVersion The version this write was composed against
 *   [BR3.3]. The server applies the write only if this is still
 *   current, which is the whole mechanism: a roster queued at 10:15,
 *   corrected from a tablet at 11:00, must not silently reinstate the
 *   stale mark when the phone reconnects at 11:40 [ADR-006]
 * @property clientMutationId The server's replay key, scoped per
 *   account per endpoint [BR3.8]. A duplicate returns the ORIGINAL
 *   stored result with 200 and writes nothing
 * @property entries The roster, empty for a [QueueTarget.TOPIC] write
 * @property topic The topic text, null for an attendance write.
 *
 *   **Null and empty are different** [BR2.2]: null is a topic never
 *   written, an empty string is one the teacher deliberately saved as
 *   blank. Collapsing them makes it impossible to tell a class nobody
 *   logged from one logged as nothing
 * @property state Where this item is [BR3.2]
 * @property conflictCurrentVersion The version the server said was
 *   current when it refused, or null when this item has not conflicted.
 *   Carried so re-apply can compose against it [BR3.7]
 * @property serverRetryable Whether the last failed send was one the
 *   server said may be retried. **Read from the envelope, never
 *   inferred** [TC-9]; true when no answer arrived at all. The
 *   automatic sync skips a FAILED item the server called final, which
 *   would otherwise be re-sent every cycle and refused every time.
 *   Defaults to true, so a queue file written before this field existed
 *   still drains
 */
@Serializable
data class QueuedWrite(
    val id: String,
    val target: QueueTarget,
    @SerialName("session_id") val sessionId: String,
    @SerialName("base_version") val baseVersion: Int,
    @SerialName("client_mutation_id") val clientMutationId: String,
    val entries: List<AttendanceEntry> = emptyList(),
    val topic: String? = null,
    val state: QueueState = QueueState.QUEUED,
    @SerialName("conflict_current_version") val conflictCurrentVersion: Int? = null,
    @SerialName("server_retryable") val serverRetryable: Boolean = true,
) {
    /**
     * Mark this item failed, recording whether the server allows a retry.
     *
     * One function for both senders -- the screen's own send and the
     * background drain -- so they cannot record a failure differently.
     *
     * @param envelope The refusal, or null when nothing arrived
     * @return The failed item
     */
    fun failed(envelope: ErrorEnvelope?): QueuedWrite =
        copy(
            state = QueueState.FAILED,
            serverRetryable = envelope?.error?.retryable ?: true,
        )

    /**
     * Whether the automatic sync may send this without being asked.
     *
     * The state decides first ([QueueState.isAutomaticallySendable]);
     * a FAILED item is then sent only if the server said a retry could
     * help. The teacher can still retry it by hand.
     *
     * @return True when the background drain should try it
     */
    fun isAutomaticallySendable(): Boolean =
        state.isAutomaticallySendable() &&
            (state != QueueState.FAILED || serverRetryable)


    /**
     * Compose the NEW write a re-apply sends [BR3.7].
     *
     * **The obvious implementation reuses the old `client_mutation_id`,
     * and it fails silently in the worst possible way.** That id carries
     * a unique constraint, and § B.7 makes a duplicate return the
     * ORIGINAL stored result with 200 while writing nothing — so a
     * re-apply that reused it would report success and change nothing,
     * which is the exact opposite of what the teacher asked for. The
     * teacher would see a confirmation and the record would still hold
     * somebody else's roster.
     *
     * Re-apply is a **new decision by the teacher**, not a replay of the
     * old one, and the two differences say so: a freshly generated id,
     * and the version the server reported as current rather than the one
     * that was refused.
     *
     * Returning a new item rather than mutating is what makes that
     * checkable — a test asserts both fields differ from the refused
     * attempt's, which it cannot do if the old values were overwritten
     * in place.
     *
     * @param currentVersion The version the server reported as current
     * @param freshMutationId The new replay key. Injectable so a test
     *   can assert the value rather than merely that it changed; the
     *   default generates one
     * @return A fresh [QueueState.QUEUED] item for the same roster
     */
    fun reapplied(
        currentVersion: Int = conflictCurrentVersion ?: baseVersion,
        freshMutationId: String = newMutationId(),
    ): QueuedWrite {
        require(freshMutationId != clientMutationId) {
            "re-apply must carry a FRESH client_mutation_id [BR3.7]: " +
                "reusing '$clientMutationId' hits the replay path, returns " +
                "200 with the original stored result, and changes nothing."
        }
        return copy(
            id = newItemId(),
            baseVersion = currentVersion,
            clientMutationId = freshMutationId,
            state = QueueState.QUEUED,
            conflictCurrentVersion = null,
        )
    }

    companion object {
        /**
         * A fresh replay key for a brand-new write.
         *
         * `randomUUID` and not a device identifier of any kind: no
         * AAID, no SIM serial, no build serial, no IMEI
         * [project.md: NEVER transmit a device identifier; TC-3, D-37].
         * A random v4 UUID carries nothing about the handset.
         *
         * @return A fresh mutation id
         */
        fun newMutationId(): String = UUID.randomUUID().toString()

        /**
         * A fresh device-local identity for a queue item.
         *
         * @return A fresh item id
         */
        fun newItemId(): String = UUID.randomUUID().toString()

        /**
         * Build a first attendance write for a session.
         *
         * @param sessionId The session being marked
         * @param baseVersion The `attendance_version` the roster was
         *   composed against
         * @param entries One entry per seat on the roster
         * @return A queued item
         */
        fun attendance(
            sessionId: String,
            baseVersion: Int,
            entries: List<AttendanceEntry>,
        ): QueuedWrite =
            QueuedWrite(
                id = newItemId(),
                target = QueueTarget.ATTENDANCE,
                sessionId = sessionId,
                baseVersion = baseVersion,
                clientMutationId = newMutationId(),
                entries = entries,
            )

        /**
         * Build a first topic write for a session.
         *
         * @param sessionId The session being logged
         * @param baseVersion The `topic_version` it was composed against
         * @param topic The topic text, which may be empty but not null —
         *   an empty string is a topic deliberately saved blank [BR2.2]
         * @return A queued item
         */
        fun topic(
            sessionId: String,
            baseVersion: Int,
            topic: String,
        ): QueuedWrite =
            QueuedWrite(
                id = newItemId(),
                target = QueueTarget.TOPIC,
                sessionId = sessionId,
                baseVersion = baseVersion,
                clientMutationId = newMutationId(),
                topic = topic,
            )
    }
}
