package com.shikkhokplus.app.feature.inbox.ui

import androidx.compose.foundation.background
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
import com.shikkhokplus.app.feature.inbox.InboxMessage
import com.shikkhokplus.app.feature.inbox.InboxUiState

/** The bell on a home screen's bar. */
const val TAG_INBOX_BELL: String = "inbox_bell"

/** The unread count on the bell. */
const val TAG_INBOX_BADGE: String = "inbox_badge"

/** One message. */
const val TAG_INBOX_ITEM: String = "inbox_item"

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
 */
@Composable
fun InboxScreen(
    state: InboxUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.inbox_title),
        modifier = modifier,
        onBack = onBack,
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
                    Messages(state.messages)
                }
        }
    }
}

/**
 * The messages, in one white card.
 *
 * @param messages Newest first
 */
@Composable
private fun Messages(messages: List<InboxMessage>) {
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
                MessageRow(message)
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
 */
@Composable
private fun MessageRow(message: InboxMessage) {
    Row(
        Modifier
            .fillMaxWidth()
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
                stringResource(R.string.inbox_fee_reminder_title, Numerals.freeText(message.batchName)),
                style =
                    MaterialTheme.typography.bodyLarge.copy(
                        fontWeight = if (message.unread) FontWeight.Bold else FontWeight.Normal,
                    ),
            )
            body(message)?.let {
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
 * "৳1,200 is due, from Oct."
 *
 * @param message The message
 * @return The line, or null when it carries no amount
 */
@Composable
private fun body(message: InboxMessage): String? {
    val amount = message.amount ?: return null
    val period = message.period
    return if (period == null) {
        stringResource(R.string.inbox_fee_reminder_body_no_period, Numerals.money(amount))
    } else {
        stringResource(R.string.inbox_fee_reminder_body, Numerals.money(amount), monthName(period, short = false))
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
