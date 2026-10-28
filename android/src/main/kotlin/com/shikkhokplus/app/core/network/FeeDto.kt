package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One period's fee as the server describes it.
 *
 * **`status` arrives decided** [BR6.1]. The client switches on this
 * enum and never compares an amount of its own: `if (balance > 0)
 * "Due" else "Paid"` is a business rule about what counts as due,
 * written where it looks like presentation — and it diverges the first
 * time a waiver is involved, because a fully waived cycle has a zero
 * balance and is **not** paid.
 *
 * `charged` and `outstanding` are [Money], so a JSON **number** fails
 * to decode rather than being quietly converted to a double [TC-7,
 * D-20]. That lenient conversion is the real failure mode and it
 * passes a happy-path test on both sides.
 *
 * @property period The calendar month as `YYYY-MM`
 * @property dueDate The due date after the short-month clamp, which
 *   the server computed [BR2.2] — the client never derives it from an
 *   anchor day
 * @property charged What was charged for this period
 * @property outstanding What is still owed, floored at zero server-side
 * @property status `paid`, `partly_paid`, `unpaid` or `waived`,
 *   decided server-side. **Four values rather than two**, and the
 *   fourth is the whole reason the enum exists
 */
@Serializable
data class FeeCycleDto(
    val period: String,
    @SerialName("due_date") val dueDate: String,
    val charged: Money,
    val outstanding: Money,
    val status: String,
)

/**
 * One seat's periods, with the total the SERVER computed.
 *
 * **A wrapper rather than a bare array, and the total is why.** The
 * client must not sum [cycles]: that would be money arithmetic on
 * this side, which [D-20] forbids outright, and it would be wrong the
 * moment the history paginates — a page of three periods would report
 * a total that is not the balance.
 *
 * @property cycles One row per generated period, oldest first
 * @property totalOutstanding What this seat still owes in total
 */
@Serializable
data class FeeHistoryDto(
    val cycles: List<FeeCycleDto> = emptyList(),
    @SerialName("total_outstanding") val totalOutstanding: Money,
)

/**
 * One seat's fee position on a teacher's roster.
 *
 * **Carries no collection number** [BR6.4, NFR14.33]. The teacher's
 * payment destination reaches exactly one response and this is not it;
 * a gate over the generated schema asserts that as an equality rather
 * than a membership, so the field spreading here would fail the build.
 *
 * @property enrollmentId The teacher-facing key, never an account id
 * @property displayName The teacher-typed name
 * @property outstanding What this seat owes across every period
 * @property currentPeriod The latest generated period, or null
 * @property currentStatus That period's status, or null
 * @property dueDate That period's due date, or null
 * @property daysOverdue How late the oldest unpaid period is, decided by
 *   the server against Bangladesh's date, or null
 * @property verifying The total of claims waiting for the teacher, or null
 */
@Serializable
data class RosterFeeRowDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    val outstanding: Money,
    @SerialName("current_period") val currentPeriod: String? = null,
    @SerialName("current_status") val currentStatus: String? = null,
    @SerialName("due_date") val dueDate: String? = null,
    @SerialName("days_overdue") val daysOverdue: Int? = null,
    val verifying: Money? = null,
)

/**
 * A payment claim and its outcome, as its submitter sees it.
 *
 * `previousDecision` is carried deliberately: a corrected verification
 * is visible to the teacher **and** to that student and guardian, never
 * hidden from either party [BR5.7, FR9.2].
 *
 * @property claimId The claim
 * @property period The period it resolved to at submission
 * @property claimedAmount What was claimed
 * @property approvedAmount What was accepted, or null while pending
 * @property status `pending`, `approved_full`, `approved_partial` or
 *   `rejected`, set server-side [BR6.3]. A guardian must be able to
 *   tell a partial approval from a full one, or a dispute has no
 *   shared record
 * @property shortfallDisposition `carried` or `waived`, where one
 *   applies. The two have opposite consequences for the student, so
 *   the value is shown rather than summarised
 * @property channel Which service the money moved through
 * @property submittedAt When it was submitted
 * @property verifiedAt When it was decided, or null
 * @property previousDecision The prior decision, on a correction. Every
 *   value in it is a string, including the amount, so a money value
 *   inside it crosses the wire under the same rule as every other
 */
@Serializable
data class ClaimDto(
    @SerialName("claim_id") val claimId: String,
    val period: String,
    @SerialName("claimed_amount") val claimedAmount: Money,
    @SerialName("approved_amount") val approvedAmount: Money? = null,
    val status: String,
    @SerialName("shortfall_disposition") val shortfallDisposition: String? = null,
    val channel: String,
    @SerialName("submitted_at") val submittedAt: String,
    @SerialName("verified_at") val verifiedAt: String? = null,
    @SerialName("previous_decision") val previousDecision: Map<String, String?>? = null,
)

/**
 * What the claimant needs in order to pay.
 *
 * **The whole object is absent where the teacher set no number**
 * [NFR14.34] — the route returns null rather than this with a null
 * inside it, so the screen omits the destination step entirely and the
 * copy tells the person to ask the teacher. A null field would invite
 * a client-side placeholder instead.
 *
 * @property collectionNumber Where payments are sent
 * @property collectionChannel Which service that number belongs to
 * @property channels The channel set, **server-supplied** [BR6.5].
 *
 *   A `List<String>` rendered as labels, deliberately **not** a sealed
 *   type with a branch per channel. The sealed type is the idiomatic
 *   Kotlin choice and it is the wrong one here: adding a channel
 *   server-side would then require an app release, and an installed
 *   Android app cannot be forced to update
 */
@Serializable
data class PaymentDestinationDto(
    @SerialName("collection_number") val collectionNumber: String,
    @SerialName("collection_channel") val collectionChannel: String? = null,
    val channels: List<String> = emptyList(),
)

/**
 * A claim being submitted.
 *
 * @property claimedAmount What the claimant says they paid, as a
 *   [Money] so it is serialized as a JSON **string** outbound too —
 *   the rule is both directions, not only inbound [BR6.2]
 * @property channel Which service it moved through, from the set the
 *   destination response supplied
 * @property transactionId The reference they quote, if any
 */
@Serializable
data class ClaimSubmitDto(
    @SerialName("claimed_amount") val claimedAmount: Money,
    val channel: String,
    @SerialName("transaction_id") val transactionId: String? = null,
)
