package com.shikkhokplus.app.feature.myexams.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayHeading
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.MyExamDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.myexams.ExaminerUiState
import com.shikkhokplus.app.feature.myexams.Loadable
import com.shikkhokplus.app.feature.myexams.MarksNotice
import com.shikkhokplus.app.feature.myexams.MyExamMarksUiState
import com.shikkhokplus.app.feature.myexams.STATE_ABSENT
import com.shikkhokplus.app.feature.myexams.STATE_JOINED_AFTER
import com.shikkhokplus.app.feature.myexams.STATE_NOT_ENTERED

/** The publish button. */
const val TAG_MY_EXAM_PUBLISH: String = "my_exam_publish"

/** The marks screen's refusal. */
const val TAG_MY_EXAM_FAILURE: String = "my_exam_failure"

/** The examiner control. */
const val TAG_EXAMINER: String = "examiner_control"

/**
 * Tag for one exam on My exams.
 *
 * @param examId The exam
 * @return The tag
 */
fun myExamTag(examId: String): String = "my_exam_$examId"

/**
 * Tag for one seat's save action.
 *
 * @param enrollmentId The seat
 * @return The tag
 */
fun myExamSaveTag(enrollmentId: String): String = "my_exam_save_$enrollmentId"

/**
 * Tag for one seat's absent action.
 *
 * @param enrollmentId The seat
 * @return The tag
 */
fun myExamAbsentTag(enrollmentId: String): String = "my_exam_absent_$enrollmentId"

/**
 * Tag for one examiner choice.
 *
 * @param memberId The member, or `none`
 * @return The tag
 */
fun examinerChoiceTag(memberId: String): String = "examiner_$memberId"

/**
 * The exams a centre asked me to mark, across every centre.
 *
 * @param state What to render
 * @param onOpen Opens one exam's marks
 * @param onRetry Reads again
 * @param modifier Layout modifier from the caller
 * @param bottomBar The lens's tab bar
 */
@Composable
fun MyExamsScreen(
    state: Loadable<List<MyExamDto>>,
    onOpen: (String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ScreenScaffold(title = stringResource(R.string.my_exams_title), modifier = modifier, bottomBar = bottomBar) {
        when (state) {
            Loadable.Loading -> SkeletonList(rows = 4)
            is Loadable.Failed -> Failure(state, onRetry)
            is Loadable.Loaded ->
                if (state.value.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.my_exams_title),
                        body = stringResource(R.string.my_exams_empty),
                    )
                } else {
                    state.value.forEach { ExamCard(it, onOpen) }
                }
        }
    }
}

