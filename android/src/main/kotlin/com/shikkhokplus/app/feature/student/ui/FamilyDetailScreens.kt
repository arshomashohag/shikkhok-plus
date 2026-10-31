package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.student.FamilyExam
import com.shikkhokplus.app.feature.student.FamilyExamUiState
import com.shikkhokplus.app.feature.student.NoticeRow
import com.shikkhokplus.app.feature.student.PastClass

/** A detail's heading. */
const val TAG_FAMILY_DETAIL_TITLE: String = "family_detail_title"

/** A detail whose item is no longer in the batch. */
const val TAG_FAMILY_DETAIL_MISSING: String = "family_detail_missing"

/** The topic of a class. */
const val TAG_FAMILY_DETAIL_TOPIC: String = "family_detail_topic"

/** The attendance line of a class. */
const val TAG_FAMILY_DETAIL_ATTENDANCE: String = "family_detail_attendance"

/** One topic of an exam. */
const val TAG_FAMILY_DETAIL_EXAM_TOPIC: String = "family_detail_exam_topic"

/** The body of a notice. */
const val TAG_FAMILY_DETAIL_NOTICE_BODY: String = "family_detail_notice_body"

/** The loading placeholder of an exam. */
const val TAG_FAMILY_DETAIL_LOADING: String = "family_detail_loading"

/** The failure message of an exam. */
const val TAG_FAMILY_DETAIL_ERROR: String = "family_detail_error"

/**
 * One past class: when, what it taught, what was covered and whether
 * the seat attended.
 *
 * @param past The class, or null when it is not in the batch any more
 * @param onBack Called to return to the batch
 * @param modifier The layout modifier
 */
@Composable
fun ClassDetailScreen(past: PastClass?, onBack: () -> Unit, modifier: Modifier = Modifier) {
    ScreenScaffold(title = stringResource(R.string.family_class_title), modifier = modifier, onBack = onBack) {
        if (past == null) {
            Missing()
            return@ScreenScaffold
        }
        Heading(past.subjectName?.let(Numerals::freeText) ?: dayLabel(past.date))
        Quiet("${dayLabel(past.date)} · ${displayTime(past.startTime)}")
        Section(stringResource(R.string.topic_label))
        Text(
            past.topic?.let(Numerals::freeText) ?: stringResource(R.string.session_topic_unlogged),
            modifier = Modifier.testTag(TAG_FAMILY_DETAIL_TOPIC),
        )
        Section(stringResource(R.string.family_attendance))
        Text(
            stringResource(
                when (past.present) {
                    true -> R.string.family_present
                    false -> R.string.family_absent
                    null -> R.string.family_not_marked
                },
            ),
            modifier = Modifier.testTag(TAG_FAMILY_DETAIL_ATTENDANCE),
        )
    }
}

/**
 * One exam: its subject, date, marks and the topics it covers.
 *
 * @param state The exam's state
 * @param onBack Called to return to the batch
 * @param onRetry Called when the reader asks to try again
 * @param modifier The layout modifier
 */
@Composable
fun ExamDetailScreen(
    state: FamilyExamUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.family_exam_title), modifier = modifier, onBack = onBack) {
        when (state) {
            FamilyExamUiState.Loading -> LogoLoader(Modifier.testTag(TAG_FAMILY_DETAIL_LOADING))
            is FamilyExamUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_FAMILY_DETAIL_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry) { Text(stringResource(R.string.roster_retry)) }
                }
            }
            is FamilyExamUiState.Loaded -> ExamBody(state.exam)
        }
    }
}

/**
 * The loaded exam.
 *
 * @param exam The exam
 */
@Composable
private fun ExamBody(exam: FamilyExam) {
    Heading(Numerals.freeText(exam.title))
    Quiet(
        listOf(
            Numerals.freeText(exam.subjectName),
            dayLabel(exam.date),
            stringResource(R.string.batch_exam_out_of, Numerals.count(exam.totalMarks)),
        ).joinToString(" · "),
    )
    Section(stringResource(R.string.family_exam_topics))
    if (exam.topics.isEmpty()) {
        Quiet(stringResource(R.string.family_exam_no_topics))
    } else {
        RowsCard {
            exam.topics.forEachIndexed { index, topic ->
                if (index > 0) InsetDivider()
                Text(
                    Numerals.freeText(topic),
                    modifier = Modifier.fillMaxWidth().padding(16.dp).testTag(TAG_FAMILY_DETAIL_EXAM_TOPIC),
                )
            }
        }
    }
}

/**
 * One notice, in full and verbatim.
 *
 * @param notice The notice, or null when it is not in the batch any more
 * @param onBack Called to return to the batch
 * @param modifier The layout modifier
 */
@Composable
fun NoticeDetailScreen(notice: NoticeRow?, onBack: () -> Unit, modifier: Modifier = Modifier) {
    ScreenScaffold(title = stringResource(R.string.family_notice_title), modifier = modifier, onBack = onBack) {
        if (notice == null) {
            Missing()
            return@ScreenScaffold
        }
        Text(Numerals.freeText(notice.body), modifier = Modifier.testTag(TAG_FAMILY_DETAIL_NOTICE_BODY))
        Quiet(
            listOfNotNull(ago(notice.postedAt), stringResource(R.string.family_notice_edited).takeIf { notice.edited })
                .joinToString(" · "),
        )
    }
}

/** The line shown when the item has gone from the batch. */
@Composable
private fun Missing() {
    Text(
        stringResource(R.string.family_detail_missing),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.testTag(TAG_FAMILY_DETAIL_MISSING),
    )
}

/**
 * A detail's heading.
 *
 * @param text The heading
 */
@Composable
private fun Heading(text: String) {
    Column {
        Text(
            text,
            style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
            modifier = Modifier.testTag(TAG_FAMILY_DETAIL_TITLE),
        )
    }
}
