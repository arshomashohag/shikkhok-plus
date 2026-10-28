package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One seat as the server describes it.
 *
 * **`status` arrives decided.** The client switches on this enum and
 * never compares a date or an amount of its own: `if (balance > 0)
 * "Due"` is a business rule about what counts as due, written where it
 * looks like presentation [TC-9, D-31].
 *
 * `feeAmount` is a [Money], so a JSON number fails to decode rather
 * than being quietly converted to a double [TC-7, D-20].
 *
 * @property enrollmentId The teacher-facing key for this seat
 * @property displayName The teacher-typed name
 * @property guardianPhone The teacher-typed guardian contact, if any
 * @property feeAmount This seat's fee, or null when it inherits
 * @property status `dormant`, `active` or `inactive`, decided server-side.
 *   **A different axis from acceptance**, and the two sit side by side
 *   rather than folding together: an inactive seat keeps whatever
 *   decisions its links carry, because leaving a batch is not
 *   un-accepting it
 * @property studentState The student link's own decision — `pending`,
 *   `accepted` or `declined` [BR2.1]
 * @property guardianState The guardian link's own decision, plus a
 *   fourth value `absent` when no guardian was recorded [BR2.2].
 *
 *   **Both states arrive per link and the seat appears once.** A
 *   student who accepted beside a guardian who declined is a real seat
 *   and neither single value describes it: the student is enrolled and
 *   owes a fee, the guardian simply does not watch.
 *
 *   **These default to nothing.** A missing field is a contract
 *   failure the decoder must report, not a seat to render as pending —
 *   the mapper turns an unrecognised value into an explicit failure
 *   state for the same reason [RosterStateMapper].
 * @property isRemovable Whether removal would succeed, **decided
 *   server-side** [BR3.1, NFR14.31].
 *
 *   It could be derived from the two states above today, and deriving
 *   it is the trap: removal tests a second condition this row does not
 *   carry — the erasure markers [BR7.1] — so a derivation would offer
 *   removal on an erased seat, whose decisions both read `pending`.
 * @property inactiveFrom The recorded date, if any
 */
@Serializable
data class RosterRowDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    @SerialName("fee_amount") val feeAmount: Money? = null,
    val status: String,
    @SerialName("student_state") val studentState: String,
    @SerialName("guardian_state") val guardianState: String,
    @SerialName("is_removable") val isRemovable: Boolean,
    @SerialName("inactive_from") val inactiveFrom: String? = null,
)

/**
 * One batch as its owner sees it.
 *
 * @property id The batch
 * @property name The teacher's name for the class
 * @property subjects The subjects taught
 * @property defaultFee The fee an enrollment inherits
 * @property feeDueDay Day of month 1-31
 * @property active False means read-only history
 * @property enrollmentCount How many seats, counted server-side. The
 *   **denominator** of "9 of 12 accepted", and it counts every seat the
 *   teacher created including declined ones [BR1.4]
 * @property acceptedCount How many of those seats at least one link has
 *   accepted, counted server-side [BR1.2, BR1.3].
 *
 *   **The client never counts rows to derive this** [TC-9]. A client
 *   counting is a client deciding what counts as accepted, and it is
 *   wrong the moment the roster paginates because it can only count the
 *   rows it holds.
 */
@Serializable
data class BatchDto(
    val id: String,
    val name: String,
    val subjects: List<String> = emptyList(),
    @SerialName("subject_options") val subjectOptions: List<SubjectOptionDto> = emptyList(),
    val schedule: List<ScheduleSlotDto> = emptyList(),
    @SerialName("default_fee") val defaultFee: Money? = null,
    @SerialName("fee_due_day") val feeDueDay: Int? = null,
    val active: Boolean = true,
    @SerialName("enrollment_count") val enrollmentCount: Int = 0,
    @SerialName("accepted_count") val acceptedCount: Int = 0,
)

/**
 * One weekly class of a batch.
 *
 * Times are `HH:MM`, 24-hour, exactly as the server sends them; the
 * screen formats them for display.
 *
 * @property weekday 0-6, Monday through Sunday
 * @property startTime When it starts
 * @property endTime When it ends
 */
@Serializable
data class ScheduleSlotDto(
    val weekday: Int,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String,
)

/**
 * One subject of a batch, with the key exam and class writes take.
 *
 * The batch list used to carry subject NAMES only, so there was no key
 * to send and an exam could not be created from the app at all.
 *
 * @property id The `batch_subject_id`
 * @property name The subject's name, as the teacher typed it
 */
@Serializable
data class SubjectOptionDto(
    val id: String,
    val name: String,
)

/**
 * One reachable child as a guardian sees it.
 *
 * Carries `batchName` because attribution is required even when there
 * is only one child [AC2.8.5] — that is where it is most needed, since
 * the selection list is where it would otherwise have been shown.
 *
 * @property enrollmentId The seat, which the route is keyed on
 * @property displayName The teacher-typed name for the child
 * @property batchName Which class
 * @property teacherDisplayName Which teacher recorded this
 */
@Serializable
data class GuardianChildDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
)
