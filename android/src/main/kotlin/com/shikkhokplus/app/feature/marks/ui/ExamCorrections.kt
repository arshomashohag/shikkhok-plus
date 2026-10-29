package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.HistoryEntry
import com.shikkhokplus.app.feature.marks.MarkHistory

/** One recorded mark in the history sheet. */
const val TAG_MARK_HISTORY_ENTRY: String = "mark_history_entry"

/** The exam edit form. */
const val TAG_EXAM_EDIT: String = "exam_edit"

/**
 * Every mark recorded for one seat in one exam, oldest first [FR9.2].
 *
 * A correction never overwrites: each row the teacher recorded stays,
 * and the ones replaced are struck through.
 *
 * @param history The seat's history
 * @param onDismiss Called to close the sheet
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MarkHistorySheet(history: MarkHistory, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, bottom = 24.dp)) {
            Text(
                stringResource(R.string.mark_history_title, Numerals.freeText(history.displayName)),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            val entries = history.entries
            when {
                history.failed ->
                    Text(
                        stringResource(MessageKeys.resolve(OFFLINE_KEY)),
                        color = MaterialTheme.colorScheme.error,
                    )
                entries == null -> SkeletonList(rows = 2)
                else ->
                    entries.forEachIndexed { index, entry ->
                        if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
                        EntryRow(entry)
                    }
            }
        }
    }
}

/**
 * One recorded mark: what was recorded and when.
 *
 * @param entry The row
 */
@Composable
private fun EntryRow(entry: HistoryEntry) {
    val decoration = if (entry.superseded) TextDecoration.LineThrough else TextDecoration.None
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag(TAG_MARK_HISTORY_ENTRY),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            entry.marks?.let(Numerals::count) ?: stringResource(MessageKeys.resolve(entry.stateLabel)),
            style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold, textDecoration = decoration),
            modifier = Modifier.weight(1f),
        )
        Text(
            if (entry.superseded) {
                stringResource(R.string.mark_history_replaced, ago(entry.recordedAt))
            } else {
                stringResource(R.string.mark_history_current, ago(entry.recordedAt))
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Edit an exam's title, date and total, with the create form filled in.
 *
 * Closes once the server accepts the edit; a total below a mark already
 * recorded is refused there and shown beside the fields.
 *
 * @param values The exam as it stands
 * @param write Where the save stands
 * @param onSave Called with title, ISO date and total
 * @param onClose Called to leave
 * @param modifier The layout modifier
 */
@Composable
fun EditExamScreen(
    values: ExamFormValues,
    write: WriteState,
    onSave: (String, String, Int) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    LaunchedEffect(write) {
        if (write == WriteState.Saved) onClose()
    }
    ScreenScaffold(title = stringResource(R.string.exam_edit_title), modifier = modifier, onBack = onClose) {
        ExamCreateForm(
            subjects = emptyList(),
            onCreate = { title, date, total, _ -> onSave(title, date, total) },
            onCancel = onClose,
            modifier = Modifier.testTag(TAG_EXAM_EDIT),
            saving = write == WriteState.Saving,
            error = (write as? WriteState.Failed)?.let { stringResource(MessageKeys.resolve(it.messageKey)) },
            editing = values,
        )
    }
}

/** The key shown when the device cannot reach the server at all. */
private const val OFFLINE_KEY: String = "error.network.unreachable"
