package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.core.ui.scheduleSummary
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ProgressRow
import com.shikkhokplus.app.feature.student.StudentBatchUiState
import com.shikkhokplus.app.feature.student.StudentBatchView

/** The loading placeholder. */
const val TAG_STUDENT_BATCH_LOADING: String = "student_batch_loading"

/** The next-class card. */
const val TAG_STUDENT_NEXT_CLASS: String = "student_next_class"

/** One result row, which opens its marksheet. */
const val TAG_STUDENT_RESULT: String = "student_result"

/** One topic row. */
const val TAG_STUDENT_TOPIC: String = "student_topic"

/** One notice. */
const val TAG_STUDENT_NOTICE: String = "student_notice"

/** The fee-history link. */
const val TAG_STUDENT_FEES: String = "student_fees"

/** The failure message. */
const val TAG_STUDENT_BATCH_ERROR: String = "student_batch_error"

/**
 * S2: one batch from the student's side.
 *
 * Next class, the latest fee, results, the latest notice and the
 * topics covered. Everything shown is what the server decided; the
 * screen formats and decides nothing [TC-9].
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onOpenExam Called with an exam id when a result is tapped
 * @param onOpenFees Called to open the fee history
 * @param onRetry Called when the student asks to try again
 * @param modifier The layout modifier
 */
@Composable
fun StudentBatchScreen(
    state: StudentBatchUiState,
    onBack: () -> Unit,
    onOpenExam: (String) -> Unit,
    onOpenFees: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val title = (state as? StudentBatchUiState.Loaded)?.view?.batch?.batchName?.let(Numerals::freeText)
    ScreenScaffold(
        title = title ?: stringResource(R.string.my_batches_title),
        modifier = modifier,
        onBack = onBack,
    ) {
        when (state) {
            StudentBatchUiState.Loading -> LogoLoader(Modifier.testTag(TAG_STUDENT_BATCH_LOADING))
            is StudentBatchUiState.Loaded -> BatchBody(state.view, onOpenExam, onOpenFees)
            is StudentBatchUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_STUDENT_BATCH_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry) { Text(stringResource(R.string.roster_retry)) }
                }
            }
        }
    }
}

/**
 * The loaded batch, top to bottom as S2 orders it.
 *
 * @param view The batch
 * @param onOpenExam Called with an exam id
 * @param onOpenFees Called to open the fee history
 */
@Composable
private fun BatchBody(
    view: StudentBatchView,
    onOpenExam: (String) -> Unit,
    onOpenFees: () -> Unit,
) {
    val byline =
        listOfNotNull(
            view.batch.teacherName?.let(Numerals::freeText),
            scheduleSummary(view.batch.schedule).ifEmpty { null },
        )
    if (byline.isNotEmpty()) {
        Text(
            byline.joinToString(" · "),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    ShikkhokCard(Modifier.testTag(TAG_STUDENT_NEXT_CLASS)) {
        Text(stringResource(R.string.student_next_class), style = MaterialTheme.typography.labelSmall)
        val date = view.nextClassDate
        Text(
            if (date == null) {
                stringResource(R.string.student_no_next_class)
            } else {
                listOfNotNull(date, view.nextClassStart?.let(::displayTime)).joinToString(", ")
            },
            fontWeight = FontWeight.SemiBold,
        )
    }

    view.batch.fee?.let { fee ->
        ShikkhokCard(onClick = onOpenFees, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
            FeeSummary(fee)
            Text(
                stringResource(R.string.student_fee_due, fee.dueDate, Numerals.money(fee.outstanding)),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    } ?: TextButton(onClick = onOpenFees, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
        Text(stringResource(R.string.screen_title_fee_history))
    }

    Section(stringResource(R.string.student_results))
    if (view.results.isEmpty()) {
        Text(stringResource(R.string.student_results_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    view.results.asReversed().forEach { ResultRow(it, onOpen = { onOpenExam(it.examId) }) }

    view.notices.firstOrNull()?.let { notice ->
        Section(stringResource(R.string.student_latest_notice))
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_NOTICE)) {
            Text(Numerals.freeText(notice.body))
            Text(
                notice.postedAt.take(DATE_LENGTH),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    Section(stringResource(R.string.student_topics))
    if (view.topics.isEmpty()) {
        Text(stringResource(R.string.student_topics_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    view.topics.forEach { topic ->
        Row(
            Modifier.fillMaxWidth().testTag(TAG_STUDENT_TOPIC),
            horizontalArrangement = Arrangement.spacedBy(Spacer),
        ) {
            Text(topic.date, style = MaterialTheme.typography.labelLarge)
            Text(Numerals.freeText(topic.topic))
        }
    }
}

/**
 * A section heading.
 *
 * @param text The heading
 */
@Composable
private fun Section(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium)
}

/**
 * One result: the exam, its date and the student's own mark.
 *
 * @param row The result
 * @param onOpen Called to open its marksheet
 */
@Composable
private fun ResultRow(row: ProgressRow, onOpen: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onOpen).testTag(TAG_STUDENT_RESULT),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text("${Numerals.freeText(row.examTitle)} · ${row.dateLabel}")
        Text(
            // No mark is not zero: an absence shows as one [BR6.6].
            row.marks?.let { Numerals.marks(it.toBigDecimal(), row.totalMarks) }
                ?: stringResource(MessageKeys.resolve(row.stateLabel)),
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** `yyyy-MM-dd` out of a timestamp. */
private const val DATE_LENGTH = 10

/** The gap between a topic's date and its text. */
private val Spacer = com.shikkhokplus.app.core.designsystem.Spacing.tight
