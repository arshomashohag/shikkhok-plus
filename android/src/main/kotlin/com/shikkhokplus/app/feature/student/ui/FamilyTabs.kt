package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.MonthCalendar
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.classcalendar.ui.ClassPickList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ProgressRow
import com.shikkhokplus.app.feature.student.FamilyExam
import com.shikkhokplus.app.feature.student.FamilyTeacher
import com.shikkhokplus.app.feature.student.StudentBatchView

/** One upcoming exam, which opens its detail. */
const val TAG_FAMILY_EXAM_UPCOMING: String = "family_exam_upcoming"

/** One done exam, which opens its marksheet. */
const val TAG_FAMILY_EXAM_DONE: String = "family_exam_done"

/** One notice, which opens its detail. */
const val TAG_FAMILY_NOTICE: String = "family_notice"

/** The teacher's name. */
const val TAG_FAMILY_TEACHER_NAME: String = "family_teacher_name"

/** The teacher's initials, shown when they gave a name. */
const val TAG_FAMILY_TEACHER_INITIALS: String = "family_teacher_initials"

/** The generic person mark, shown when they did not. */
const val TAG_FAMILY_TEACHER_ICON: String = "family_teacher_icon"

/** One subject the teacher teaches. */
const val TAG_FAMILY_TEACHER_SUBJECT: String = "family_teacher_subject"

/**
 * The Classes tab: the batch's month as a calendar, each day as the
 * server decided it. A day with one class opens it; a day with several
 * asks which first.
 *
 * @param calendar The month's state
 * @param onPickMonth Called with the month the reader moved to
 * @param onOpen Called with a class to open
 * @param onRetry Called to read the month again
 */
@Composable
fun ColumnScope.ClassesTab(
    calendar: ClassCalendarUiState,
    onPickMonth: (YearMonth) -> Unit,
    onOpen: (CalendarClassUi) -> Unit,
    onRetry: () -> Unit,
) {
    var choosing by remember { mutableStateOf<List<CalendarClassUi>?>(null) }
    when (calendar) {
        ClassCalendarUiState.Idle, ClassCalendarUiState.Loading -> SkeletonList(rows = 4)
        is ClassCalendarUiState.Failed ->
            ErrorCard(
                title = stringResource(R.string.batch_classes_failed),
                body = stringResource(MessageKeys.resolve(calendar.messageKey)),
                retryLabel = stringResource(R.string.roster_retry).takeIf { calendar.retryable },
                onRetry = onRetry.takeIf { calendar.retryable },
            )
        is ClassCalendarUiState.Loaded ->
            MonthCalendar(
                year = calendar.view.month.year,
                month = calendar.view.month.month,
                days = calendar.view.days,
                firstMonth = calendar.view.firstMonth,
                lastMonth = calendar.view.lastMonth,
                onPickMonth = onPickMonth,
                onDay = { day ->
                    when (day.classes.size) {
                        0 -> Unit
                        1 -> onOpen(day.classes.single())
                        else -> choosing = day.classes
                    }
                },
                today = calendar.view.today,
            )
    }
    choosing?.let { classes ->
        ClassPickList(
            classes,
            onPick = {
                choosing = null
                onOpen(it)
            },
            onDismiss = { choosing = null },
        )
    }
}

/**
 * The Exams tab: results, then upcoming, each as the server grouped them.
 *
 * A done exam opens its marksheet; an upcoming one opens its detail.
 *
 * @param view The batch
 * @param onOpenResult Called with a done exam's id
 * @param onOpenDetail Called with an upcoming exam's id
 */
@Composable
fun ColumnScope.ExamsTab(view: StudentBatchView, onOpenResult: (String) -> Unit, onOpenDetail: (String) -> Unit) {
    if (view.upcomingExams.isEmpty() && view.doneExams.isEmpty()) {
        Quiet(stringResource(R.string.student_results_empty))
        return
    }
    // **Results first, then what is coming** (S2): a student opens the
    // tab to see how the last test went far more often than to check
    // the next date.
    if (view.doneExams.isNotEmpty()) {
        Section(stringResource(R.string.student_results))
        RowsCard {
            view.doneExams.forEachIndexed { index, exam ->
                if (index > 0) InsetDivider()
                val result = view.results.firstOrNull { it.examId == exam.examId }
                ExamRowView(exam, result, tag = TAG_FAMILY_EXAM_DONE) { onOpenResult(exam.examId) }
            }
        }
    }
    if (view.upcomingExams.isNotEmpty()) {
        Section(stringResource(R.string.student_coming_up))
        RowsCard {
            view.upcomingExams.forEachIndexed { index, exam ->
                if (index > 0) InsetDivider()
                ExamRowView(exam, result = null, tag = TAG_FAMILY_EXAM_UPCOMING) { onOpenDetail(exam.examId) }
            }
        }
    }
}

