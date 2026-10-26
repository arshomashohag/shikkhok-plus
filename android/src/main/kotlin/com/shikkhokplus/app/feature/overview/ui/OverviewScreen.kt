package com.shikkhokplus.app.feature.overview.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.overview.EarningsPoint
import com.shikkhokplus.app.feature.overview.NextExam
import com.shikkhokplus.app.feature.overview.OverviewUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_OVERVIEW_LOADING: String = "overview_loading"

/** This month's earnings figure. Never absent. */
const val TAG_OVERVIEW_EARNINGS: String = "overview_earnings"

/** The trend block. Absent entirely under two months of history. */
const val TAG_OVERVIEW_TREND: String = "overview_trend"

/** One month in the trend. */
const val TAG_OVERVIEW_TREND_ROW: String = "overview_trend_row"

/** The next-exam block, when one is scheduled. */
const val TAG_OVERVIEW_EXAM: String = "overview_exam"

/** The defined empty state shown when nothing is scheduled. */
const val TAG_OVERVIEW_NO_EXAM: String = "overview_no_exam"

/** The error message. */
const val TAG_OVERVIEW_ERROR: String = "overview_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_OVERVIEW_RETRY: String = "overview_retry"

/**
 * The teacher overview: this month, the trend, and the next exam.
 *
 * **Three independent blocks, each able to be absent without the
 * others** — and the three absences are different things, decided by
 * the mapper and merely rendered here:
 *
 * - earnings is **never absent**, because zero is a value;
 * - the trend block is **omitted entirely** under two months, rather
 *   than drawn as an empty frame;
 * - the exam block becomes a **defined empty state**, not a failure.
 *
 * **The trend renders as a list of months with existing Compose
 * primitives.** No charting library: a new dependency on a
 * Families-track app has to be checked against the forbidden-identifier
 * set before it is added, and a readable month-by-month list answers
 * "how am I doing" without one.
 *
 * @param state What to render
 * @param onRetry Invoked when the teacher asks to try again
 * @param modifier The layout modifier
 */
@Composable
fun OverviewScreen(
    state: OverviewUiState,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.screen_title_overview),
        modifier = modifier,
    ) {
        when (state) {
            OverviewUiState.Idle -> Unit

            OverviewUiState.Loading ->
                CircularProgressIndicator(
                    modifier = Modifier.testTag(TAG_OVERVIEW_LOADING),
                )

            is OverviewUiState.Loaded -> {
                EarningsBlock(state.thisMonth)
                // **`?.let`, not `.orEmpty()`.** Null means under two
                // months of history and the block is omitted; an empty
                // list would be a different claim, and rendering one as
                // the other is the defect this nullability exists to
                // prevent.
                state.trend?.let { TrendBlock(it) }
                ExamBlock(state.nextExam)
            }

            is OverviewUiState.Failed -> {
                Text(
                    text = stringResource(MessageKeys.resolve(state.messageKey)),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag(TAG_OVERVIEW_ERROR),
                )
                if (state.retryable) {
                    TextButton(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_OVERVIEW_RETRY),
                    ) {
                        Text(stringResource(R.string.overview_retry))
                    }
                }
            }
        }
    }
}

/**
 * This month's earnings, which are always shown.
 *
 * **The densest short string this unit renders**: a money amount in
 * Bangla numerals under a long Bangla label, on the screen a teacher
 * opens most. It is the first row of the Bangla layout check for that
 * reason.
 *
 * @param point The month and what arrived in it
 */
@Composable
private fun EarningsBlock(point: EarningsPoint) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.overview_earnings_label),
            style = MaterialTheme.typography.labelLarge,
        )
        Text(
            // A zero month renders "৳0", which is a figure. There is no
            // branch here turning it into "no data": that would tell a
            // teacher their records are missing when they are complete.
            text = Numerals.money(point.received),
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.testTag(TAG_OVERVIEW_EARNINGS),
        )
    }
}

/**
 * The monthly series, in the order the server sent it.
 *
 * Reached only when the server supplied two or more months, so there is
 * no "not enough data" branch inside it — that decision was made by the
 * caller, from a null.
 *
 * @param points The months, already ascending
 */
@Composable
private fun TrendBlock(points: List<EarningsPoint>) {
    Column(
        modifier = Modifier.testTag(TAG_OVERVIEW_TREND),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text = stringResource(R.string.overview_trend_label),
            style = MaterialTheme.typography.labelLarge,
        )
        // Rendered in the order given. Sorting here would be the client
        // deciding a domain list's order.
        points.forEach { point ->
            Row(
                modifier = Modifier.fillMaxWidth().testTag(TAG_OVERVIEW_TREND_ROW),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = point.period,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    text = Numerals.money(point.received),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            HorizontalDivider()
        }
    }
}

/**
 * The next exam, or the defined empty state.
 *
 * @param exam The exam, or null when nothing is scheduled
 */
@Composable
private fun ExamBlock(exam: NextExam?) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.overview_next_exam_label),
            style = MaterialTheme.typography.labelLarge,
        )
        if (exam == null) {
            // **A sentence, not a blank.** A teacher between terms is
            // told nothing is scheduled rather than shown an absence
            // they must interpret.
            Text(
                text = stringResource(R.string.overview_no_exam),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_OVERVIEW_NO_EXAM),
            )
            return@Column
        }
        Column(modifier = Modifier.testTag(TAG_OVERVIEW_EXAM)) {
            Text(
                text = exam.title,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = "${exam.batchName} · ${exam.subjectName}",
                style = MaterialTheme.typography.bodySmall,
            )
            Text(
                // The server's own count. Recomputing it from the date
                // would use the device clock.
                text =
                    stringResource(
                        R.string.overview_days_remaining,
                        Numerals.count(exam.daysRemaining),
                    ),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
