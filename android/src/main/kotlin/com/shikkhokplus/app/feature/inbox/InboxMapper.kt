package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NotificationDetailDto
import com.shikkhokplus.app.core.network.NotificationDto

/**
 * Maps the inbox response to an [InboxUiState]. Pure: no network, no
 * clock.
 */
object InboxMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The kinds this app knows how to show, by their wire names. */
    private val KINDS: Map<String, InboxKind> =
        mapOf(
            "fee_reminder" to InboxKind.FEE_REMINDER,
            "payment_approved" to InboxKind.PAYMENT_APPROVED,
            "payment_partial" to InboxKind.PAYMENT_PARTIAL,
            "payment_rejected" to InboxKind.PAYMENT_REJECTED,
            "notice" to InboxKind.NOTICE,
            "exam_scheduled" to InboxKind.EXAM_SCHEDULED,
            "marks_available" to InboxKind.MARKS_AVAILABLE,
            "claim_to_verify" to InboxKind.CLAIM_TO_VERIFY,
        )

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
        InboxUiState.Loaded(dto.items.mapNotNull(::toMessage), dto.unread)

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
     * @return The message to render, or null for a kind this app does not know
     */
    private fun toMessage(dto: NotificationDto): InboxMessage? =
        KINDS[dto.kind]?.let { kind ->
            InboxMessage(
                id = dto.notificationId,
                batchName = dto.batchName,
                amount = dto.amount,
                period = dto.period,
                sentAt = dto.createdAt,
                unread = !dto.read,
                kind = kind,
                enrollmentId = dto.enrollmentId,
                sourceId = dto.sourceId,
                childName = dto.childName,
                preview = dto.preview,
            )
        }

    /**
     * Where tapping an item leads.
     *
     * An item without the ids its screen needs opens its own detail
     * instead of a screen that could not load.
     *
     * @param message The item
     * @return The target
     */
    fun targetOf(message: InboxMessage): InboxTarget {
        val guardian = message.childName != null
        val seat = message.enrollmentId
        val source = message.sourceId
        return when {
            message.kind == InboxKind.MARKS_AVAILABLE && seat != null && source != null ->
                InboxTarget.Marksheet(source, seat, guardian)
            message.kind == InboxKind.FEE_REMINDER && seat != null -> InboxTarget.Fees(seat, guardian)
            message.kind == InboxKind.CLAIM_TO_VERIFY -> InboxTarget.Verify
            else -> InboxTarget.Detail(message.id)
        }
    }

    /**
     * Map a loaded detail.
     *
     * @param dto The server's detail
     * @return Unavailable when the server says so, else the content
     */
    fun afterDetail(dto: NotificationDetailDto): InboxDetailUiState {
        val kind = KINDS[dto.kind]
        return if (!dto.available || kind == null) {
            InboxDetailUiState.Unavailable
        } else {
            InboxDetailUiState.Loaded(
                InboxDetail(kind, dto.batchName, dto.childName, contentOf(dto)),
            )
        }
    }

    /**
     * Map a server error envelope for the detail.
     *
     * @param envelope The server's error
     * @return The state to render
     */
    fun detailError(envelope: ErrorEnvelope): InboxDetailUiState =
        InboxDetailUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    /**
     * Pick the block that carries the item's content.
     *
     * @param dto The server's detail
     * @return The content, or null when the kind carries none
     */
    private fun contentOf(dto: NotificationDetailDto): InboxContent? =
        dto.notice?.let { InboxContent.Notice(it.body, it.postedAt, it.editedAt) }
            ?: dto.exam?.let { InboxContent.Exam(it.title, it.date, it.subjectName, it.totalMarks, it.topics) }
            ?: dto.payment?.let {
                InboxContent.Payment(it.period, it.claimed, it.approved, outcomeOf(it.outcome), it.reason)
            }

    /**
     * Name a payment outcome.
     *
     * @param wire The server's word
     * @return The outcome; an unknown word reads as pending
     */
    private fun outcomeOf(wire: String): PaymentOutcome =
        PaymentOutcome.entries.firstOrNull { it.name.lowercase() == wire } ?: PaymentOutcome.PENDING
}