/**
 * One exam: title, subject, date, out of, and the seat's mark when the
 * exam is done and the server sent one.
 *
 * @param exam The exam
 * @param result The seat's result in it, or null
 * @param tag The test tag
 * @param onOpen Called to open it
 */
@Composable
private fun ExamRowView(exam: FamilyExam, result: ProgressRow?, tag: String, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                Numerals.freeText(exam.title),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
            )
            Quiet(
                listOf(
                    Numerals.freeText(exam.subjectName),
                    shortDate(exam.date),
                    stringResource(R.string.batch_exam_out_of, Numerals.count(exam.totalMarks)),
                ).joinToString(" · "),
            )
        }
        result?.let { MarkText(it) }
    }
}

/**
 * The mark, or the state that stands in for one: an absence is shown
 * as one and never as zero [BR6.6].
 *
 * @param row The result
 */
@Composable
private fun MarkText(row: ProgressRow) {
    val marks = row.marks
    if (marks == null) {
        Quiet(stringResource(MessageKeys.resolve(row.stateLabel)))
    } else {
        // The title step, so the mark reads larger than its "/total".
        val markSize = MaterialTheme.typography.titleLarge.fontSize
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = markSize)) {
                    append(Numerals.mark(marks))
                }
                append(stringResource(R.string.student_out_of, Numerals.count(row.totalMarks)))
            },
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

/**
 * The Notices tab: every notice, newest first, verbatim.
 *
 * @param view The batch
 * @param onOpen Called with a notice id
 */
@Composable
fun ColumnScope.NoticesTab(view: StudentBatchView, onOpen: (String) -> Unit) {
    if (view.notices.isEmpty()) {
        Quiet(stringResource(R.string.family_notices_empty))
        return
    }
    RowsCard {
        view.notices.forEachIndexed { index, notice ->
            if (index > 0) InsetDivider()
            Column(
                Modifier
                    .fillMaxWidth()
                    .clickable { onOpen(notice.noticeId) }
                    .padding(horizontal = 16.dp, vertical = 12.dp)
                    .testTag(TAG_FAMILY_NOTICE),
            ) {
                Text(Numerals.freeText(notice.body), maxLines = 3, overflow = TextOverflow.Ellipsis)
                Quiet(ago(notice.postedAt))
            }
        }
    }
}

/**
 * The Teacher tab: initials, name and subjects. No phone, no address.
 *
 * @param teacher The teacher
 */
@Composable
fun ColumnScope.TeacherTab(teacher: FamilyTeacher) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(48.dp).background(MaterialTheme.colorScheme.primary, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            val initials = teacher.initials
            if (initials == null) {
                Icon(
                    painterResource(R.drawable.ic_person),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.testTag(TAG_FAMILY_TEACHER_ICON),
                )
            } else {
                Text(
                    initials,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.testTag(TAG_FAMILY_TEACHER_INITIALS),
                )
            }
        }
        Text(
            teacher.displayName?.let(Numerals::freeText) ?: stringResource(R.string.family_teacher_unnamed),
            style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
            modifier = Modifier.testTag(TAG_FAMILY_TEACHER_NAME),
        )
    }
    Section(stringResource(R.string.family_teacher_subjects))
    if (teacher.subjects.isEmpty()) {
        Quiet(stringResource(R.string.family_teacher_no_subjects))
    } else {
        RowsCard {
            teacher.subjects.forEachIndexed { index, subject ->
                if (index > 0) InsetDivider()
                Text(
                    Numerals.freeText(subject),
                    modifier = Modifier.fillMaxWidth().padding(16.dp).testTag(TAG_FAMILY_TEACHER_SUBJECT),
                )
            }
        }
    }
}
