package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One of a student's seats, as the teacher reads it on the student.
 *
 * Every amount is a [Money] decoded from a JSON string [TC-7]. Whether
 * the seat is active, and whether it may be deleted, are the SERVER's
 * decisions; the client renders them and compares nothing [TC-9].
 *
 * @property enrollmentId The seat, which fees, attendance and marks use
 * @property batchId Its batch
 * @property batchName That batch's name
 * @property feeAmount What the seat is charged, or null when unset
 * @property status `active`, or `inactive` once the student left
 * @property inactiveFrom The date they left, if they did
 * @property outstanding What this seat owes now
 * @property isRemovable Whether the seat itself can be deleted
 */
@Serializable
data class StudentSeatDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("batch_id") val batchId: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("fee_amount") val feeAmount: Money? = null,
    val status: String,
    @SerialName("inactive_from") val inactiveFrom: String? = null,
    val outstanding: Money,
    @SerialName("is_removable") val isRemovable: Boolean,
)

/**
 * One of the teacher's students, with every seat they hold [0018].
 *
 * Teacher-authored fields only: the name and numbers the teacher typed,
 * never a student's own profile [TC-13].
 *
 * @property studentId The teacher's record of this student
 * @property displayName The teacher-typed name
 * @property studentPhone The student's number, as typed
 * @property guardianPhone The guardian's number, as typed
 * @property studentState `pending`, `accepted` or `declined`
 * @property guardianState The same, or `absent`
 * @property enrollments The seats, possibly none
 * @property totalOutstanding What the student owes across every seat
 * @property isRemovable Whether removing the student would succeed
 */
@Serializable
data class TeacherStudentDto(
    @SerialName("student_id") val studentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("student_phone") val studentPhone: String? = null,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    @SerialName("student_state") val studentState: String,
    @SerialName("guardian_state") val guardianState: String,
    val enrollments: List<StudentSeatDto> = emptyList(),
    @SerialName("total_outstanding") val totalOutstanding: Money,
    @SerialName("is_removable") val isRemovable: Boolean,
)

/**
 * One batch to put a new student in.
 *
 * @property batchId The batch
 * @property feeAmount A canonical money STRING, or null to inherit [TC-7]
 */
@Serializable
data class StudentSeatBody(
    @SerialName("batch_id") val batchId: String,
    @SerialName("fee_amount") val feeAmount: String? = null,
)

/**
 * The add-student body. Numbers are sent as typed; the server
 * canonicalises them.
 */
@Serializable
internal data class StudentCreateBody(
    @SerialName("display_name") val displayName: String,
    @SerialName("student_phone") val studentPhone: String? = null,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    val enrollments: List<StudentSeatBody> = emptyList(),
)

/**
 * The edit body. A null field is omitted by the client's JSON settings,
 * which the server reads as "unchanged".
 */
@Serializable
internal data class StudentUpdateBody(
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("student_phone") val studentPhone: String? = null,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
)

/** The add-to-one-more-batch body. */
@Serializable
internal data class StudentEnrollBody(
    @SerialName("batch_id") val batchId: String,
    @SerialName("fee_amount") val feeAmount: String? = null,
)

/** The roster picker's body: existing students into one batch. */
@Serializable
internal data class AddStudentsBody(
    @SerialName("student_ids") val studentIds: List<String>,
)

/** The leave-batch body: the date the seat goes inactive from. */
@Serializable
internal data class LeaveBatchBody(
    @SerialName("inactive_from") val inactiveFrom: String,
)
