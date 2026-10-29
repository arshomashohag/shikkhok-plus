package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ExamRow
import com.shikkhokplus.app.feature.marks.MarksUiState

/** One exam row. */
const val TAG_EXAM_ROW: String = "batch_exam_row"

/** An exam's "Enter marks" button. */
const val TAG_EXAM_ENTER: String = "batch_exam_enter"

/**
 * The Exams tab: exams grouped as the server says they stand — needing
 * marks, coming up, done.
 *
 * @param state The exams' state
 * @param onOpen Called with an exam id to enter or review marks
 * @param onRetry Called to read the exams again
 */
@Composable
fun ExamsTab(state: MarksUiState, onOpen: (String) -> Unit, onRetry: () -> Unit) {
    when (state) {
        is MarksUiState.ExamsLoaded -> ExamGroups(state.exams, onOpen)
        is MarksUiState.ExamsEmpty ->
            EmptyState(stringResource(R.string.batch_exams_empty), stringResource(R.string.batch_exams_empty_body))
        is MarksUiState.Failed ->
            ErrorCard(
                title = stringResource(R.string.batch_exams_failed),
                body = stringResource(MessageKeys.resolve(state.messageKey)),
                retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                onRetry = onRetry.takeIf { state.retryable },
            )
        else -> SkeletonList(rows = 3)
    }
}

/**
 * The three groups, in the board's order.
 *
 * @param exams Every exam, in the server's order
 * @param onOpen Called with an exam id
 */
@Composable
private fun ExamGroups(exams: List<ExamRow>, onOpen: (String) -> Unit) {
    val groups =
        listOf(
            R.string.batch_exams_needs_marks to exams.filter { it.state == "needs_marks" },
            R.string.batch_exams_coming to exams.filter { it.state == "upcoming" },
            R.string.batch_exams_done to exams.filter { it.state == "complete" }.asReversed(),
        ).filter { it.second.isNotEmpty() }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        groups.forEach { (title, rows) ->
            item {
                Text(
                    stringResource(title),
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            item {
                Column(
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
                ) {
                    rows.forEachIndexed { index, row ->
                        if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
                        ExamRowView(row, onOpen)
                    }
                }
            }
        }
        item { Column(Modifier.heightIn(min = 88.dp)) {} }
    }
}

/**
 * One exam: title, subject, date, out of, how far marking has got.
 *
 * @param row The exam
 * @param onOpen Called with its id
 */
@Composable
private fun ExamRowView(row: ExamRow, onOpen: (String) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable { onOpen(row.examId) }
            .heightIn(min = 64.dp)
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .testTag(TAG_EXAM_ROW),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(row.title), style = MaterialTheme.typography.titleMedium)
            Text(
                listOfNotNull(
                    row.subjectName?.let(Numerals::freeText),
                    row.dateLabel,
                    stringResource(R.string.batch_exam_out_of, Numerals.count(row.totalMarks)),
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        when (row.state) {
            "needs_marks" ->
                TonalButton(
                    stringResource(R.string.batch_enter_marks),
                    { onOpen(row.examId) },
                    Modifier.testTag(TAG_EXAM_ENTER),
                )
            "complete" ->
                Text(
                    stringResource(
                        R.string.batch_exam_entered,
                        Numerals.count(row.enteredCount),
                        Numerals.count(row.expectedCount),
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
        }
    }
}
