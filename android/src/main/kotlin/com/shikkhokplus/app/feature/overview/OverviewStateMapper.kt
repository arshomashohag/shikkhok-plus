package com.shikkhokplus.app.feature.overview

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MonthlyEarningsDto
import com.shikkhokplus.app.core.network.NextExamDto
import com.shikkhokplus.app.core.network.OverviewDto

/**
 * Maps the overview response to an [OverviewUiState].
 *
 * **The three absences are decided here and nowhere else.** Whether to
 * show the trend block at all, and whether the next-exam block is a
 * figure or an empty state, are the only questions this screen has —
 * and answering them in a composable would put a `when` over a domain
 * value where nothing tests it [TC-9, D-31].
 *
 * **Null is carried through, never converted to a zero or an empty
 * list.** That is the single most important property of this mapper: a
 * `trend ?: emptyList()` would turn "the server has under two months of
 * history" into "the server sent an empty series", and the screen would
 * then draw an empty chart frame instead of omitting the block.
 */
object OverviewStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map a loaded overview.
     *
     * @param dto The overview the server returned
     * @return The state the screen renders
     */
    fun afterLoad(dto: OverviewDto): OverviewUiState =
        OverviewUiState.Loaded(
            // Non-null on both sides. A zero month arrives as "0.00"
            // and stays a figure.
            thisMonth = toPoint(dto.earnings),
            // **`?.map`, never `.orEmpty().map`.** The nullability IS
            // the contract: null means under two months of history and
            // an empty list would mean the server had two months that
            // both earned nothing, which is a different screen.
            trend = dto.trend?.map(::toPoint),
            nextExam = dto.nextExam?.let(::toExam),
        )

    /**
     * Convert one month of the series.
     *
     * @param dto The month the server returned
     * @return The point the screen renders
     */
    private fun toPoint(dto: MonthlyEarningsDto): EarningsPoint =
        EarningsPoint(period = dto.period, received = dto.received)

    /**
     * Convert the next exam.
     *
     * `daysRemaining` is carried, not recomputed from [NextExamDto.date].
     *
     * @param dto The exam the server returned
     * @return The block the screen renders
     */
    private fun toExam(dto: NextExamDto): NextExam =
        NextExam(
            title = dto.title,
            batchName = dto.batchName,
            subjectName = dto.subjectName,
            date = dto.date,
            daysRemaining = dto.daysRemaining,
        )

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): OverviewUiState =
        OverviewUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): OverviewUiState =
        OverviewUiState.Failed(OFFLINE_KEY, retryable = true)
}
