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
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ProgressRow
import com.shikkhokplus.app.feature.student.FamilyExam
import com.shikkhokplus.app.feature.student.FamilyTeacher
import com.shikkhokplus.app.feature.student.NextClass
import com.shikkhokplus.app.feature.student.PastClass
import com.shikkhokplus.app.feature.student.StudentBatchView

/** One past class, which opens its detail. */
const val TAG_FAMILY_CLASS: String = "family_class"

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
 * The Classes tab: the next class, then past classes newest first.
 *
 * @param view The batch
 * @param onOpen Called with a past class's session id
 */
@Composable
fun ColumnScope.ClassesTab(view: StudentBatchView, onOpen: (String) -> Unit) {
    val next = view.next
    if (next == null) {
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_NEXT_CLASS)) {
            Text(stringResource(R.string.student_no_next_class), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        NextClassHero(
            next,
            thenLine(view.following),
            withEnd = true,
            modifier = Modifier.testTag(TAG_STUDENT_NEXT_CLASS),
        )
    }

    Section(stringResource(R.string.family_past_classes))
    if (view.classes.isEmpty()) {
        Quiet(stringResource(R.string.student_topics_empty))
    } else {
        RowsCard {
            view.classes.forEachIndexed { index, past ->
                if (index > 0) InsetDivider()
                PastClassRow(past) { onOpen(past.sessionId) }
            }
        }
    }
}

/**
 * "Then Mon 19 Oct, Wed 21 Oct (moved to 6:00 pm)", or null with none.
 *
 * @param following The classes after the next
 * @return The line
 */
@Composable
private fun thenLine(following: List<NextClass>): String? {
    if (following.isEmpty()) return null
    val days =
        following.map { next ->
            if (next.moved) {
                stringResource(R.string.student_moved_to, dayLabel(next.date), displayTime(next.startTime))
            } else {
                dayLabel(next.date)
            }
        }
    return stringResource(R.string.student_then, days.joinToString(", "))
}

/**
 * One past class: the date and weekday in a column, then the subject
 * and what was covered, as the teacher typed it.
 *
 * @param past The class
 * @param onOpen Called to open it
 */
@Composable
private fun PastClassRow(past: PastClass, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(TAG_FAMILY_CLASS),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.width(52.dp)) {
            Text(shortDate(past.date), style = Emphasis)
            Quiet(dayLabel(past.date).substringBefore(" "))
        }
        Column(Modifier.weight(1f)) {
            past.subjectName?.let { Text(Numerals.freeText(it), style = Emphasis) }
            Text(
                past.topic?.let(Numerals::freeText) ?: stringResource(R.string.session_topic_unlogged),
                color = if (past.topic == null) MaterialTheme.colorScheme.onSurfaceVariant else Color.Unspecified,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/**
 * The Exams tab: upcoming, then done, each as the server grouped them.
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
    if (view.upcomingExams.isNotEmpty()) {
        Section(stringResource(R.string.student_coming_up))
        RowsCard {
            view.upcomingExams.forEachIndexed { index, exam ->
                if (index > 0) InsetDivider()
                ExamRowView(exam, result = null, tag = TAG_FAMILY_EXAM_UPCOMING) { onOpenDetail(exam.examId) }
            }
        }
    }
    if (view.doneExams.isNotEmpty()) {
        Section(stringResource(R.string.family_exams_done))
        RowsCard {
            view.doneExams.forEachIndexed { index, exam ->
                if (index > 0) InsetDivider()
                val result = view.results.firstOrNull { it.examId == exam.examId }
                ExamRowView(exam, result, tag = TAG_FAMILY_EXAM_DONE) { onOpenResult(exam.examId) }
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
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 22.sp)) { append(Numerals.count(marks)) }
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
