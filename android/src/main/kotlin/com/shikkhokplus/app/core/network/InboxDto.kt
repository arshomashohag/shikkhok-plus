package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One message in the reader's own inbox.
 *
 * @property notificationId The message
 * @property kind What produced it; `fee_reminder` today
 * @property enrollmentId The seat it is about, if any
 * @property batchName The batch, as named when it was sent
 * @property period The period it concerns, as `YYYY-MM`, if any
 * @property amount What is owed, as the server computed it, if any
 * @property createdAt When it was sent
 * @property read Whether the reader has opened the inbox since
 */
@Serializable
data class NotificationDto(
    @SerialName("notification_id") val notificationId: String,
    val kind: String,
    @SerialName("enrollment_id") val enrollmentId: String? = null,
    @SerialName("batch_name") val batchName: String,
    val period: String? = null,
    val amount: Money? = null,
    @SerialName("created_at") val createdAt: String,
    val read: Boolean,
)

/**
 * The reader's inbox, newest first.
 *
 * @property items The messages
 * @property unread How many have not been seen, for the bell's badge
 */
@Serializable
data class InboxDto(
    val items: List<NotificationDto> = emptyList(),
    val unread: Int,
)
