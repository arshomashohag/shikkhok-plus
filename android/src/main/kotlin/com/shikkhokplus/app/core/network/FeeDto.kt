package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.ClaimOutcome
import com.shikkhokplus.app.core.model.HistoryLine
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
    @SerialName("month_states") val monthStates: List<MonthStateDto> = emptyList(),
)

/**
 * The latest payment claim for one month, as data to localize.
 *
 * Every field is structured: the server sends no English sentence, so
 * the phone words it in the person's language.
 *
 * @property amount What was approved for this child once approved;
 *   otherwise the whole payment as sent, covering [coveredNames]
 * @property channel Which service the money moved through, or `cash`
 * @property paidOn When the money was sent, `YYYY-MM-DD`
 * @property status `pending`, `approved_full`, `approved_partial` or
 *   `rejected`
 * @property decisionNote The teacher's note on the decision, if any
 * @property coveredNames The children the sent amount covered, in the
 *   server's order; empty when [amount] is the child's approved figure
 */
@Serializable
data class HistoryLineDto(
    val amount: Money,
    val channel: String,
    @SerialName("paid_on") val paidOn: String,
    val status: String,
    @SerialName("decision_note") val decisionNote: String? = null,
    @SerialName("covered_names") val coveredNames: List<String> = emptyList(),
)

/**
 * One month on a seat's strip.
 *
 * @property period The month as `YYYY-MM`
 * @property state `paid`, `partly_paid`, `unpaid`, `waived` or
 *   `checking`, decided by the server
 * @property historyLine The latest claim for the month, if any
 */
@Serializable
data class MonthStateDto(
    val period: String,
    val state: String,
    @SerialName("history_line") val historyLine: HistoryLineDto? = null,
)

/**
 * Seats per filter on a batch-month screen, counted by the server.
 *
 * @property paid Seats that are paid
 * @property checking Seats with a payment waiting to be checked
 * @property owed Seats that owe
 */
@Serializable
data class MonthCountsDto(
    val paid: Int,
    val checking: Int,
    val owed: Int,
)

/**
 * One batch in one month (M2).
 *
 * @property period The month as `YYYY-MM`
 * @property collected Cash in for the month after corrections
 * @property charged What the month was billed
 * @property counts Seats per filter, **the server's counts**
 * @property seats One row per seat
 */
@Serializable
data class BatchFeesDto(
    val period: String,
    val collected: Money,
    val charged: Money,
    val counts: MonthCountsDto,
    val seats: List<RosterFeeRowDto> = emptyList(),
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
 * @property state The seat's state in the requested month, or null
 *   when nothing was charged
 * @property historyLine The latest claim for that month, or null
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
    val state: String? = null,
    @SerialName("history_line") val historyLine: HistoryLineDto? = null,
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
 * @property teacherDisplayName Who the money goes to, or null
 */
@Serializable
data class PaymentDestinationDto(
    @SerialName("collection_number") val collectionNumber: String,
    @SerialName("collection_channel") val collectionChannel: String? = null,
    val channels: List<String> = emptyList(),
    @SerialName("teacher_display_name") val teacherDisplayName: String? = null,
)

/**
 * Convert a server history line to data the screen can word.
 *
 * An unknown status reads as pending rather than as a decision the
 * server never made.
 *
 * @return The line
 */
fun HistoryLineDto.toHistoryLine(): HistoryLine =
    HistoryLine(
        amount = amount,
        channel = channel,
        paidOn = paidOn,
        outcome =
            when (status) {
                "approved_full" -> ClaimOutcome.APPROVED_FULL
                "approved_partial" -> ClaimOutcome.APPROVED_PARTIAL
                "rejected" -> ClaimOutcome.REJECTED
                else -> ClaimOutcome.PENDING
            },
        decisionNote = decisionNote,
        coveredNames = coveredNames,
    )

/**
 * One exam or other fee charged to a seat, as the server folded it.
 *
 * @property extraFeeId The fee
 * @property label Its name, as the teacher typed it
 * @property purpose `exam` or `other`
 * @property dueOn When it is due, `yyyy-MM-dd`
 * @property charged What the seat was charged
 * @property paid What has been approved against it
 * @property owed What is still owed on it
 * @property status `paid`, `partly_paid`, `unpaid` or `waived`
 */
@Serializable
data class SeatExtraFeeDto(
    @SerialName("extra_fee_id") val extraFeeId: String,
    @SerialName("label") val label: String,
    @SerialName("purpose") val purpose: String,
    @SerialName("due_on") val dueOn: String,
    @SerialName("charged") val charged: Money,
    @SerialName("paid") val paid: Money,
    @SerialName("owed") val owed: Money,
    @SerialName("status") val status: String,
)

/**
 * The exam and other fees one seat was charged, soonest due first.
 *
 * @property fees One per fee
 */
@Serializable
data class SeatExtraFeesDto(
    @SerialName("fees") val fees: List<SeatExtraFeeDto> = emptyList(),
)
