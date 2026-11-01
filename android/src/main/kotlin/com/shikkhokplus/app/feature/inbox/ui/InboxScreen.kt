package com.shikkhokplus.app.feature.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.CornerSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.inbox.InboxKind
import com.shikkhokplus.app.feature.inbox.InboxMessage
import com.shikkhokplus.app.feature.inbox.InboxUiState

/** The bell on a home screen's bar. */
const val TAG_INBOX_BELL: String = "inbox_bell"

/** The unread count on the bell. */
const val TAG_INBOX_BADGE: String = "inbox_badge"

/** One message. */
const val TAG_INBOX_ITEM: String = "inbox_item"

/** The mark-all-read action. */
const val TAG_INBOX_MARK_ALL: String = "inbox_mark_all"

/** The empty inbox. */
const val TAG_INBOX_EMPTY: String = "inbox_empty"

/** The badge's largest number; more reads as `9+`. */
private const val BADGE_MAX = 9

/**
 * The reader's inbox: fee reminders from their teachers, newest first.
 *
 * Every figure is the server's: the amount owed and the unread mark
 * arrive in the message.
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onRetry Called to read again after a failure
 * @param modifier The layout modifier
 * @param onSelect Called with the item the reader taps
 * @param onMarkAllRead Called to mark every message read
 */
@Composable
fun InboxScreen(
    state: InboxUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    onSelect: (InboxMessage) -> Unit = {},
    onMarkAllRead: () -> Unit = {},
) {
    ListScreenScaffold(
        title = stringResource(R.string.inbox_title),
        modifier = modifier,
        onBack = onBack,
        actions = {
            if (state is InboxUiState.Loaded && state.unread > 0) {
                TextButton(onClick = onMarkAllRead, modifier = Modifier.testTag(TAG_INBOX_MARK_ALL)) {
                    Text(stringResource(R.string.inbox_mark_all_read))
                }
            }
        },
    ) {
        when (state) {
            InboxUiState.Loading -> SkeletonList(modifier = Modifier.padding(top = 8.dp))
            is InboxUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.padding(top = 8.dp),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is InboxUiState.Loaded ->
                if (state.messages.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.inbox_empty_title),
                        body = stringResource(R.string.inbox_empty_body),
                        modifier = Modifier.padding(top = 8.dp).testTag(TAG_INBOX_EMPTY),
                    )
                } else {
                    Messages(state.messages, onSelect)
                }
        }
    }
}

/**
 * The messages, in one white card.
 *
 * @param messages Newest first
 * @param onSelect Called with the item tapped
 */
@Composable
private fun Messages(messages: List<InboxMessage>, onSelect: (InboxMessage) -> Unit) {
    LazyColumn(Modifier.padding(top = 8.dp)) {
        itemsIndexed(messages, key = { _, message -> message.id }) { index, message ->
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface, rowShape(index, messages.size)),
            ) {
                if (index > 0) {
                    HorizontalDivider(
                        Modifier.padding(start = 16.dp),
                        color = MaterialTheme.colorScheme.surfaceContainerHigh,
                    )
                }
                MessageRow(message, onSelect)
            }
        }
    }
}

/**
 * The card's corners: rounded only at its top and bottom.
 *
 * @param index The row's place
 * @param count How many rows
 * @return Its shape
 */
@Composable
private fun rowShape(index: Int, count: Int) =
    MaterialTheme.shapes.medium.copy(
        topStart = if (index == 0) MaterialTheme.shapes.medium.topStart else ZeroCorner,
        topEnd = if (index == 0) MaterialTheme.shapes.medium.topEnd else ZeroCorner,
        bottomStart = if (index == count - 1) MaterialTheme.shapes.medium.bottomStart else ZeroCorner,
        bottomEnd = if (index == count - 1) MaterialTheme.shapes.medium.bottomEnd else ZeroCorner,
    )

/**
 * One reminder: bell, batch, what is owed, and when it came.
 *
 * @param message The message
 * @param onSelect Called when the row is tapped
 */
