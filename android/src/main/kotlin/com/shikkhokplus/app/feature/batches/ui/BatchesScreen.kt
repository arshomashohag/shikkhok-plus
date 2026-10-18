package com.shikkhokplus.app.feature.batches.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.batches.BatchRow
import com.shikkhokplus.app.feature.batches.BatchesUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_BATCHES_LOADING: String = "batches_loading"

/** The list of batches. */
const val TAG_BATCHES_LIST: String = "batches_list"

/** One batch. */
const val TAG_BATCH_ROW: String = "batch_row"

/** The explanation shown when a teacher has no batches. */
const val TAG_BATCHES_EMPTY: String = "batches_empty"

/** The error message. */
const val TAG_BATCHES_ERROR: String = "batches_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_BATCHES_RETRY: String = "batches_retry"

/**
 * The teacher's classes.
 *
 * **Renders a [BatchesUiState] and nothing else.** No conditional here
 * depends on a domain value: the count comes from the server and the
 * fee is formatted by the renderer, not decided by it [TC-9, D-31].
 *
 * @param state What to render
 * @param onOpen Called with a batch id when a row is tapped
 * @param onRetry Called when the user asks to retry
 * @param modifier The layout modifier
 */
@Composable
fun BatchesScreen(
    state: BatchesUiState,
    onOpen: (String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.batches_title),
            style = MaterialTheme.typography.titleLarge,
        )

        when (state) {
            BatchesUiState.Idle -> Unit

            BatchesUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_BATCHES_LOADING))

            BatchesUiState.Empty ->
                Text(
                    stringResource(R.string.batches_empty),
                    Modifier.testTag(TAG_BATCHES_EMPTY),
                )

            is BatchesUiState.Loaded ->
                LazyColumn(Modifier.testTag(TAG_BATCHES_LIST)) {
                    items(state.rows, key = { it.id }) { row ->
                        BatchRowView(row, onOpen)
                    }
                }

            is BatchesUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_BATCHES_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_BATCHES_RETRY),
                    ) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * One class.
 *
 * @param row The batch to render
 * @param onOpen Called with the batch id when tapped
 */
@Composable
private fun BatchRowView(row: BatchRow, onOpen: (String) -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clickable { onOpen(row.id) }
            .padding(vertical = 8.dp)
            .testTag(TAG_BATCH_ROW),
    ) {
        Text(row.name, style = MaterialTheme.typography.titleMedium)
        Text(row.subjects.joinToString(", "))
        // A PLURAL resource, not a format string. Bangla and English
        // agree on the plural rule here, but a format string would have
        // made "1 students" the permanent answer in both.
        Text(
            androidx.compose.ui.res.pluralStringResource(
                R.plurals.batches_student_count,
                row.enrollmentCount,
                row.enrollmentCount,
            ),
        )
    }
}
