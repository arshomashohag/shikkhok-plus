package com.shikkhokplus.app.feature.help

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.HelpMessageDto
import com.shikkhokplus.app.core.network.HelpTicketDetailDto
import com.shikkhokplus.app.core.network.HelpTicketDto
import com.shikkhokplus.app.core.network.HelpTicketListDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * Maps the help centre's responses to UI states. Pure: no network, no
 * clock.
 */
object HelpMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The server's word for a message written by support. */
    private const val SUPPORT = "support"

    /**
     * Name a status.
     *
     * A word this build does not know reads as open -- "With support" --
     * rather than hiding the question: the reader asked it, and a list
     * that drops it says it was never asked.
     *
     * @param wire The server's `status`
     * @return The status
     */
    fun statusOf(wire: String): HelpStatus =
        HelpStatus.entries.firstOrNull { it.name.lowercase() == wire } ?: HelpStatus.OPEN

    /**
     * Map the list, in the server's order.
     *
     * @param dto The server's list
     * @return The state to render
     */
    fun afterList(dto: HelpTicketListDto): HelpListUiState =
        HelpListUiState.Loaded(dto.tickets.map(::ticketOf), dto.newReplies)

    /**
     * Map a thread, in the server's order.
     *
     * @param dto The server's thread
     * @return The thread
     */
    fun threadOf(dto: HelpTicketDetailDto): HelpThread {
        val ticket = ticketOf(dto.ticket)
        return HelpThread(ticket, dto.messages.map(::messageOf), closed = ticket.status == HelpStatus.CLOSED)
    }

    /**
     * Map a read of the list.
     *
     * @param result The repository's answer
     * @return The state to render
     */
    fun list(result: AuthResult<HelpTicketListDto>): HelpListUiState =
        when (result) {
            is AuthResult.Ok -> afterList(result.value)
            is AuthResult.Refused ->
                HelpListUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> HelpListUiState.Failed(OFFLINE_KEY, retryable = true)
        }

    /**
     * Map a read of one thread.
     *
     * @param result The repository's answer
     * @return The state to render
     */
    fun thread(result: AuthResult<HelpTicketDetailDto>): HelpThreadUiState =
        when (result) {
            is AuthResult.Ok -> HelpThreadUiState.Loaded(threadOf(result.value))
            is AuthResult.Refused ->
                HelpThreadUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> HelpThreadUiState.Failed(OFFLINE_KEY, retryable = true)
        }

    /**
     * Map a write that was refused.
     *
     * @param envelope The server's error
     * @return The failed write, carrying the server's key and retryability
     */
    fun writeFailed(envelope: ErrorEnvelope): WriteState.Failed =
        WriteState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a write that got no answer.
     *
     * @return The failed write; a lost connection is always worth retrying
     */
    fun writeUnanswered(): WriteState.Failed = WriteState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Convert one question.
     *
     * @param dto The server's question
     * @return The question to render
     */
    private fun ticketOf(dto: HelpTicketDto): HelpTicket =
        HelpTicket(
            id = dto.ticketId,
            subject = dto.subject,
            status = statusOf(dto.status),
            updatedAt = dto.updatedAt,
            newReply = dto.hasNewReply,
            preview = dto.preview,
        )

    /**
     * Convert one message.
     *
     * @param dto The server's message
     * @return The message to render
     */
    private fun messageOf(dto: HelpMessageDto): HelpMessage =
        HelpMessage(id = dto.messageId, fromSupport = dto.author == SUPPORT, body = dto.body, sentAt = dto.createdAt)
}