@Composable
private fun MessageRow(message: InboxMessage, onSelect: (InboxMessage) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable { onSelect(message) }
            .heightIn(min = 72.dp)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(TAG_INBOX_ITEM),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier
                .size(40.dp)
                .background(MaterialTheme.colorScheme.errorContainer, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                painterResource(R.drawable.ic_bell),
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.size(20.dp),
            )
        }
        Column(Modifier.weight(1f)) {
            Text(
                inboxTitle(message.kind, message.childName, message.batchName),
                style =
                    MaterialTheme.typography.bodyLarge.copy(
                        fontWeight = if (message.unread) FontWeight.Bold else FontWeight.Normal,
                    ),
            )
            (message.preview?.let(Numerals::freeText) ?: body(message))?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                ago(message.sentAt),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (message.unread) {
            Box(Modifier.padding(top = 6.dp).size(10.dp).background(MaterialTheme.colorScheme.primary, CircleShape))
        }
    }
}

/**
 * A message's heading: what it is, then who and which batch.
 *
 * @param kind What it is about
 * @param childName Which child, on a guardian's copy
 * @param batchName The batch
 * @return The heading, such as `Fee reminder · Rahim · Physics`
 */
@Composable
internal fun inboxTitle(kind: InboxKind, childName: String?, batchName: String): String {
    val subject = listOfNotNull(childName, batchName).joinToString(" · ")
    return stringResource(titleOf(kind), Numerals.freeText(subject))
}

/**
 * A message's heading template, by what it is about.
 *
 * @param kind What it is about
 * @return Its string resource
 */
private fun titleOf(kind: InboxKind): Int =
    when (kind) {
        InboxKind.FEE_REMINDER -> R.string.inbox_fee_reminder_title
        InboxKind.PAYMENT_APPROVED -> R.string.inbox_payment_approved_title
        InboxKind.PAYMENT_PARTIAL -> R.string.inbox_payment_partial_title
        InboxKind.PAYMENT_REJECTED -> R.string.inbox_payment_rejected_title
        InboxKind.NOTICE -> R.string.inbox_notice_title
        InboxKind.EXAM_SCHEDULED -> R.string.inbox_exam_scheduled_title
        InboxKind.MARKS_AVAILABLE -> R.string.inbox_marks_available_title
        InboxKind.CLAIM_TO_VERIFY -> R.string.inbox_claim_to_verify_title
    }

/**
 * "৳1,200 is due, from Oct." or what happened to a payment.
 *
 * @param message The message
 * @return The line, or null when it carries no amount
 */
@Composable
private fun body(message: InboxMessage): String? {
    val amount = message.amount ?: return null
    val period = message.period
    val money = Numerals.money(amount)
    val month = period?.let { monthName(it, short = false) }
    return when {
        month == null && message.kind == InboxKind.FEE_REMINDER ->
            stringResource(R.string.inbox_fee_reminder_body_no_period, money)
        month == null -> null
        else ->
            stringResource(
                when (message.kind) {
                    InboxKind.PAYMENT_APPROVED -> R.string.inbox_payment_approved_body
                    InboxKind.PAYMENT_PARTIAL -> R.string.inbox_payment_partial_body
                    InboxKind.PAYMENT_REJECTED -> R.string.inbox_payment_rejected_body
                    InboxKind.CLAIM_TO_VERIFY -> R.string.inbox_claim_to_verify_body
                    else -> R.string.inbox_fee_reminder_body
                },
                money,
                month,
            )
    }
}

/**
 * The bell for a home screen's bar, with the server's unread count.
 *
 * @param unread How many are unread; nothing is drawn for zero
 * @param onClick Called to open the inbox
 */
@Composable
fun InboxBell(unread: Int, onClick: () -> Unit) {
    IconButton(onClick = onClick, modifier = Modifier.testTag(TAG_INBOX_BELL)) {
        Box {
            Icon(
                painterResource(R.drawable.ic_bell),
                contentDescription = stringResource(R.string.inbox_open),
                modifier = Modifier.size(24.dp),
            )
            if (unread > 0) {
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .offset(x = 6.dp, y = (-4).dp)
                        .sizeIn(minWidth = 16.dp, minHeight = 16.dp)
                        .background(MaterialTheme.colorScheme.error, CircleShape)
                        .padding(horizontal = 4.dp)
                        .testTag(TAG_INBOX_BADGE),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        if (unread > BADGE_MAX) "${Numerals.count(BADGE_MAX)}+" else Numerals.count(unread),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onError,
                    )
                }
            }
        }
    }
}

/** A square corner for the card's inner rows. */
private val ZeroCorner = CornerSize(0.dp)
