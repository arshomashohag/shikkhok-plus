package com.shikkhokplus.app.feature.dues.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.dues.DuesRow
import com.shikkhokplus.app.feature.dues.DuesUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_DUES_LOADING: String = "dues_loading"

/** The screen heading. */
const val TAG_DUES_TITLE: String = "dues_title"

/** The good-news empty state: nobody owes anything. */
const val TAG_DUES_EMPTY: String = "dues_empty"

/** The list of people who owe. */
const val TAG_DUES_LIST: String = "dues_list"

/** One person who owes. */
const val TAG_DUES_ROW: String = "dues_row"

/** The amount on one row. */
const val TAG_DUES_AMOUNT: String = "dues_amount"

/** The period the debt starts in, where the server sent one. */
const val TAG_DUES_SINCE: String = "dues_since"

/** The error message. */
const val TAG_DUES_ERROR: String = "dues_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_DUES_RETRY: String = "dues_retry"

/**
 * Everyone who owes this teacher money, across every batch [FR7.1].
 *
 * **No composable here compares a domain value.** The server decided
 * who appears, in what order and what each owes; this renders what it
 * was given. `if (outstanding > 0)` would be the dues membership rule
 * reimplemented where nothing tests it [TC-9, D-31], and sorting or
 * grouping the list would be the client deciding a domain list's shape.
 *
 * @param state What to render
 * @param onRetry Invoked when the teacher asks to try again
 * @param modifier The layout modifier
 */
@Composable
fun DuesScreen(
    state: DuesUiState,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.dues_title),
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.testTag(TAG_DUES_TITLE),
        )

        when (state) {
            DuesUiState.Idle -> Unit

            DuesUiState.Loading ->
                CircularProgressIndicator(
                    modifier = Modifier.testTag(TAG_DUES_LOADING),
                )

            // **The empty state says it is good news.** A blank list
            // explains nothing, and a teacher seeing one cannot tell it
            // apart from a failed load.
            DuesUiState.Empty ->
                Text(
                    text = stringResource(R.string.dues_nobody_owes),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag(TAG_DUES_EMPTY),
                )

            is DuesUiState.Loaded ->
                LazyColumn(
                    modifier = Modifier.testTag(TAG_DUES_LIST),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.rows, key = { it.enrollmentId }) { row ->
                        DuesRowItem(row)
                        HorizontalDivider()
                    }
                }

            is DuesUiState.Failed -> {
                Text(
                    text = stringResource(MessageKeys.resolve(state.messageKey)),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag(TAG_DUES_ERROR),
                )
                // Offered only where the SERVER said retrying could
                // work. Inferring it from a status code would be the
                // client holding a rule about retryability [TC-9].
                if (state.retryable) {
                    TextButton(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_DUES_RETRY),
                    ) {
                        Text(stringResource(R.string.dues_retry))
                    }
                }
            }
        }
    }
}

/**
 * One row: who, which class, how much, and since when.
 *
 * @param row The row to render
 */
@Composable
private fun DuesRowItem(row: DuesRow) {
    Row(
        modifier = Modifier.fillMaxWidth().testTag(TAG_DUES_ROW),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.padding(end = 12.dp)) {
            Text(
                text = row.displayName,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = row.batchName,
                style = MaterialTheme.typography.bodySmall,
            )
            // Rendered only where the server sent one. There is no
            // fallback figure: a period the server could not name is
            // not a period this screen may invent.
            row.oldestUnpaidPeriod?.let { period ->
                Text(
                    text = stringResource(R.string.dues_since, period),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag(TAG_DUES_SINCE),
                )
            }
        }
        Text(
            text = Numerals.money(row.outstanding),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.testTag(TAG_DUES_AMOUNT),
        )
    }
}
