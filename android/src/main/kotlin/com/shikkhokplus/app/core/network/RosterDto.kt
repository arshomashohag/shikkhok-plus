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
 * @property status `dormant`, `active` or `inactive`, decided server-side
 * @property inactiveFrom The recorded date, if any
 */
@Serializable
data class RosterRowDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    @SerialName("fee_amount") val feeAmount: Money? = null,
    val status: String,
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
 * @property enrollmentCount How many seats, counted server-side
 */
@Serializable
data class BatchDto(
    val id: String,
    val name: String,
    val subjects: List<String> = emptyList(),
    @SerialName("default_fee") val defaultFee: Money? = null,
    @SerialName("fee_due_day") val feeDueDay: Int? = null,
    val active: Boolean = true,
    @SerialName("enrollment_count") val enrollmentCount: Int = 0,
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
