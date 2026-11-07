package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One of the reader's own help-centre questions.
 *
 * @property ticketId The question
 * @property subject Its one-line summary, as the reader wrote it
 * @property status `open` (with support), `answered` or `closed`
 * @property createdAt When it was asked
 * @property updatedAt The latest activity on it
 * @property hasNewReply Support replied since the reader last opened it
 * @property preview The start of the latest message
 */
@Serializable
data class HelpTicketDto(
    @SerialName("ticket_id") val ticketId: String,
    val subject: String,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("has_new_reply") val hasNewReply: Boolean,
    val preview: String,
)

/**
 * The reader's questions, most recently active first.
 *
 * @property tickets The questions
 * @property newReplies How many carry a reply not yet seen
 */
@Serializable
data class HelpTicketListDto(
    val tickets: List<HelpTicketDto>,
    @SerialName("new_replies") val newReplies: Int,
)

/**
 * One message in a question's thread.
 *
 * @property messageId The message
 * @property author `requester` for the reader, `support` for ShikkhokPlus;
 *   a support reply never names the person who wrote it
 * @property body What was written
 * @property createdAt When
 */
@Serializable
data class HelpMessageDto(
    @SerialName("message_id") val messageId: String,
    val author: String,
    val body: String,
    @SerialName("created_at") val createdAt: String,
)

/**
 * A question and its whole thread, oldest message first.
 *
 * @property ticket The question
 * @property messages Its messages
 */
@Serializable
data class HelpTicketDetailDto(
    val ticket: HelpTicketDto,
    val messages: List<HelpMessageDto>,
)

/**
 * Ask support a question.
 *
 * @property subject A one-line summary, 1 to 120 characters once trimmed
 * @property body The question, 1 to 4000 characters once trimmed
 */
@Serializable
data class HelpTicketRequestDto(
    val subject: String,
    val body: String,
)

/**
 * Add a message to a question's thread.
 *
 * @property body The message, 1 to 4000 characters once trimmed
 */
@Serializable
data class HelpReplyRequestDto(
    val body: String,
)
