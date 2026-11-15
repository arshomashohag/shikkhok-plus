package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.EmailEdit
import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.buildClassSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonEncoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

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
 * @property studentEmail The student's address as the teacher typed it,
 *   lowercased by the server, or null [FR6.1]. Teacher-written, never an
 *   account's own
 * @property guardianEmail The guardian's address, likewise
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
    @SerialName("student_email") val studentEmail: String? = null,
    @SerialName("guardian_email") val guardianEmail: String? = null,
) {
    // Someone else's contacts, typed by a teacher [NFR3.2].
    override fun toString(): String =
        "TeacherStudentDto(studentId=$studentId, studentState=$studentState, guardianState=$guardianState, " +
            "seats=${enrollments.size}, studentPhone=***, guardianPhone=***, studentEmail=***, guardianEmail=***)"
}

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
 * The add-student body. Numbers and addresses are sent as typed (the
 * addresses trimmed); the server canonicalises them. A blank contact is
 * null, and so left out of the body.
 */
@Serializable
internal data class StudentCreateBody(
    @SerialName("display_name") val displayName: String,
    @SerialName("student_phone") val studentPhone: String? = null,
    @SerialName("guardian_phone") val guardianPhone: String? = null,
    val enrollments: List<StudentSeatBody> = emptyList(),
    @SerialName("client_mutation_id") val clientMutationId: String? = null,
    @SerialName("student_email") val studentEmail: String? = null,
    @SerialName("guardian_email") val guardianEmail: String? = null,
) {
    override fun toString(): String =
        "StudentCreateBody(seats=${enrollments.size}, studentPhone=***, guardianPhone=***, " +
            "studentEmail=***, guardianEmail=***)"
}

/**
 * The edit body.
 *
 * **Two encodings in one body, on purpose** [W7.5, C2]. A null name or
 * phone is omitted by the client's JSON settings, which the server reads
 * as "unchanged" -- today's rule for those fields, kept. An email is an
 * [EmailEdit], which can also say "clear": that is sent as an explicit
 * JSON `null`, which `explicitNulls = false` would otherwise drop. So
 * this body is written by [StudentUpdateBodySerializer], field by field.
 *
 * @property displayName The new name, or null to leave it
 * @property studentPhone The new student number, or null to leave it
 * @property guardianPhone The new guardian number, or null to leave it
 * @property studentEmail What to do with the student's address
 * @property guardianEmail What to do with the guardian's address
 */
@Serializable(with = StudentUpdateBodySerializer::class)
internal data class StudentUpdateBody(
    val displayName: String? = null,
    val studentPhone: String? = null,
    val guardianPhone: String? = null,
    val studentEmail: EmailEdit = EmailEdit.Unchanged,
    val guardianEmail: EmailEdit = EmailEdit.Unchanged,
) {
    override fun toString(): String =
        "StudentUpdateBody(studentPhone=***, guardianPhone=***, studentEmail=$studentEmail, " +
            "guardianEmail=$guardianEmail)"
}

/**
 * Writes [StudentUpdateBody]: omitted, a value, or JSON `null` per field.
 *
 * Write-only; the server never sends this shape back.
 */
internal object StudentUpdateBodySerializer : KSerializer<StudentUpdateBody> {
    override val descriptor: SerialDescriptor = buildClassSerialDescriptor("StudentUpdateBody")

    override fun serialize(encoder: Encoder, value: StudentUpdateBody) {
        val json =
            encoder as? JsonEncoder
                ?: throw SerializationException("StudentUpdateBody is written as JSON only")
        json.encodeJsonElement(
            buildJsonObject {
                value.displayName?.let { put("display_name", it) }
                value.studentPhone?.let { put("student_phone", it) }
                value.guardianPhone?.let { put("guardian_phone", it) }
                putEdit("student_email", value.studentEmail)
                putEdit("guardian_email", value.guardianEmail)
            },
        )
    }

    override fun deserialize(decoder: Decoder): StudentUpdateBody =
        throw SerializationException("StudentUpdateBody is never read")

    private fun JsonObjectBuilder.putEdit(name: String, edit: EmailEdit) {
        when (edit) {
            EmailEdit.Unchanged -> Unit
            is EmailEdit.Set -> put(name, edit.address.trim())
            EmailEdit.Clear -> put(name, JsonNull)
        }
    }
}

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
