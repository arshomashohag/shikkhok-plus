package com.shikkhokplus.app.feature.roster.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.feature.roster.RosterUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_ROSTER_LOADING: String = "roster_loading"

/** The batch name heading. */
const val TAG_ROSTER_TITLE: String = "roster_title"

/** The explanation shown when a batch holds no seats. */
const val TAG_ROSTER_EMPTY: String = "roster_empty"

/** The staleness notice shown when rendering cached data. */
const val TAG_ROSTER_FETCHED_AT: String = "roster_fetched_at"

/** The list of seats. */
const val TAG_ROSTER_LIST: String = "roster_list"

/** One seat. */
const val TAG_ROSTER_ROW: String = "roster_row"

/** The error message. */
const val TAG_ROSTER_ERROR: String = "roster_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_ROSTER_RETRY: String = "roster_retry"

/**
 * The teacher's roster for one batch.
 *
 * **This composable renders a [RosterUiState] and nothing else.** There
 * is no conditional here depending on a domain value — no comparison of
 * a date against today, no threshold on an amount, no decision about
 * what counts as due. Every such decision was made by
 * `RosterStateMapper` [TC-9, D-31].
 *
 * The retry button appears because the *state* says `retryable`, which
 * the server set. The client never infers that from a status code.
 *
 * Test tags are stable identifiers for the Compose UI test; they are
 * not user-visible text.
 */
@Composable
fun RosterScreen(
    state: RosterUiState,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when (state) {
            RosterUiState.Idle -> Unit

            RosterUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_ROSTER_LOADING))

            is RosterUiState.Empty -> {
                Text(state.batchName, Modifier.testTag(TAG_ROSTER_TITLE))
                // An empty list and "no students yet" are different
                // states, and a blank list explains neither.
                Text(
                    stringResource(R.string.roster_empty),
                    Modifier.testTag(TAG_ROSTER_EMPTY),
                )
            }

            is RosterUiState.Loaded -> {
                Text(state.batchName, Modifier.testTag(TAG_ROSTER_TITLE))
                state.fetchedAtLabel?.let { label ->
                    // The cache is a READ cache, and saying so is part of
                    // the contract: a teacher must know when they are
                    // looking at saved data rather than live data.
                    Text(
                        stringResource(R.string.roster_fetched_at, label),
                        Modifier.testTag(TAG_ROSTER_FETCHED_AT),
                    )
                }
                LazyColumn(Modifier.testTag(TAG_ROSTER_LIST)) {
                    items(state.rows, key = { it.enrollmentId }) { row ->
                        RosterRowView(row)
                    }
                }
            }

            is RosterUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_ROSTER_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry, modifier = Modifier.testTag(TAG_ROSTER_RETRY)) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * One seat.
 *
 * The status label is a **resource key the mapper chose** from the
 * server's enum. This composable looks up a string and renders it; it
 * does not decide which one.
 *
 * @param row The row to render
 */
@Composable
private fun RosterRowView(row: RosterRow) {
    Column(Modifier.fillMaxWidth().testTag(TAG_ROSTER_ROW)) {
        Text(row.displayName)
        Text(stringResource(MessageKeys.resolve(row.statusLabel)))
    }
}
