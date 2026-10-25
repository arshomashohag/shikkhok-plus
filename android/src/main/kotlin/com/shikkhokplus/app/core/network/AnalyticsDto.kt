package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One person who owes this teacher money, in one batch.
 *
 * **`outstanding` is a [Money]**, so a JSON number fails to decode
 * rather than being quietly converted to a double [TC-7, D-20]. That
 * lenient conversion is the real failure mode and it passes a
 * happy-path test on both sides.
 *
 * **There is no `isOverdue`, no status and no badge field, and that is
 * the point.** Membership in this list IS the decision: the server put
 * the row here because the seat owes money, so a client comparing
 * `outstanding > 0` would be reimplementing the dues membership rule
 * where nothing tests it [TC-9, D-31].
 *
 * @property enrollmentId The teacher-facing key, never an account id
 * @property batchId The batch the debt sits in
 * @property batchName That batch's name, carried because the same
 *   person may owe in two and a row without it is ambiguous
 * @property displayName The teacher-typed name
 * @property outstanding What this seat still owes across every period
 * @property oldestUnpaidPeriod Which period the debt starts in as
 *   `YYYY-MM`, or null. **Computed server-side** from the same fold
 *   the balance comes from
 */
@Serializable
data class DuesRowDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("display_name") val displayName: String,
    val outstanding: Money,
    @SerialName("oldest_unpaid_period") val oldestUnpaidPeriod: String? = null,
)

/**
 * Everyone who owes this teacher money, across every batch.
 *
 * A wrapper rather than a bare array, matching the server's own
 * response model: an empty `rows` is the defined empty state and is
 * never an error, so the screen shows "nobody owes anything" rather
 * than a retry prompt for the best possible news.
 *
 * @property rows One entry per owing seat, **already ordered** largest
 *   debt first. The client renders the order it is given; sorting a
 *   domain list here would be the second of the five erosion paths
 */
@Serializable
data class DuesResponseDto(
    val rows: List<DuesRowDto> = emptyList(),
)

/**
 * Money received in one calendar month.
 *
 * @property period The month as `YYYY-MM`
 * @property received What arrived that month, as a [Money]
 */
@Serializable
data class MonthlyEarningsDto(
    val period: String,
    val received: Money,
)

/**
 * The soonest exam dated today or later.
 *
 * @property examId The exam
 * @property title The teacher's name for it
 * @property batchName Which class sits it
 * @property subjectName The subject assessed
 * @property date When it is sat, as `YYYY-MM-DD`
 * @property daysRemaining Whole days, **computed server-side**. A
 *   client deriving it from [date] would use the device clock, which
 *   this product rules out for decisions, and would disagree across
 *   time zones
 */
@Serializable
data class NextExamDto(
    @SerialName("exam_id") val examId: String,
    val title: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subject_name") val subjectName: String,
    val date: String,
    @SerialName("days_remaining") val daysRemaining: Int,
)

/**
 * The teacher overview's three blocks.
 *
 * **Two of the three are nullable and one is not, and the asymmetry is
 * the contract rather than an oversight:**
 *
 * - [earnings] is **never absent**. A month with no receipts carries a
 *   zero VALUE, because zero earned is a fact about the month and
 *   rendering it as "no data" would tell a teacher their records are
 *   missing when they are complete;
 * - [trend] is **null under two months of history**, not a one-point
 *   list. A single point implies a direction it cannot know;
 * - [nextExam] is **null when nothing is scheduled**, which the screen
 *   renders as a defined empty state rather than a failure.
 *
 * **Absent and zero are different wire shapes and encoding either as
 * the other is the defect**, which is why [earnings] carries no
 * nullability for a mapper to collapse.
 *
 * @property earnings This month's money received; never absent
 * @property trend The monthly series ascending, or null under two
 *   months
 * @property nextExam The soonest upcoming exam, or null
 */
@Serializable
data class OverviewDto(
    val earnings: MonthlyEarningsDto,
    val trend: List<MonthlyEarningsDto>? = null,
    @SerialName("next_exam") val nextExam: NextExamDto? = null,
)
