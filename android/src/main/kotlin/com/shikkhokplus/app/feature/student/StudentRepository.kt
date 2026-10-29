package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the student screens read. */
interface StudentRepository {
    /**
     * List the batches this student has accepted a seat in (S1).
     *
     * @return The batches, a refusal, or a transport failure
     */
    suspend fun batches(): AuthResult<List<StudentBatchDto>>

    /**
     * Read the signed-in account, for the number S1's empty state
     * shows: the one a teacher adds the student by.
     *
     * @return The account, a refusal, or a transport failure
     */
    suspend fun phone(): AuthResult<MeDto>

    /**
     * Read one batch from the student's side: next class, past
     * classes, notices (S2).
     *
     * @param enrollmentId The student's own seat
     * @return The view, a refusal, or a transport failure
     */
    suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto>

    /**
     * Read the student's own results in one batch, in date order.
     *
     * @param enrollmentId The student's own seat
     * @return The series, a refusal, or a transport failure
     */
    suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>>
}
