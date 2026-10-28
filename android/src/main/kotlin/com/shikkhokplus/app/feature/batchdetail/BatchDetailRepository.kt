package com.shikkhokplus.app.feature.batchdetail

import com.shikkhokplus.app.core.network.AnnouncementDto
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.BatchEdit
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the batch screen (T7) reads and writes beyond the roster. */
interface BatchDetailRepository {
    /**
     * Read one batch's summary: fee, due day, schedule, subjects.
     *
     * @param batchId The batch
     * @return The batch, a refusal, or a transport failure
     */
    suspend fun batch(batchId: String): AuthResult<BatchDto>

    /**
     * Edit the batch's name, subjects, fee or due day.
     *
     * @param batchId The batch
     * @param edit What changes
     * @return The batch as it now stands, a refusal, or a transport failure
     */
    suspend fun editBatch(batchId: String, edit: BatchEdit): AuthResult<BatchDto>

    /**
     * Read each seat's fee position, for the Students tab's chips.
     *
     * @param batchId The batch
     * @return One row per seat, a refusal, or a transport failure
     */
    suspend fun fees(batchId: String): AuthResult<List<RosterFeeRowDto>>

    /**
     * Read the batch's notices, newest first.
     *
     * @param batchId The batch
     * @return The notices, a refusal, or a transport failure
     */
    suspend fun notices(batchId: String): AuthResult<List<AnnouncementDto>>

    /**
     * Post a notice to the batch.
     *
     * @param batchId The batch
     * @param body The text
     * @return Nothing on success, or why the server refused
     */
    suspend fun postNotice(batchId: String, body: String): AuthResult<Unit>

    /**
     * Change a notice's text.
     *
     * @param noticeId The notice
     * @param body The new text
     * @return Nothing on success, or why the server refused
     */
    suspend fun editNotice(noticeId: String, body: String): AuthResult<Unit>

    /**
     * Take a notice down.
     *
     * @param noticeId The notice
     * @return Nothing on success, or why the server refused
     */
    suspend fun removeNotice(noticeId: String): AuthResult<Unit>
}
