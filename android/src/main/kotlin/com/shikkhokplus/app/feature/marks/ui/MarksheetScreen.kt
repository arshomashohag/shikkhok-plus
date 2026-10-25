package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.MarksUiState
import com.shikkhokplus.app.feature.marks.MarksheetComparison

/** Stable test identifiers. Not user-visible text. */
const val TAG_MARKSHEET_LOADING: String = "marksheet_loading"

/** The exam heading. */
const val TAG_MARKSHEET_TITLE: String = "marksheet_title"

/** The viewer's own mark. */
const val TAG_MARKSHEET_OWN: String = "marksheet_own"

/** The viewer's own result state. */
const val TAG_MARKSHEET_OWN_STATE: String = "marksheet_own_state"

/** The rank, present only when the server published a comparison. */
const val TAG_MARKSHEET_RANK: String = "marksheet_rank"

/** The batch average. */
const val TAG_MARKSHEET_AVERAGE: String = "marksheet_average"

/** The highest mark. */
const val TAG_MARKSHEET_HIGHEST: String = "marksheet_highest"

/** The banded distribution. */
const val TAG_MARKSHEET_BANDS: String = "marksheet_bands"

/** One published band. */
const val TAG_MARKSHEET_BAND: String = "marksheet_band"

/**
 * The notice shown when the server published no comparison.
 *
 * Present when and only when [MarksUiState.MarksheetLoaded.comparison]
 * is null, which is the server's decision [BR6.4].
 */
const val TAG_MARKSHEET_NO_COMPARISON: String = "marksheet_no_comparison"

// No tag for a toggle-off notice: the server does not distinguish
// that case from an unreachable seat, by design [BR5.4]. It renders
// through the error branch below. See the note in `MarksUiState`.

/** The error message. */
const val TAG_MARKSHEET_ERROR: String = "marksheet_error"

/** The retry button. */
const val TAG_MARKSHEET_RETRY: String = "marksheet_retry"

/**
 * The marksheet, as a student or guardian sees it [FR4.4, FR4.5].
 *
 * **This composable renders a [MarksUiState] and computes nothing.**
 * The rank, the average, the highest and the bands are all the
 * server's, and so is the decision to publish them at all — every one
 * of those is a **disclosure** decision rather than a formatting one
 * [BR6.2–BR6.5].
 *
 * **Never a list of other students' marks** [BR6.2]. In a batch of 8
 * to 20 students who sit together and compare marks, twelve
 * unattributed numbers are deanonymised by inference within a day, so
 * a row list would over-claim "anonymised" for a product under a
 * Families declaration. What this renders is the viewer's own mark,
 * named, plus aggregates.
 *
 * **Every published band holds at least three results**, merged
 * server-side until that holds [BR6.3]. The client never merges and
 * never decides whether a band is safe to show: a band of one IS a
 * named mark, with the name supplied by anyone who knows who is in the
 * batch.
 *
 * **The toggle being off renders no marksheet at all** [BR5.4] — not
 * an empty one, not one with marks hidden, because an empty marksheet
 * still discloses that exams exist and how many. It arrives as the
 * shared refusal rather than as a state of its own, because the server
 * will not say whether a hidden marksheet exists; see the note in
 * `MarksUiState`.
 *
 * @param state What to render
 * @param onRetry Called when the viewer asks to retry
 * @param modifier Layout modifier
 */
@Composable
fun MarksheetScreen(
    state: MarksUiState,
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when (state) {
            MarksUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_MARKSHEET_LOADING))

            is MarksUiState.MarksheetLoaded -> {
                Text(
                    Numerals.freeText(state.examTitle),
                    Modifier.testTag(TAG_MARKSHEET_TITLE),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    stringResource(MessageKeys.resolve(state.ownStateLabel)),
                    Modifier.testTag(TAG_MARKSHEET_OWN_STATE),
                )
                state.ownMarks?.let { own ->
                    Text(
                        stringResource(
                            R.string.marksheet_own,
                            Numerals.marks(own.toBigDecimal(), state.totalMarks),
                        ),
                        Modifier.testTag(TAG_MARKSHEET_OWN),
                    )
                }

                // **Present or absent as one unit** [BR6.4]. The
                // server withholds all four figures below five marked
                // results, and again while any seat is unmarked. The
                // client tests neither condition: it cannot see the
                // second at all, and testing the first would publish a
                // comparison the server deliberately withheld.
                val comparison = state.comparison
                if (comparison == null) {
                    Text(
                        stringResource(R.string.marksheet_no_comparison),
                        Modifier.testTag(TAG_MARKSHEET_NO_COMPARISON),
                    )
                } else {
                    ComparisonBody(comparison)
                }
            }

            is MarksUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_MARKSHEET_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_MARKSHEET_RETRY),
                    ) {
                        Text(stringResource(R.string.marksheet_retry))
                    }
                }
            }

            else -> Unit
        }
    }
}

/**
 * The four published figures.
 *
 * @param comparison The aggregates the server published
 */
@Composable
private fun ComparisonBody(comparison: MarksheetComparison) {
    Text(
        stringResource(
            R.string.marksheet_rank,
            Numerals.count(comparison.rank),
            Numerals.count(comparison.markedCount),
        ),
        Modifier.testTag(TAG_MARKSHEET_RANK),
    )
    // The server's own rendering of the average. Parsing and
    // reformatting it here would be lossy and would move the rounding
    // decision to the client.
    Text(
        stringResource(R.string.marksheet_average, Numerals.freeText(comparison.average)),
        Modifier.testTag(TAG_MARKSHEET_AVERAGE),
    )
    Text(
        stringResource(R.string.marksheet_highest, Numerals.count(comparison.highest)),
        Modifier.testTag(TAG_MARKSHEET_HIGHEST),
    )

    Column(
        Modifier.fillMaxWidth().testTag(TAG_MARKSHEET_BANDS),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        for (band in comparison.bands) {
            Row(
                Modifier.fillMaxWidth().testTag(TAG_MARKSHEET_BAND),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(Numerals.freeText(band.rangeLabel))
                Text(Numerals.count(band.count))
            }
        }
    }
}
