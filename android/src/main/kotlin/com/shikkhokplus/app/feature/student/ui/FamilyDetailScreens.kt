package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarMark
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.student.FamilyExam
import com.shikkhokplus.app.feature.student.FamilyExamUiState
import com.shikkhokplus.app.feature.student.NoticeRow

/** A detail's heading. */
const val TAG_FAMILY_DETAIL_TITLE: String = "family_detail_title"

/** A detail whose item is no longer in the batch. */
const val TAG_FAMILY_DETAIL_MISSING: String = "family_detail_missing"

/** The topic of a class. */
const val TAG_FAMILY_DETAIL_TOPIC: String = "family_detail_topic"

/** The attendance line of a class. */
const val TAG_FAMILY_DETAIL_ATTENDANCE: String = "family_detail_attendance"

/** The teacher's notes on a class. */
const val TAG_FAMILY_DETAIL_NOTES: String = "family_detail_notes"

/** One topic of an exam. */
const val TAG_FAMILY_DETAIL_EXAM_TOPIC: String = "family_detail_exam_topic"

/** The body of a notice. */
const val TAG_FAMILY_DETAIL_NOTICE_BODY: String = "family_detail_notice_body"

/** The loading placeholder of an exam. */
const val TAG_FAMILY_DETAIL_LOADING: String = "family_detail_loading"

/** The failure message of an exam. */
const val TAG_FAMILY_DETAIL_ERROR: String = "family_detail_error"

/**
 * One class, read-only: when, what the teacher wrote, and this seat's
 * mark. Nothing here can be edited by a family.
 *
 * @param clazz The class from the loaded month, or null when it is not there
 * @param onBack Called to return to the calendar
 * @param modifier The layout modifier
 * @param loading Whether the month is still being read
 */
@Composable
fun ClassDetailScreen(
    clazz: CalendarClassUi?,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    loading: Boolean = false,
) {
    ScreenScaffold(title = stringResource(R.string.family_class_title), modifier = modifier, onBack = onBack) {
        if (clazz == null) {
            if (loading) LogoLoader(Modifier.testTag(TAG_FAMILY_DETAIL_LOADING)) else Missing()
            return@ScreenScaffold
        }
        Heading(clazz.subjectName?.let(Numerals::freeText) ?: dayLabel(clazz.date))
        Quiet("${dayLabel(clazz.date)} · ${displayTime(clazz.startTime.take(HHMM))}")
        val planned = clazz.state == CalendarState.UPCOMING
        Section(stringResource(if (planned) R.string.family_planned_topics else R.string.classday_topics_covered))
        val topic = clazz.topic?.takeIf { it.isNotBlank() }
        Text(
            topic?.let(Numerals::freeText) ?: stringResource(R.string.session_topic_unlogged),
            color = if (topic == null) MaterialTheme.colorScheme.onSurfaceVariant else Color.Unspecified,
            modifier = Modifier.testTag(TAG_FAMILY_DETAIL_TOPIC),
        )
        clazz.notes?.takeIf { it.isNotBlank() }?.let {
            Section(stringResource(R.string.family_class_notes))
            Text(Numerals.freeText(it), modifier = Modifier.testTag(TAG_FAMILY_DETAIL_NOTES))
        }
        Section(stringResource(R.string.family_attendance))
        Text(
            stringResource(markLabel(clazz.mark)),
            modifier = Modifier.testTag(TAG_FAMILY_DETAIL_ATTENDANCE),
        )
    }
}

/**
 * The words for a seat's standing in a class.
 *
 * @param mark The server's mark, or null when it sent none or one this build does not know
 * @return The string resource
 */
internal fun markLabel(mark: CalendarMark?): Int =
    when (mark) {
        CalendarMark.PRESENT -> R.string.family_present
        CalendarMark.ABSENT -> R.string.family_absent
        CalendarMark.NOT_ENROLLED -> R.string.family_not_enrolled_then
        CalendarMark.NOT_MARKED, null -> R.string.family_not_marked
    }

private const val HHMM = 5

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