@Composable
private fun ExamCard(exam: MyExamDto, onOpen: (String) -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(myExamTag(exam.examId)), onClick = { onOpen(exam.examId) }) {
        Text(
            "${Numerals.freeText(exam.title)} · ${Numerals.freeText(exam.subjectName)}",
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            listOf(
                Numerals.freeText(exam.batchName),
                Numerals.freeText(exam.centreName),
                dayHeading(exam.date),
                stringResource(
                    when {
                        exam.cancelled -> R.string.timetable_cancelled
                        exam.published -> R.string.my_exam_published
                        else -> R.string.my_exam_draft
                    },
                ),
            ).joinToString(" · "),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Failure(state: Loadable.Failed, onRetry: () -> Unit) {
    ErrorCard(
        title = stringResource(MessageKeys.resolve(state.messageKey)),
        body = null,
        retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
        onRetry = if (state.retryable) onRetry else null,
    )
}

/**
 * What the marks screen's controls call.
 *
 * @property onType Types one seat's mark
 * @property onSave Sends one seat's typed mark
 * @property onAbsent Records one seat absent
 * @property onPublish Publishes the results
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class MyExamMarksActions(
    val onType: (String, String) -> Unit = { _, _ -> },
    val onSave: (String) -> Unit = {},
    val onAbsent: (String) -> Unit = {},
    val onPublish: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * One exam's marks, as its examiner enters them: a number or absent per
 * seat, then publish. Names and results only.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MyExamMarksScreen(
    state: MyExamMarksUiState,
    actions: MyExamMarksActions,
    modifier: Modifier = Modifier,
) {
    val sheet = (state.sheet as? Loadable.Loaded)?.value
    ScreenScaffold(
        title = sheet?.exam?.title?.let(Numerals::freeText) ?: stringResource(R.string.my_exams_title),
        subtitle = sheet?.exam?.let { "${Numerals.freeText(it.batchName)} · ${Numerals.freeText(it.subjectName)}" },
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (val loaded = state.sheet) {
            Loadable.Loading -> SkeletonList(rows = 5)
            is Loadable.Failed -> Failure(loaded, actions.onRetry)
            is Loadable.Loaded -> {
                state.failureKey?.let {
                    Banner(
                        title = stringResource(MessageKeys.resolve(it)),
                        tone = BannerTone.ERROR,
                        modifier = Modifier.testTag(TAG_MY_EXAM_FAILURE),
                    )
                }
                state.notice?.let {
                    val text =
                        if (it == MarksNotice.PUBLISHED) R.string.my_exam_published_done else R.string.my_class_saved
                    Banner(title = stringResource(text))
                }
                loaded.value.results.forEach { row ->
                    MarkCard(row, loaded.value.exam.totalMarks, loaded.value.writable, state, actions)
                }
                if (state.canPublish) {
                    PrimaryButton(
                        text = stringResource(R.string.my_exam_publish),
                        onClick = actions.onPublish,
                        enabled = !state.saving,
                        modifier = Modifier.fillMaxWidth().testTag(TAG_MY_EXAM_PUBLISH),
                    )
                }
            }
        }
    }
}

@Composable
private fun MarkCard(
    row: ExamResultDto,
    total: Int,
    writable: Boolean,
    state: MyExamMarksUiState,
    actions: MyExamMarksActions,
) {
    ShikkhokCard {
        Text(Numerals.freeText(row.displayName), style = MaterialTheme.typography.titleMedium)
        Text(
            resultLine(row, total),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (writable && row.resultState != STATE_JOINED_AFTER) {
            val typed = state.typed[row.enrollmentId].orEmpty()
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ShikkhokTextField(
                    value = typed,
                    onValueChange = { actions.onType(row.enrollmentId, it) },
                    label = stringResource(R.string.my_exam_marks_label, Numerals.count(total)),
                    keyboardType = KeyboardType.Decimal,
                    modifier = Modifier.width(140.dp),
                )
                TextAction(
                    text = stringResource(R.string.my_exam_save),
                    onClick = { actions.onSave(row.enrollmentId) },
                    enabled = !state.saving && Numerals.parseAmount(typed) != null,
                    modifier = Modifier.testTag(myExamSaveTag(row.enrollmentId)),
                )
                TextAction(
                    text = stringResource(R.string.my_exam_absent),
                    onClick = { actions.onAbsent(row.enrollmentId) },
                    enabled = !state.saving,
                    modifier = Modifier.testTag(myExamAbsentTag(row.enrollmentId)),
                )
            }
        }
    }
}

@Composable
private fun resultLine(row: ExamResultDto, total: Int): String =
    when (row.resultState) {
        STATE_ABSENT -> stringResource(R.string.my_exam_absent)
        STATE_JOINED_AFTER -> stringResource(R.string.my_exam_joined_after)
        STATE_NOT_ENTERED -> stringResource(R.string.my_exam_not_entered)
        else -> row.marks?.let { "${Numerals.mark(it)} / ${Numerals.count(total)}" }.orEmpty()
    }

/**
 * Who marks a centre's exam, and changing it: nobody, or a live member.
 * Drawn on the exam's marks screen for a manager in a centre.
 *
 * @param state What to render
 * @param onChoose Names a member, or null for nobody
 * @param modifier Layout modifier from the caller
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ExaminerControl(
    state: ExaminerUiState,
    onChoose: (String?) -> Unit,
    modifier: Modifier = Modifier,
) {
    val exam = state.exam ?: return
    val enabled = !state.saving && !exam.cancelled
    Column(modifier.testTag(TAG_EXAMINER), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(R.string.examiner_label), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = exam.examinerMemberId == null,
                onClick = { onChoose(null) },
                enabled = enabled,
                label = { Text(stringResource(R.string.examiner_none)) },
                modifier = Modifier.testTag(examinerChoiceTag("none")),
            )
            state.members.forEach { member ->
                FilterChip(
                    selected = exam.examinerMemberId == member.memberId,
                    onClick = { onChoose(member.memberId) },
                    enabled = enabled,
                    label = { Text(Numerals.freeText(member.displayName)) },
                    modifier = Modifier.testTag(examinerChoiceTag(member.memberId)),
                )
            }
        }
        val fallback = if (state.changed) R.string.examiner_changed else R.string.examiner_help
        val note = state.failureKey?.let { stringResource(MessageKeys.resolve(it)) } ?: stringResource(fallback)
        Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
