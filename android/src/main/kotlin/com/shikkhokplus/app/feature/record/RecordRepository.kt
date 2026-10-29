package com.shikkhokplus.app.feature.record

import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult

/** What recording a class needs from the server (T2). */
interface RecordRepository {
    /**
     * Read a batch's subjects, for the subject picker.
     *
     * @param batchId The batch
     * @return Its subjects, a refusal, or a transport failure
     */
    suspend fun subjects(batchId: String): AuthResult<List<SubjectOptionDto>>

    /**
     * Read a batch's classes, for the "continue where you left off"
     * suggestion.
     *
     * @param batchId The batch
     * @return Its classes, a refusal, or a transport failure
     */
    suspend fun sessions(batchId: String): AuthResult<List<SessionDto>>

    /**
     * Set which subject a class taught. Online only: the server queues
     * topic and attendance writes, not this.
     *
     * @param sessionId The class
     * @param batchSubjectId The subject, or null to clear it
     * @return Nothing on success, or why the server refused
     */
    suspend fun setSubject(sessionId: String, batchSubjectId: String?): AuthResult<Unit>

    /**
     * Send one queued topic write.
     *
     * @param item The write
     * @return Applied, conflicted, or failed
     */
    suspend fun send(item: QueuedWrite): SendOutcome
}
