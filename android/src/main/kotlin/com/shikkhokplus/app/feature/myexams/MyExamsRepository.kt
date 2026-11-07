package com.shikkhokplus.app.feature.myexams

import com.shikkhokplus.app.core.network.ExamExaminerDto
import com.shikkhokplus.app.core.network.ExaminerResultsDto
import com.shikkhokplus.app.core.network.MarkWriteBody
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MyExamDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What an examiner's screens need from the network. */
interface MyExamsRepository {
    /**
     * Read the exams I mark, across every centre.
     *
     * @return The exams, a refusal, or a transport failure
     */
    suspend fun exams(): AuthResult<List<MyExamDto>>

    /**
     * Read one exam's results.
     *
     * @param examId The exam
     * @return The exam and its results, a refusal, or a transport failure
     */
    suspend fun results(examId: String): AuthResult<ExaminerResultsDto>

    /**
     * Record one seat's mark or absence.
     *
     * @param examId The exam
     * @param body The seat and its result
     * @return Done, a refusal, or a transport failure
     */
    suspend fun mark(examId: String, body: MarkWriteBody): AuthResult<Unit>

    /**
     * Publish the results.
     *
     * @param examId The exam
     * @return Done, a refusal (an incomplete sheet), or a transport failure
     */
    suspend fun publish(examId: String): AuthResult<Unit>
}

/** What naming an exam's examiner needs from the network. */
interface ExaminerRepository {
    /**
     * Read who marks an exam.
     *
     * @param examId The exam
     * @return The exam's examiner, a refusal, or a transport failure
     */
    suspend fun exam(examId: String): AuthResult<ExamExaminerDto>

    /**
     * Read the centre's members, for the picker.
     *
     * @return The members, a refusal, or a transport failure
     */
    suspend fun members(): AuthResult<List<MemberDto>>

    /**
     * Name an exam's examiner.
     *
     * @param examId The exam
     * @param memberId A live member, or null for nobody
     * @return The exam's examiner now, a refusal, or a transport failure
     */
    suspend fun setExaminer(examId: String, memberId: String?): AuthResult<ExamExaminerDto>
}
