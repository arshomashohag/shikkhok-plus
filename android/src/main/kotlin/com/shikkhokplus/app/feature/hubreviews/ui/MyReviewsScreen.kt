package com.shikkhokplus.app.feature.hubreviews.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.Quiet
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayMonthYear
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubreviews.MyReviewsUiState
import com.shikkhokplus.app.feature.hubreviews.ReviewableBatch
import com.shikkhokplus.app.feature.hubreviews.ReviewableState

/**
 * Tag for one batch's row.
 *
 * @param batchId The batch
 * @return The tag
 */
fun hubReviewsRowTag(batchId: String): String = "hub_reviews_row_$batchId"

/**
 * What the guardian's review list can do.
 *
 * @property onOpen Opens a batch's review
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class MyReviewsActions(
    val onOpen: (ReviewableBatch) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The batches a guardian may review, is waiting to, or has reviewed,
 * each opening its review [H4]. Each row shows the server's state and,
 * for one not yet open, the day the server says it opens; the client
 * counts no days or classes.
 *
 * @param state What to render
 * @param actions What the rows do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MyReviewsScreen(
    state: MyReviewsUiState,
    actions: MyReviewsActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_reviews_title), modifier = modifier, onBack = actions.onBack) {
        when (state) {
            MyReviewsUiState.Loading -> SkeletonList(rows = 3)
            is MyReviewsUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            MyReviewsUiState.Off -> Unit
            is MyReviewsUiState.Ready ->
                if (state.rows.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.hub_reviews_empty),
                        body = stringResource(R.string.hub_reviews_entry_guardian_sub),
                    )
                } else {
                    state.rows.forEach { row -> BatchRow(row) { actions.onOpen(row) } }
                }
        }
    }
}

/**
 * One batch: its title, its owner's public name, and where the guardian stands.
 *
 * @param row The server's row
 * @param onOpen Opens its review
 */
@Composable
private fun BatchRow(row: ReviewableBatch, onOpen: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(hubReviewsRowTag(row.batchId)), onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Numerals.freeText(row.batchTitle), style = MaterialTheme.typography.titleMedium)
                Quiet(Numerals.freeText(row.ownerPublicName))
            }
            Column(Modifier.padding(start = 12.dp), horizontalAlignment = Alignment.End) {
                stateText(row.state)?.let {
                    Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                }
                row.eligibleFrom?.let { Quiet(stringResource(R.string.hub_reviews_from, dayMonthYear(it))) }
            }
        }
    }
}

/**
 * A row's state in words.
 *
 * @param wire The server's state
 * @return The words, or null for a state this version does not know
 */
@Composable
private fun stateText(wire: String): String? =
    when (ReviewableState.fromWire(wire)) {
        ReviewableState.ELIGIBLE -> stringResource(R.string.hub_reviews_state_eligible)
        ReviewableState.NOT_YET -> stringResource(R.string.hub_reviews_state_not_yet)
        ReviewableState.REVIEWED -> stringResource(R.string.hub_reviews_state_reviewed)
        null -> null
    }
