package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.sessions.SessionRow
import com.shikkhokplus.app.feature.sessions.SessionsUiState

/** One class row. */
const val TAG_CLASS_ROW: String = "batch_class_row"

/** A class row's Record button. */
const val TAG_CLASS_RECORD: String = "batch_class_record"

/**
 * The Classes tab: each class, where it stands, and what was covered.
 *
 * Tapping a class opens its attendance; Record opens the topic sheet.
 *
 * @param state The classes' state
 * @param onOpen Called with a class to take attendance
 * @param onRecord Called with a class to record its topic
 * @param onRetry Called to read the classes again
 */
@Composable
fun ClassesTab(
    state: SessionsUiState,
    onOpen: (SessionRow) -> Unit,
    onRecord: (SessionRow) -> Unit,
    onRetry: () -> Unit,
) {
    when (state) {
        SessionsUiState.Idle, SessionsUiState.Loading -> SkeletonList(rows = 4)
        is SessionsUiState.Empty ->
            EmptyState(stringResource(R.string.batch_classes_empty), stringResource(R.string.schedule_none))
        is SessionsUiState.Failed ->
            ErrorCard(
                title = stringResource(R.string.batch_classes_failed),
                body = stringResource(MessageKeys.resolve(state.messageKey)),
                retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                onRetry = onRetry.takeIf { state.retryable },
            )
        is SessionsUiState.Loaded ->
            LazyColumn(
                Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
            ) {
                items(state.rows, key = { it.sessionId }) { row ->
                    ClassRowView(row, onOpen, onRecord)
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
                }
                item { Column(Modifier.heightIn(min = 88.dp)) {} }
            }
    }
}

/**
 * One class: date and time, what it covered or that it was called off.
 *
 * @param row The class
 * @param onOpen Called to take attendance
 * @param onRecord Called to record the topic
 */
@Composable
private fun ClassRowView(row: SessionRow, onOpen: (SessionRow) -> Unit, onRecord: (SessionRow) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = !row.isCancelled) { onOpen(row) }
            .heightIn(min = 64.dp)
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .testTag(TAG_CLASS_ROW),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                listOfNotNull(
                    row.dateLabel,
                    displayTime(row.timeLabel.take(HHMM)),
                    row.subjectName?.let(Numerals::freeText),
                ).joinToString(" · "),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                when {
                    row.isCancelled -> stringResource(R.string.today_cancelled)
                    row.topicLogged && !row.topic.isNullOrBlank() -> "✓ " + Numerals.freeText(row.topic)
                    else -> stringResource(MessageKeys.resolve(row.statusLabel))
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (!row.isCancelled && !row.topicLogged) {
            TonalButton(stringResource(R.string.today_record), { onRecord(row) }, Modifier.testTag(TAG_CLASS_RECORD))
        }
    }
}

/** `HH:MM` out of `HH:MM:SS`. */
private const val HHMM = 5
