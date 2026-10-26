package com.shikkhokplus.app.feature.batches.ui


import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonBlock
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.format.Numerals
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

/** The new-class button. */
const val TAG_BATCHES_CREATE: String = "batches_create"

/** The accepted-of-total count on one batch card. */
const val TAG_BATCH_ACCEPTED_COUNT: String = "batch_accepted_count"

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
 * @param onCreate Called when the teacher wants a new class
 * @param modifier The layout modifier
 */
@Composable
fun BatchesScreen(
    state: BatchesUiState,
    onOpen: (String) -> Unit,
    onRetry: () -> Unit,
    onCreate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // `BatchesHeader` stays, in the scaffold's header slot: it carries
    // the "N batches · M students" summary, which belongs above the
    // list and must not scroll away with it.
    ListScreenScaffold(
        title = stringResource(R.string.batches_title),
        modifier = modifier,
        header = { BatchesHeader(state) },
    ) {
        when (state) {
            BatchesUiState.Idle -> Unit

            // **A static skeleton, not a spinner.** The design forbids
            // shimmer and asks the placeholder to hold the real row
            // heights, so the list does not jump when content lands.
            BatchesUiState.Loading ->
                Column(
                    Modifier
                        .testTag(TAG_BATCHES_LOADING)
                        .padding(horizontal = Spacing.screen),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    repeat(SKELETON_ROWS) { BatchSkeletonCard() }
                }

            BatchesUiState.Empty ->
                EmptyState(
                    title = stringResource(R.string.batches_empty_title),
                    body = stringResource(R.string.batches_empty_body),
                    modifier = Modifier.testTag(TAG_BATCHES_EMPTY),
                ) {
                    MoneyWeightButton(
                        text = stringResource(R.string.batches_create_first),
                        onClick = onCreate,
                        modifier = Modifier.testTag(TAG_BATCHES_CREATE),
                    )
                }

            is BatchesUiState.Loaded ->
                Box(Modifier.fillMaxSize()) {
                    LazyColumn(
                        modifier = Modifier.testTag(TAG_BATCHES_LIST),
                        contentPadding = PaddingValues(
                            start = Spacing.screen,
                            end = Spacing.screen,
                            // Clears the FAB, so the last row is
                            // reachable rather than hidden under it.
                            bottom = Spacing.screen + Reach.moneyButton + Spacing.screen,
                        ),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        items(state.rows, key = { it.id }) { row ->
                            BatchRowView(row, onOpen)
                        }
                    }
                    CreateBatchFab(
                        onClick = onCreate,
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .padding(Spacing.screen)
                            .testTag(TAG_BATCHES_CREATE),
                    )
                }

            is BatchesUiState.Failed ->
                EmptyState(
                    title = stringResource(R.string.batches_error_title),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                    modifier = Modifier.testTag(TAG_BATCHES_ERROR),
                ) {
                    // **Only when the server said retryable.** The
                    // client does not decide this [TC-9]: a retry
                    // button on a non-retryable error invites a user
                    // to repeat something that cannot work.
                    if (state.retryable) {
                        OutlinedButton(
                            onClick = onRetry,
                            modifier = Modifier
                                .heightIn(min = Reach.touch)
                                .testTag(TAG_BATCHES_RETRY),
                        ) {
                            Text(stringResource(R.string.roster_retry))
                        }
                    }
                }
        }
    }
}

/** How many placeholder cards the loading state draws. */
private const val SKELETON_ROWS = 3

/**
 * The screen's heading, with its count line.
 *
 * The subtitle changes with the state rather than disappearing, so the
 * header does not resize as content arrives — a reflow at that moment
 * moves whatever the user was about to tap.
 *
 * @param state What the screen is showing
 */
@Composable
private fun BatchesHeader(state: BatchesUiState) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(vertical = Spacing.tight),
    ) {
        // The title is in the app bar; this header carries only the
        // count beneath it. Rendering the name here as well showed it
        // twice, and the horizontal padding is now the scaffold's.
        val subtitle = when (state) {
            is BatchesUiState.Loaded -> stringResource(
                R.string.batches_count,
                state.rows.size,
                state.rows.sumOf { it.enrollmentCount },
            )
            BatchesUiState.Loading -> stringResource(R.string.batches_loading_label)
            else -> null
        }
        if (subtitle != null) {
            Text(
                text = subtitle,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * One class, as a card.
 *
 * @param row The batch to render
 * @param onOpen Called with the batch id when tapped
 */
@Composable
private fun BatchRowView(row: BatchRow, onOpen: (String) -> Unit) {
    ShikkhokCard(
        modifier = Modifier.testTag(TAG_BATCH_ROW),
        onClick = { onOpen(row.id) },
    ) {
        Text(
            // A batch name is text the teacher typed, so it is shown
            // exactly as typed — Bangla digits inside it included.
            text = Numerals.freeText(row.name),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = row.subjects.joinToString(" · ") { Numerals.freeText(it) },
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // **"9 of 12 accepted", both numbers from the SERVER**
            // [BR1.2, BR1.3, AC1.3.5a]. This composable formats two
            // integers it was handed; it does not count rows, and it
            // does not decide what counts as accepted — a client tally
            // would be wrong the moment the roster paginates [TC-9].
            //
            // Latin digits via `Numerals.count`, because this is the
            // app's own output rather than text a person typed. It is
            // the one count in the product with no other formatter
            // between the server and the screen [NFR3.3].
            Text(
                text = stringResource(
                    R.string.roster_accepted_count,
                    Numerals.count(row.acceptedCount),
                    Numerals.count(row.enrollmentCount),
                ),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag(TAG_BATCH_ACCEPTED_COUNT),
            )
            if (row.defaultFee != null) {
                Text(
                    text = stringResource(
                        R.string.batches_fee_per_month,
                        Numerals.money(row.defaultFee),
                    ),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

/** A placeholder card, sized to a real one. */
@Composable
private fun BatchSkeletonCard() {
    ShikkhokCard {
        SkeletonBlock(widthFraction = 0.6f, height = 16.dp)
        SkeletonBlock(widthFraction = 0.75f, height = 10.dp)
        SkeletonBlock(widthFraction = 0.45f, height = 12.dp)
    }
}

/**
 * The new-batch button.
 *
 * **In the bottom-right, never the top bar.** The design puts the
 * primary action within thumb reach on teacher screens; the top bar
 * holds only back, the title and the batch name.
 *
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 */
@Composable
private fun CreateBatchFab(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        modifier = modifier.heightIn(min = Reach.moneyButton),
        shape = MaterialTheme.shapes.large,
    ) {
        Text(
            text = stringResource(R.string.batch_create_title),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/**
 * A full-width button for a decision that matters.
 *
 * 56dp and full width, which the design reserves for actions with
 * consequences. Creating a batch is the first such action a teacher
 * takes, and the empty state has nothing competing for the space.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 */
@Composable
private fun MoneyWeightButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        modifier = modifier.fillMaxWidth().heightIn(min = Reach.moneyButton),
        shape = MaterialTheme.shapes.large,
    ) {
        Text(text = text, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}
