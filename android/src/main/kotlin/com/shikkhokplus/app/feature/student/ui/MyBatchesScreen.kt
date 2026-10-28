package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.scheduleSummary
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.student.FeeLine
import com.shikkhokplus.app.feature.student.MyBatchesUiState
import com.shikkhokplus.app.feature.student.StudentBatchRow

/** The loading placeholder. */
const val TAG_MY_BATCHES_LOADING: String = "my_batches_loading"

/** The empty state, shown before any teacher has added the student. */
const val TAG_MY_BATCHES_EMPTY: String = "my_batches_empty"

/** One batch card. */
const val TAG_MY_BATCH_ROW: String = "my_batch_row"

/** A card's fee line. */
const val TAG_MY_BATCH_FEE: String = "my_batch_fee"

/** The failure message. */
const val TAG_MY_BATCHES_ERROR: String = "my_batches_error"

/** The retry button. */
const val TAG_MY_BATCHES_RETRY: String = "my_batches_retry"

/**
 * S1, "My batches": the student's home.
 *
 * @param state What to render
 * @param onOpen Called with a seat id when a batch is tapped
 * @param onRetry Called when the student asks to try again
 * @param modifier The layout modifier
 * @param bottomBar The lens's tab bar
 */
@Composable
fun MyBatchesScreen(
    state: MyBatchesUiState,
    onOpen: (String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ListScreenScaffold(
        title = stringResource(R.string.my_batches_title),
        modifier = modifier,
        bottomBar = bottomBar,
    ) {
        when (state) {
            MyBatchesUiState.Loading -> LogoLoader(Modifier.testTag(TAG_MY_BATCHES_LOADING))

            is MyBatchesUiState.Empty ->
                EmptyState(
                    title = stringResource(R.string.my_batches_empty_title),
                    body =
                        state.phone
                            ?.let { stringResource(R.string.my_batches_empty_body, Numerals.phone(it)) }
                            ?: stringResource(R.string.my_batches_empty_body_no_phone),
                    modifier = Modifier.testTag(TAG_MY_BATCHES_EMPTY),
                )

            is MyBatchesUiState.Loaded ->
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(state.rows, key = { it.enrollmentId }) { row ->
                        StudentBatchCard(row, onOpen = { onOpen(row.enrollmentId) })
                    }
                }

            is MyBatchesUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_MY_BATCHES_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry, modifier = Modifier.testTag(TAG_MY_BATCHES_RETRY)) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * One batch as a card: name, teacher and days, and the latest fee.
 *
 * @param row The batch
 * @param onOpen Called when tapped
 */
@Composable
private fun StudentBatchCard(row: StudentBatchRow, onOpen: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(TAG_MY_BATCH_ROW), onClick = onOpen) {
        Text(
            text = Numerals.freeText(row.batchName),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
        val byline =
            listOfNotNull(row.teacherName?.let(Numerals::freeText), scheduleSummary(row.schedule).ifEmpty { null })
        if (byline.isNotEmpty()) {
            Text(
                text = byline.joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        row.fee?.let { FeeSummary(it) }
    }
}

/**
 * A fee period in one line: the period, and the server's status.
 *
 * @param fee The period
 * @param modifier The layout modifier
 */
@Composable
internal fun FeeSummary(fee: FeeLine, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().testTag(TAG_MY_BATCH_FEE),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            stringResource(R.string.my_batches_fee_period, fee.period),
            style = MaterialTheme.typography.labelLarge,
        )
        Text(
            stringResource(MessageKeys.resolve(fee.statusKey)),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
