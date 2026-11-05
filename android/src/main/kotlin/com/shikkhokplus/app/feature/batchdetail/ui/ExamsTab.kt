package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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

/** "Draft · not published" on a marked exam not yet out to families. */
const val TAG_EXAM_DRAFT: String = "exam_draft"

/** One exam row. */
const val TAG_EXAM_ROW: String = "batch_exam_row"

/** An exam's "Enter marks" button. */
const val TAG_EXAM_ENTER: String = "batch_exam_enter"

/** "Cancelled" on an exam the teacher called off. */
const val TAG_EXAM_CANCELLED: String = "exam_cancelled"

/**
 * The Exams tab: exams grouped as the server says they stand — needing
 * marks, coming up, done — then the cancelled ones, which stay on the
 * tab they were scheduled on, flagged, and open read-only.
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
    // A cancelled exam leaves the working groups whatever its marking
    // state, so it never asks for marks.
    val on = exams.filterNot { it.cancelled }
    val groups =
        listOf(
            R.string.batch_exams_needs_marks to on.filter { it.state == "needs_marks" },
            R.string.batch_exams_coming to on.filter { it.state == "upcoming" },
            R.string.batch_exams_done to on.filter { it.state == "complete" }.asReversed(),
            R.string.exam_cancelled_chip to exams.filter { it.cancelled },
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
            // Marked but not yet out to families (decided 2026-11-05).
            if (row.state == "complete" && !row.published && !row.cancelled) {
                Text(
                    stringResource(R.string.batch_exam_draft),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.testTag(TAG_EXAM_DRAFT),
                )
            }
        }
        if (row.cancelled) {
            Text(
                stringResource(R.string.exam_cancelled_chip),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier =
                    Modifier
                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, MaterialTheme.shapes.small)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                        .testTag(TAG_EXAM_CANCELLED),
            )
            return@Row
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
