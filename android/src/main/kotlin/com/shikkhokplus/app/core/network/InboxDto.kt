package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One message in the reader's own inbox.
 *
 * @property notificationId The message
 * @property kind What produced it; `fee_reminder` today
 * @property enrollmentId The seat it is about, if any
 * @property batchName The batch, as named when it was sent
 * @property period The period it concerns, as `YYYY-MM`, if any
 * @property amount What is owed, as the server computed it, if any
 * @property createdAt When it was sent
 * @property read Whether the reader has opened this message
 * @property sourceId The record that produced it, if any
 * @property childName Which child it is about, on a guardian's copy
 * @property preview A short line of its content, if any
 */
@Serializable
data class NotificationDto(
    @SerialName("notification_id") val notificationId: String,
    val kind: String,
    @SerialName("enrollment_id") val enrollmentId: String? = null,
    @SerialName("batch_name") val batchName: String,
    val period: String? = null,
    val amount: Money? = null,
    @SerialName("created_at") val createdAt: String,
    val read: Boolean,
    @SerialName("source_id") val sourceId: String? = null,
    @SerialName("child_name") val childName: String? = null,
    val preview: String? = null,
)

/**
 * A notice, as the teacher wrote it.
 *
 * @property body The teacher's words
 * @property postedAt When it was posted
 * @property editedAt When it was last edited, if it was
 */
@Serializable
data class NoticeBlockDto(
    val body: String,
    @SerialName("posted_at") val postedAt: String,
    @SerialName("edited_at") val editedAt: String? = null,
)

/**
 * An exam, as it stands now.
 *
 * @property examId The exam
 * @property title Its title
 * @property date The day, as `YYYY-MM-DD`
 * @property subjectName The subject
 * @property totalMarks The marks it is out of
 * @property topics What it covers, in the teacher's words
 * @property cancelled Whether the teacher has cancelled it; absent from
 *   a server older than cancelling, which reads as not cancelled
 */
@Serializable
data class ExamBlockDto(
    @SerialName("exam_id") val examId: String,
    val title: String,
    val date: String,
    @SerialName("subject_name") val subjectName: String,
    @SerialName("total_marks") val totalMarks: Int,
    val topics: List<String> = emptyList(),
    val cancelled: Boolean = false,
)

/**
 * A payment and how it was decided.
 *
 * @property claimId The claim
 * @property period The period, as `YYYY-MM`
 * @property claimed What was claimed
 * @property approved What the teacher accepted, if decided
 * @property outcome `approved`, `partial`, `rejected` or `pending`
 * @property reason The teacher's reason, if given
 */
@Serializable
data class PaymentBlockDto(
    @SerialName("claim_id") val claimId: String,
    val period: String,
    val claimed: Money,
    val approved: Money? = null,
    val outcome: String,
    val reason: String? = null,
)

/**
 * One message and what it opens to, as its source stands now.
 *
 * @property notificationId The message
 * @property kind What produced it
 * @property enrollmentId The seat it is about, if any
 * @property batchName The batch
 * @property period The period it concerns, if any
 * @property amount The money it concerns, if any
 * @property createdAt When it was sent
 * @property read Whether the reader has opened it
 * @property sourceId The record that produced it, if any
 * @property childName Which child it is about, if a guardian's copy
 * @property preview A short line of its content, if any
 * @property available False once the source is gone or the seat unreachable
 * @property notice Set for an available notice
 * @property exam Set for an available exam
 * @property payment Set for an available payment result
 */
@Serializable
data class NotificationDetailDto(
    @SerialName("notification_id") val notificationId: String,
    val kind: String,
    @SerialName("enrollment_id") val enrollmentId: String? = null,
    @SerialName("batch_name") val batchName: String,
    val period: String? = null,
    val amount: Money? = null,
    @SerialName("created_at") val createdAt: String,
    val read: Boolean,
    @SerialName("source_id") val sourceId: String? = null,
    @SerialName("child_name") val childName: String? = null,
    val preview: String? = null,
    val available: Boolean = true,
    val notice: NoticeBlockDto? = null,
    val exam: ExamBlockDto? = null,
    val payment: PaymentBlockDto? = null,
)

/**
 * The reader's inbox, newest first.
 *
 * @property items The messages
 * @property unread How many have not been seen, for the bell's badge
 */
@Serializable
data class InboxDto(
    val items: List<NotificationDto> = emptyList(),
    val unread: Int,
)
