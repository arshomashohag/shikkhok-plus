package com.shikkhokplus.app.feature.students

import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.StudentSeatDto
import com.shikkhokplus.app.core.network.TeacherStudentDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * Response-to-state mapping for the students screens. Pure functions, so
 * each decision is tested without a ViewModel.
 *
 * **Decides nothing about the domain** [TC-9]: which seats are active,
 * which may be deleted and what is owed all arrive from the server and
 * are carried through unchanged.
 */
object StudentsStateMapper {
    /** The key used when no response arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The server's status for a seat the student is still in. */
    private const val ACTIVE = "active"

    /**
     * The list's state after a load.
     *
     * @param students What the server returned
     * @param filtered Whether a filter or search narrowed it
     * @return Loaded with rows, or Empty
     */
    fun afterLoad(students: List<TeacherStudentDto>, filtered: Boolean): StudentsUiState =
        if (students.isEmpty()) {
            StudentsUiState.Empty(filtered = filtered)
        } else {
            StudentsUiState.Loaded(
                students.map { dto ->
                    StudentListRow(
                        id = dto.studentId,
                        name = dto.displayName,
                        phone = dto.studentPhone,
                        batchNames = dto.enrollments.map(StudentSeatDto::batchName),
                    )
                },
            )
        }

    /**
     * The list's state after a refusal.
     *
     * @param envelope The server's error
     * @return Failed, with the server's own retryable flag
     */
    fun afterError(envelope: ErrorEnvelope): StudentsUiState =
        StudentsUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Batches as filter chips and picker choices.
     *
     * @param batches What the server returned
     * @return One option per batch, in the server's order
     */
    fun options(batches: List<BatchDto>): List<BatchOption> =
        batches.map { BatchOption(id = it.id, name = it.name, defaultFee = it.defaultFee) }

    /**
     * One student in full, with the batches they could still join.
     *
     * @param dto The student
     * @param batches Every batch the teacher has
     * @return The detail
     */
    fun detail(dto: TeacherStudentDto, batches: List<BatchOption>): StudentDetail {
        val seated = dto.enrollments.map(StudentSeatDto::batchId).toSet()
        return StudentDetail(
            id = dto.studentId,
            name = dto.displayName,
            studentPhone = dto.studentPhone,
            guardianPhone = dto.guardianPhone,
            studentState = dto.studentState,
            guardianState = dto.guardianState,
            seats =
                dto.enrollments.map { seat ->
                    SeatLine(
                        enrollmentId = seat.enrollmentId,
                        batchName = seat.batchName,
                        fee = seat.feeAmount,
                        outstanding = seat.outstanding,
                        active = seat.status == ACTIVE,
                        removable = seat.isRemovable,
                    )
                },
            totalOutstanding = dto.totalOutstanding,
            removable = dto.isRemovable,
            otherBatches = batches.filterNot { it.id in seated },
        )
    }

    /**
     * A write's outcome as the form shows it.
     *
     * @param result What the write returned
     * @return Saved, or Failed with the server's key and flag
     */
    fun <T> written(result: AuthResult<T>): WriteState =
        when (result) {
            is AuthResult.Ok -> WriteState.Saved
            is AuthResult.Refused ->
                WriteState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> WriteState.Failed(OFFLINE_KEY, retryable = true)
        }
}
