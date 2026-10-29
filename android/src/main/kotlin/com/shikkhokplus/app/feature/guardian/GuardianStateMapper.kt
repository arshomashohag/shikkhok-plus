package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.network.ChildResultDto
import com.shikkhokplus.app.core.network.ChildSummaryDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.PayableDto
import com.shikkhokplus.app.core.network.UpcomingSessionDto
import com.shikkhokplus.app.feature.pay.PayOption
import com.shikkhokplus.app.feature.student.NextClass

/**
 * Maps the guardian home response to a [GuardianUiState]. Pure: every
 * decision -- what to pay next, how a result trends -- is the server's.
 */
object GuardianStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** `HH:MM` out of `HH:MM:SS`. */
    private const val HHMM = 5

    /**
     * Map a loaded home.
     *
     * @param dto The server's children
     * @param phone The guardian's number, for the empty state
     * @return The state to render
     */
    fun afterLoad(dto: GuardianHomeDto, phone: String?): GuardianUiState =
        if (dto.children.isEmpty()) {
            GuardianUiState.Empty(phone)
        } else {
            GuardianUiState.Loaded(dto.children.map(::toCard))
        }

    /**
     * Show another child, replacing the one shown [BR4.2].
     *
     * @param state The current state
     * @param index The child to show
     * @return The new state; unchanged for an index out of range
     */
    fun select(state: GuardianUiState.Loaded, index: Int): GuardianUiState.Loaded =
        if (index in state.children.indices && index != state.selected) {
            state.copy(selected = index, switched = true)
        } else {
            state
        }

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): GuardianUiState =
        GuardianUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a transport failure.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): GuardianUiState = GuardianUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * The fee option a payable offers, for the pay flow.
     *
     * @param dto The server's payable
     * @return The option
     */
    fun option(dto: PayableDto): PayOption =
        PayOption(dto.enrollmentId, dto.batchName, dto.period, dto.amountDue, dto.dueDate)

    /**
     * Convert one child.
     *
     * @param dto The server's child
     * @return The card
     */
    private fun toCard(dto: ChildSummaryDto): ChildCard =
        ChildCard(
            key = dto.key,
            name = dto.displayName,
            batchCount = dto.batchCount,
            payment =
                dto.nextPayment?.let {
                    GuardianPayment(option(it), it.totalDue ?: it.amountDue, it.laterPeriods, it.daysLate)
                },
            waiting = dto.waiting.map { WaitingCard(it.batchName, it.period, it.amount, it.channel, it.submittedAt) },
            results = dto.latestResults.map(::toResult),
            batches =
                dto.batches.map {
                    ChildBatch(it.enrollmentId, it.batchName, it.teacherDisplayName, it.nextSession?.let(::toNext))
                },
        )

    /**
     * Convert one result, naming the server's trend.
     *
     * @param dto The server's result
     * @return The card
     */
    private fun toResult(dto: ChildResultDto): ResultCard =
        ResultCard(
            enrollmentId = dto.enrollmentId,
            batchName = dto.batchName,
            title = dto.title,
            date = dto.date,
            marks = dto.marks,
            totalMarks = dto.totalMarks,
            previousMarks = dto.previousMarks,
            trend =
                when (dto.trend) {
                    "up" -> Trend.UP
                    "down" -> Trend.DOWN
                    "same" -> Trend.SAME
                    else -> Trend.FIRST
                },
        )

    /**
     * Convert one coming class.
     *
     * @param dto The server's class
     * @return The class
     */
    private fun toNext(dto: UpcomingSessionDto): NextClass =
        NextClass(
            dto.date,
            dto.startTime.take(HHMM),
            dto.endTime?.take(HHMM),
            dto.startsInMinutes,
            dto.moved,
            dto.subjectName,
        )
}
