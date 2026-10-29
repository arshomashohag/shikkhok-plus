package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ExamRow
import com.shikkhokplus.app.feature.marks.MarksUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_EXAMS_LOADING: String = "exams_loading"

/** The batch name heading. */
const val TAG_EXAMS_TITLE: String = "exams_title"

/** The explanation shown when a batch has no exams. */
const val TAG_EXAMS_EMPTY: String = "exams_empty"

/** The list of exams. */
const val TAG_EXAMS_LIST: String = "exams_list"

/** One exam. */
const val TAG_EXAM_ROW: String = "exam_row"

/** How many seats have a mark, as the server counted them. */
const val TAG_EXAM_ENTERED_COUNT: String = "exam_entered_count"

/** The create-exam action. */
const val TAG_EXAMS_ADD: String = "exams_add"

/** The error message. */
const val TAG_EXAMS_ERROR: String = "exams_error"

/** The retry button. */
const val TAG_EXAMS_RETRY: String = "exams_retry"

/**
 * The teacher's exams for one batch [FR4.1].
 *
 * **This composable renders a [MarksUiState] and nothing else.** The
 * entered-of-total count is the **server's** — a `rows.count { ... }`
 * here would be the client deciding what counts as entered, and it
 * would be wrong the moment the list paginates.
 *
 * @param state What to render
 * @param onOpen Called with the exam the teacher tapped
 * @param onCreate Called when the teacher wants a new exam
 * @param onRetry Called when the teacher asks to retry
 * @param modifier Layout modifier
 */
@Composable
fun ExamListScreen(
    state: MarksUiState,
    onOpen: (ExamRow) -> Unit,
    onCreate: () -> Unit = {},
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_exam_list),
        modifier = modifier,
    ) {
        when (state) {
            MarksUiState.Idle -> Unit

            MarksUiState.Loading ->
                LogoLoader(Modifier.testTag(TAG_EXAMS_LOADING))

            is MarksUiState.ExamsEmpty -> {
                Text(state.batchName, Modifier.testTag(TAG_EXAMS_TITLE))
                Button(onClick = onCreate, modifier = Modifier.testTag(TAG_EXAMS_ADD)) {
                    Text(stringResource(R.string.exams_add))
                }
                Text(
                    stringResource(R.string.exams_empty),
                    Modifier.testTag(TAG_EXAMS_EMPTY),
                )
            }

            is MarksUiState.ExamsLoaded -> {
                Text(state.batchName, Modifier.testTag(TAG_EXAMS_TITLE))
                Button(onClick = onCreate, modifier = Modifier.testTag(TAG_EXAMS_ADD)) {
                    Text(stringResource(R.string.exams_add))
                }
                LazyColumn(Modifier.testTag(TAG_EXAMS_LIST)) {
                    items(state.exams, key = { it.examId }) { exam ->
                        ExamRowView(exam, onOpen)
                    }
                }
            }

            is MarksUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_EXAMS_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry, modifier = Modifier.testTag(TAG_EXAMS_RETRY)) {
                        Text(stringResource(R.string.exams_retry))
                    }
                }
            }

            // The other states belong to other screens in this feature.
            else -> Unit
        }
    }
}

/**
 * One exam.
 *
 * @param exam The exam to render
 * @param onOpen Called when the teacher taps it
 */
@Composable
private fun ExamRowView(exam: ExamRow, onOpen: (ExamRow) -> Unit) {
    Column(Modifier.fillMaxWidth().testTag(TAG_EXAM_ROW)) {
        TextButton(onClick = { onOpen(exam) }) {
            Text(Numerals.freeText(exam.title))
        }
        exam.subjectName?.let { Text(Numerals.freeText(it)) }
        Text(Numerals.freeText(exam.dateLabel))
        // Both numbers are the SERVER's. A numerator formatted against
        // a denominator the client computed would be a count nobody
        // computed.
        Text(
            stringResource(
                R.string.exam_entered_count,
                Numerals.count(exam.enteredCount),
                Numerals.count(exam.expectedCount),
            ),
            Modifier.testTag(TAG_EXAM_ENTERED_COUNT),
        )
    }
}
