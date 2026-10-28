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
 * What students owe across every batch, and how much is late (T1).
 *
 * **[overdue] is the server's decision** — owing on a period past its
 * due date in Bangladesh. The client never compares a date itself.
 *
 * @property total Everything still owed
 * @property overdue The part owed on periods past their due date
 * @property overdueStudents Seats with anything overdue
 * @property batchCount Batches with anything owing
 */
@Serializable
data class OutstandingDto(
    val total: Money,
    val overdue: Money,
    @SerialName("overdue_students") val overdueStudents: Int,
    @SerialName("batch_count") val batchCount: Int,
)

/**
 * One class today (T1).
 *
 * @property sessionId The class
 * @property batchId Its batch
 * @property batchName The batch's name
 * @property subjectName The subject, where set
 * @property startTime When it starts, `HH:MM:SS`
 * @property endTime When it ends, where set
 * @property status `scheduled`, `held` or `cancelled`
 * @property topic The logged topic, where written
 * @property topicLogged Whether a topic was written at all [BR2.2]
 * @property attendanceVersion The version a roster write composes against
 * @property topicVersion The version a topic write composes against
 * @property isNext The first class still to start, decided by the server
 * @property startsInMinutes Minutes until it starts, by the server's clock
 * @property examId An exam this batch sits today
 * @property examTitle That exam's title
 */
@Serializable
data class TodayClassDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subject_name") val subjectName: String? = null,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String? = null,
    val status: String,
    val topic: String? = null,
    @SerialName("topic_logged") val topicLogged: Boolean,
    @SerialName("attendance_version") val attendanceVersion: Int,
    @SerialName("topic_version") val topicVersion: Int,
    @SerialName("is_next") val isNext: Boolean,
    @SerialName("starts_in_minutes") val startsInMinutes: Int? = null,
    @SerialName("exam_id") val examId: String? = null,
    @SerialName("exam_title") val examTitle: String? = null,
)

/**
 * The teacher's Today screen in one read (T1).
 *
 * @property date Today in Bangladesh, `YYYY-MM-DD`
 * @property outstanding Money owed and overdue
 * @property classes Today's classes, by start time
 * @property toVerifyCount How many payments wait to be checked
 * @property toVerify The first few of them
 * @property hasBatches Whether the teacher has made a batch yet
 */
@Serializable
data class TodayDto(
    val date: String,
    val outstanding: OutstandingDto,
    val classes: List<TodayClassDto> = emptyList(),
    @SerialName("to_verify_count") val toVerifyCount: Int,
    @SerialName("to_verify") val toVerify: List<ClaimQueueItemDto> = emptyList(),
    @SerialName("has_batches") val hasBatches: Boolean,
)
