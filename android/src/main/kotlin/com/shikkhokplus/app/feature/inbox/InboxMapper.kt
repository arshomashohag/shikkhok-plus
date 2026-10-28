package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NotificationDto

/**
 * Maps the inbox response to an [InboxUiState]. Pure: no network, no
 * clock.
 */
object InboxMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The one kind this app knows how to show. */
    private const val FEE_REMINDER: String = "fee_reminder"

    /**
     * Map a loaded inbox, in the server's order.
     *
     * A kind this version does not know is left out rather than shown
     * as something it is not; the server's unread count still stands.
     *
     * @param dto The inbox
     * @return The state to render
     */
    fun afterLoad(dto: InboxDto): InboxUiState =
        InboxUiState.Loaded(dto.items.filter { it.kind == FEE_REMINDER }.map(::toMessage), dto.unread)

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @return The state to render
     */
    fun afterError(envelope: ErrorEnvelope): InboxUiState =
        InboxUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Map a transport failure.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): InboxUiState = InboxUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Convert one message.
     *
     * @param dto The server's message
     * @return The message to render
     */
    private fun toMessage(dto: NotificationDto): InboxMessage =
        InboxMessage(
            id = dto.notificationId,
            batchName = dto.batchName,
            amount = dto.amount,
            period = dto.period,
            sentAt = dto.createdAt,
            unread = !dto.read,
        )
}
