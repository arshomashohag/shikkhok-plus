package com.shikkhokplus.app.feature.help

import com.shikkhokplus.app.core.ui.WriteState

/** The longest subject the server accepts, once trimmed. */
const val HELP_SUBJECT_MAX: Int = 120

/** The longest message the server accepts, once trimmed. */
const val HELP_BODY_MAX: Int = 4000

/** Where a question stands, as the server named it. */
enum class HelpStatus {
    /** Waiting for support: shown as "With support". */
    OPEN,

    /** Support replied: shown as "Answered". */
    ANSWERED,

    /** Closed; a reply reopens it. */
    CLOSED,
}

/**
 * One question, as the list shows it.
 *
 * @property id The question
 * @property subject Its summary, as the reader wrote it
 * @property status Where it stands
 * @property updatedAt The latest activity, as the server's timestamp
 * @property newReply Whether support replied since the reader last
 *   opened it, as the server decided
 * @property preview The start of the latest message
 */
data class HelpTicket(
    val id: String,
    val subject: String,
    val status: HelpStatus,
    val updatedAt: String,
    val newReply: Boolean,
    val preview: String,
)

/** Everything the My questions list renders. */
sealed interface HelpListUiState {
    /** A request is in flight. */
    data object Loading : HelpListUiState

    /**
     * Read.
     *
     * @property tickets Most recently active first, as the server ordered them
     * @property newReplies How many carry an unseen reply, counted by the server
     */
    data class Loaded(val tickets: List<HelpTicket>, val newReplies: Int) : HelpListUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : HelpListUiState
}

/**
 * One message in a thread.
 *
 * @property id The message
 * @property fromSupport True for ShikkhokPlus support, false for the reader
 * @property body What was written, untouched
 * @property sentAt When, as the server's timestamp
 */
data class HelpMessage(
    val id: String,
    val fromSupport: Boolean,
    val body: String,
    val sentAt: String,
)

/**
 * A question opened to its thread.
 *
 * @property ticket The question
 * @property messages Oldest first, as the server ordered them
 * @property closed Whether the question is closed, so the reply box says
 *   that sending reopens it
 */
data class HelpThread(
    val ticket: HelpTicket,
    val messages: List<HelpMessage>,
    val closed: Boolean,
)

/** Everything the thread screen renders, apart from the reply box. */
sealed interface HelpThreadUiState {
    /** A request is in flight. */
    data object Loading : HelpThreadUiState

    /**
     * Read.
     *
     * @property thread The question and its messages
     */
    data class Loaded(val thread: HelpThread) : HelpThreadUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : HelpThreadUiState
}

/**
 * The Ask a question form.
 *
 * **What was typed survives a failure.** A refused or unanswered send
 * leaves [subject] and [body] as they were, so a retry is one tap and
 * nothing has to be typed again.
 *
 * @property subject The summary as typed
 * @property body The question as typed
 * @property write Where the send stands
 * @property ticketId The new question, once the server accepted it
 */
data class AskUiState(
    val subject: String = "",
    val body: String = "",
    val write: WriteState = WriteState.Idle,
    val ticketId: String? = null,
) {
    /** Whether Send can be pressed: both fields valid and nothing in flight. */
    val canSend: Boolean
        get() = sendable(subject, HELP_SUBJECT_MAX) && sendable(body, HELP_BODY_MAX) && write != WriteState.Saving
}

/**
 * The reply box under a thread.
 *
 * @property text The reply as typed; kept when a send fails
 * @property write Where the send stands
 */
data class ReplyUiState(
    val text: String = "",
    val write: WriteState = WriteState.Idle,
) {
    /** Whether Send can be pressed. */
    val canSend: Boolean
        get() = sendable(text, HELP_BODY_MAX) && write != WriteState.Saving
}

/**
 * Whether a field may be sent. **Format only**: trimmed, not empty, and
 * within the server's length. Anything more is the server's to refuse.
 *
 * @param text The field as typed
 * @param max The longest the server accepts
 * @return True when the server's own length check would pass
 */
internal fun sendable(text: String, max: Int): Boolean = text.trim().length in 1..max
