package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.MarksUiState
import com.shikkhokplus.app.feature.marks.ProgressRow

/** Stable test identifiers. Not user-visible text. */
const val TAG_PROGRESS_LOADING: String = "progress_loading"

/** The child's name and class. */
const val TAG_PROGRESS_TITLE: String = "progress_title"

/** The series. */
const val TAG_PROGRESS_LIST: String = "progress_list"

/** One exam in the series. */
const val TAG_PROGRESS_ROW: String = "progress_row"

/** One exam's score, present only for a marked result. */
const val TAG_PROGRESS_MARKS: String = "progress_marks"

/**
 * One exam's result state, shown for every entry.
 *
 * Present on an absence too, where no score is shown at all — which is
 * the point [BR6.6].
 */
const val TAG_PROGRESS_STATE: String = "progress_state"

/** The explanation shown when a child has sat no exams. */
const val TAG_PROGRESS_EMPTY: String = "progress_empty"

/** The error message. */
const val TAG_PROGRESS_ERROR: String = "progress_error"

/** The retry button. */
const val TAG_PROGRESS_RETRY: String = "progress_retry"

/**
 * A guardian's view of their child's results over time [FR4.7].
 *
 * **This composable renders a [MarksUiState] and nothing else.** The
 * series arrives in the server's date order and is never sorted here: a
 * client sort would differ from the server's tiebreak the moment two
 * exams share a date.
 *
 * **An absence shows as absent and carries no number** [BR6.6]. The
 * row renders its score only when one exists, so there is no `?: 0` to
 * reach for — an absence plotted as zero shows a collapse in
 * performance that did not happen, which is the single most alarming
 * thing this screen can say wrongly.
 *
 * **One child, named** [BR7.2]. The enrollment id arrives as a path
 * parameter and never from a client hint, and the server refuses a
 * non-child id with the same response it gives for an invented one.
 * Attribution is shown even when the guardian watches only one child
 * [AC2.8.5], because that is where it would otherwise be omitted.
 *
 * @param state What to render
 * @param onRetry Called when the guardian asks to retry
 * @param modifier Layout modifier
 */
@Composable
fun ProgressScreen(
    state: MarksUiState,
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_progress),
        modifier = modifier,
    ) {
        when (state) {
            MarksUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_PROGRESS_LOADING))

            is MarksUiState.ProgressLoaded -> {
                Text(
                    stringResource(
                        R.string.progress_title,
                        Numerals.freeText(state.childDisplayName),
                        Numerals.freeText(state.batchName),
                    ),
                    Modifier.testTag(TAG_PROGRESS_TITLE),
                    style = MaterialTheme.typography.titleMedium,
                )

                if (state.entries.isEmpty()) {
                    Text(
                        stringResource(R.string.progress_empty),
                        Modifier.testTag(TAG_PROGRESS_EMPTY),
                    )
                } else {
                    LazyColumn(Modifier.testTag(TAG_PROGRESS_LIST)) {
                        items(state.entries) { entry -> ProgressRowView(entry) }
                    }
                }
            }

            is MarksUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_PROGRESS_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_PROGRESS_RETRY),
                    ) {
                        Text(stringResource(R.string.progress_retry))
                    }
                }
            }

            else -> Unit
        }
    }
}

/**
 * One exam in the series.
 *
 * @param entry The exam and its result
 */
@Composable
private fun ProgressRowView(entry: ProgressRow) {
    Column(Modifier.fillMaxWidth().testTag(TAG_PROGRESS_ROW)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(Numerals.freeText(entry.examTitle))
            Text(Numerals.freeText(entry.dateLabel))
        }

        // The state is shown for EVERY entry, including an absence.
        Text(
            stringResource(MessageKeys.resolve(entry.stateLabel)),
            Modifier.testTag(TAG_PROGRESS_STATE),
        )

        // **The score only when one exists** [BR6.6]. No `?: 0` here:
        // an absence contributes no value to any trend, and plotting
        // it as zero shows a collapse that did not happen.
        entry.marks?.let { scored ->
            Text(
                Numerals.marks(scored.toBigDecimal(), entry.totalMarks),
                Modifier.testTag(TAG_PROGRESS_MARKS),
            )
        }
    }
}
