package com.shikkhokplus.app.feature.today

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.TodayClassDto
import com.shikkhokplus.app.core.network.TodayDto
import com.shikkhokplus.app.feature.verify.VerifyStateMapper

/**
 * Maps the Today read to what T1 renders. Every figure and every
 * "next" is the server's [TC-9, D-31].
 */
object TodayStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** `HH:MM` out of the server's `HH:MM:SS`. */
    private const val HHMM = 5

    private val STATUSES: Map<String, ClassStatus> =
        mapOf("scheduled" to ClassStatus.SCHEDULED, "held" to ClassStatus.HELD, "cancelled" to ClassStatus.CANCELLED)

    /**
     * Map the day.
     *
     * @param dto What the server returned
     * @return The state T1 renders
     */
    fun afterLoad(dto: TodayDto): TodayUiState {
        if (!dto.hasBatches) return TodayUiState.FirstRun(dto.date)
        val classes = dto.classes.map { toRow(it) ?: return unexpected() }
        val toVerify = dto.toVerify.map { VerifyStateMapper.toCard(it) ?: return unexpected() }
        val owed = dto.outstanding
        return TodayUiState.Loaded(
            date = dto.date,
            owed =
                OwedSummary(
                    total = owed.total,
                    overdue = owed.overdue,
                    overdueStudents = owed.overdueStudents,
                    batchCount = owed.batchCount,
                    showOverdue = owed.overdueStudents > 0,
                ),
            classes = classes,
            toVerifyCount = dto.toVerifyCount,
            toVerify = toVerify,
        )
    }

    /**
     * Map a refusal.
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): TodayUiState =
        TodayUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a read that never reached the server.
     *
     * @return The offline failure
     */
    fun afterTransportFailure(): TodayUiState = TodayUiState.Failed(OFFLINE_KEY, retryable = true)

    /** @return The state for a response outside the known values. */
    private fun unexpected(): TodayUiState = TodayUiState.Failed(UNEXPECTED_KEY, retryable = false)

    /**
     * Convert one class.
     *
     * @param dto The class
     * @return The row, or null for an unknown status
     */
    private fun toRow(dto: TodayClassDto): ClassRow? =
        STATUSES[dto.status]?.let { status ->
            ClassRow(
                sessionId = dto.sessionId,
                batchId = dto.batchId,
                batchName = dto.batchName,
                subjectName = dto.subjectName,
                startTime = dto.startTime.take(HHMM),
                topicVersion = dto.topicVersion,
                status = status,
                // A topic saved blank is logged with nothing to show [BR2.2].
                topic = dto.topic?.takeIf { dto.topicLogged && it.isNotBlank() },
                isNext = dto.isNext,
                startsInMinutes = dto.startsInMinutes,
                examId = dto.examId,
                examTitle = dto.examTitle,
            )
        }
}
