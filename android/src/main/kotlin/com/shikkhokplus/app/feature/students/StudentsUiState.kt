package com.shikkhokplus.app.feature.students

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.StudentSeatBody
import com.shikkhokplus.app.core.network.TeacherStudentDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the students repository must provide [0018]. */
interface StudentsRepository {
    /**
     * List the teacher's students, filtered by the SERVER.
     *
     * @param filter Which students
     * @param query Search text, blank for none
     * @return The students, a refusal, or a transport failure
     */
    suspend fun students(filter: StudentFilter, query: String): AuthResult<List<TeacherStudentDto>>

    /**
     * Read one student.
     *
     * @param studentId The student
     * @return The student, a refusal, or a transport failure
     */
    suspend fun student(studentId: String): AuthResult<TeacherStudentDto>

    /**
     * The teacher's batches, for the filter chips and the batch picker.
     *
     * @return The batches, a refusal, or a transport failure
     */
    suspend fun batches(): AuthResult<List<BatchDto>>

    /**
     * Record a student, optionally seating them in batches.
     *
     * @param displayName The typed name
     * @param studentPhone The typed student number, or null
     * @param guardianPhone The typed guardian number, or null
     * @param seats The batches to put them in, possibly none
     * @return The new student, a refusal, or a transport failure
     */
    suspend fun create(
        displayName: String,
        studentPhone: String?,
        guardianPhone: String?,
        seats: List<StudentSeatBody>,
    ): AuthResult<TeacherStudentDto>

    /**
     * Edit a student. A null value is left as it is.
     *
     * @param studentId The student
     * @param displayName The new name, or null
     * @param studentPhone The new student number, or null
     * @param guardianPhone The new guardian number, or null
     * @return The edited student, a refusal, or a transport failure
     */
    suspend fun rename(
        studentId: String,
        displayName: String?,
        studentPhone: String?,
        guardianPhone: String?,
    ): AuthResult<TeacherStudentDto>

    /**
     * Put a student in one more batch, at that batch's fee.
     *
     * @param studentId The student
     * @param batchId The batch
     * @return The student, a refusal, or a transport failure
     */
    suspend fun enroll(studentId: String, batchId: String): AuthResult<TeacherStudentDto>

    /**
     * Seat existing students in one batch, all or nothing.
     *
     * @param batchId The batch
     * @param studentIds The students
     * @return Ok, a refusal, or a transport failure
     */
    suspend fun addToBatch(batchId: String, studentIds: List<String>): AuthResult<Unit>

    /**
     * Mark a seat inactive from a date: the student left that batch.
     *
     * @param enrollmentId The seat
     * @param onDate The ISO date
     * @return Ok, a refusal, or a transport failure
     */
    suspend fun leaveBatch(enrollmentId: String, onDate: String): AuthResult<Unit>

    /**
     * Delete a seat nobody accepted.
     *
     * @param enrollmentId The seat
     * @return Ok, a refusal, or a transport failure
     */
    suspend fun removeSeat(enrollmentId: String): AuthResult<Unit>

    /**
     * Remove a student in no active batch who owes nothing.
     *
     * @param studentId The student
     * @return Ok, a refusal, or a transport failure
     */
    suspend fun removeStudent(studentId: String): AuthResult<Unit>
}

/** Which of the teacher's students to list. Applied by the server. */
sealed interface StudentFilter {
    /** Every student. */
    data object All : StudentFilter

    /** Students in no batch at all. */
    data object Unassigned : StudentFilter

    /**
     * Students with a seat in one batch.
     *
     * @property batchId The batch
     */
    data class InBatch(val batchId: String) : StudentFilter

    /**
     * Students WITHOUT a seat in one batch, for the roster's picker.
     *
     * @property batchId The batch
     */
    data class NotInBatch(val batchId: String) : StudentFilter
}

/**
 * A batch, as a filter chip or a choice in the batch picker.
 *
 * @property id The batch
 * @property name Its name
 * @property defaultFee Its fee, for "Batch fee · ৳1,200"
 */
data class BatchOption(
    val id: String,
    val name: String,
    val defaultFee: Money?,
)

/**
 * One student as the list draws it.
 *
 * @property id The student
 * @property name The teacher-typed name
 * @property phone The student's number, or null
 * @property batchNames The batches they sit in, by name; empty for none
 */
data class StudentListRow(
    val id: String,
    val name: String,
    val phone: String?,
    val batchNames: List<String>,
)

/**
 * Everything the Students tab renders. The four states every list
 * screen keeps: loading, loaded, empty and failed with its retry.
 */
sealed interface StudentsUiState {
    /** A request is in flight. */
    data object Loading : StudentsUiState

    /**
     * The list loaded with at least one student.
     *
     * @property rows The students, in the server's order
     */
    data class Loaded(val rows: List<StudentListRow>) : StudentsUiState

    /**
     * Nothing matched.
     *
     * @property filtered Whether a filter or search is narrowing the
     *   list, so the screen can say "no match" rather than "no students"
     */
    data class Empty(val filtered: Boolean) : StudentsUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : StudentsUiState
}

/**
 * One seat on the student detail screen.
 *
 * @property enrollmentId The seat
 * @property batchName Its batch
 * @property fee What it charges, or null when unset
 * @property outstanding What it owes now
 * @property active Whether the student is still in this batch
 * @property removable Whether the seat may be deleted outright
 */
data class SeatLine(
    val enrollmentId: String,
    val batchName: String,
    val fee: Money?,
    val outstanding: Money,
    val active: Boolean,
    val removable: Boolean,
)

/**
 * One student in full.
 *
 * @property id The student
 * @property name The teacher-typed name
 * @property studentPhone The student's number, or null
 * @property guardianPhone The guardian's number, or null
 * @property studentState `pending`, `accepted` or `declined`
 * @property guardianState The same, or `absent`
 * @property seats The seats, possibly none
 * @property totalOutstanding What they owe across every seat
 * @property removable Whether removing the student would succeed
 * @property otherBatches Batches they are not in yet, to add them to
 */
data class StudentDetail(
    val id: String,
    val name: String,
    val studentPhone: String?,
    val guardianPhone: String?,
    val studentState: String,
    val guardianState: String,
    val seats: List<SeatLine>,
    val totalOutstanding: Money,
    val removable: Boolean,
    val otherBatches: List<BatchOption>,
)

/** Everything the student detail screen renders. */
sealed interface StudentDetailUiState {
    /** A request is in flight. */
    data object Loading : StudentDetailUiState

    /**
     * The student loaded.
     *
     * @property student The student
     */
    data class Loaded(val student: StudentDetail) : StudentDetailUiState

    /** The student was removed; the screen closes. */
    data object Removed : StudentDetailUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : StudentDetailUiState
}
