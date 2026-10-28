package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.model.Money

/**
 * One fee reminder, as the inbox shows it.
 *
 * @property id The message
 * @property batchName The batch it is about
 * @property amount What is owed, as the server computed it, if any
 * @property period The period the debt starts in, if any
 * @property sentAt When it was sent
 * @property unread Whether it arrived since the inbox was last opened
 */
data class InboxMessage(
    val id: String,
    val batchName: String,
    val amount: Money?,
    val period: String?,
    val sentAt: String,
    val unread: Boolean,
)

/** Everything the inbox screen and the bell render. */
sealed interface InboxUiState {
    /** A request is in flight. */
    data object Loading : InboxUiState

    /**
     * Read.
     *
     * @property messages Newest first, as the server ordered them
     * @property unread The badge's number, counted by the server
     */
    data class Loaded(val messages: List<InboxMessage>, val unread: Int) : InboxUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : InboxUiState
}
