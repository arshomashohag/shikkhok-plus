package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.format.displayDate
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.format.todayAsUtcMillis
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.ui.TAG_FORM_CANCEL
import com.shikkhokplus.app.core.ui.TAG_FORM_ERROR
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import com.shikkhokplus.app.core.ui.TAG_FORM_SUBMIT

/** The total-marks field. */
const val TAG_EXAM_TOTAL: String = "exam_total"

/** The button that opens the date picker. */
const val TAG_EXAM_DATE: String = "exam_date"

/** One subject chip. */
const val TAG_EXAM_SUBJECT: String = "exam_subject"

/** Shown when the batch's subjects could not be read. */
const val TAG_EXAM_SUBJECTS_FAILED: String = "exam_subjects_failed"

/** The largest total a teacher can type; the server has the final say. */
private const val MAX_TOTAL_DIGITS = 4

/**
 * Create an exam in one batch [BR4.1].
 *
 * **No artboard draws this form** -- T7's Exams tab draws only its "New
 * exam" button -- so it follows the batch and student forms: the same
 * field style, the error beside what was typed, and a submit that stays
 * disabled while saving. It is pure content; the route supplies the
 * scaffold and closes it only when the server has accepted the exam.
 *
 * **Format checks only** [layering rules]: a title, a whole-number
 * total of at least one, and a subject chosen. Whether the subject
 * belongs to the batch is the server's check.
 *
 * @param subjects The batch's subjects, or null while they load
 * @param onCreate Called with title, ISO date, total and subject key
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 * @param saving True while the write is in flight
 * @param error Why the last write failed, already resolved, or null
 * @param todayUtcMillis Today, as the date picker counts it; injected so
 *   a test does not depend on the clock
 * @param editing The exam being edited, or null to create one. An edit
 *   keeps the exam's subject, so no subject is offered and the key
 *   passed to [onCreate] is empty
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ExamCreateForm(
    subjects: List<SubjectOptionDto>?,
    onCreate: (String, String, Int, String) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
    todayUtcMillis: Long = todayAsUtcMillis(),
    editing: ExamFormValues? = null,
) {
    var title by remember { mutableStateOf(editing?.title.orEmpty()) }
    var total by remember { mutableStateOf(editing?.totalMarks?.toString().orEmpty()) }
    var dateMillis by remember { mutableStateOf(editing?.date?.let(::isoToUtcMillis) ?: todayUtcMillis) }
    var picking by remember { mutableStateOf(false) }
    var chosen by remember(subjects) {
        // One subject means there is nothing to choose: pre-select it
        // rather than make the teacher tap the only option.
        mutableStateOf(subjects?.singleOrNull()?.id)
    }

    if (subjects == null) {
        LogoLoader()
        return
    }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(
            value = title,
            onValueChange = { title = it },
            label = { Text(stringResource(R.string.exam_create_title)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_NAME),
        )

        OutlinedButton(
            onClick = { picking = true },
            modifier = Modifier.fillMaxWidth().testTag(TAG_EXAM_DATE),
        ) {
            Text(stringResource(R.string.exam_create_date, displayDate(dateMillis)))
        }

        OutlinedTextField(
            value = total,
            onValueChange = { total = it.filter(Char::isDigit).take(MAX_TOTAL_DIGITS) },
            label = { Text(stringResource(R.string.exam_create_total)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth().testTag(TAG_EXAM_TOTAL),
        )

        if (editing == null) SubjectChoice(subjects, chosen) { chosen = it }

        error?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_FORM_ERROR),
            )
        }

        ExamFormActions(
            submitLabel = stringResource(if (editing == null) R.string.exam_create_submit else R.string.exam_edit_save),
            submit = submitOf(title, total, dateMillis, if (editing == null) chosen else "").takeUnless { saving },
            onCreate = onCreate,
            onCancel = onCancel,
        )
    }

    if (picking) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = dateMillis)
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        picker.selectedDateMillis?.let { dateMillis = it }
                        picking = false
                    },
                ) { Text(stringResource(R.string.action_ok)) }
            },
            dismissButton = {
                TextButton(onClick = { picking = false }) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        ) { DatePicker(state = picker) }
    }
}

/**
 * What the exam form starts from when it edits.
 *
 * @property title The exam's title
 * @property date Its date, `yyyy-MM-dd`
 * @property totalMarks Its total
 */
data class ExamFormValues(
    val title: String,
    val date: String,
    val totalMarks: Int,
)

/**
 * The subject chips, or a plain line when the subjects failed to load.
 *
 * @param subjects The batch's subjects
 * @param chosen The chosen subject's key, or null
 * @param onChoose Called with a subject's key
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SubjectChoice(
    subjects: List<SubjectOptionDto>,
    chosen: String?,
    onChoose: (String) -> Unit,
) {
    Text(
        text = stringResource(R.string.exam_create_subject),
        style = MaterialTheme.typography.labelLarge,
    )
    if (subjects.isEmpty()) {
        // A batch always has a subject [AC2.1.1], so an empty list is
        // a failed read. Said plainly rather than shown as no choice.
        Text(
            text = stringResource(R.string.exam_create_subjects_failed),
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag(TAG_EXAM_SUBJECTS_FAILED),
        )
    } else {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            subjects.forEach { subject ->
                FilterChip(
                    selected = chosen == subject.id,
                    onClick = { onChoose(subject.id) },
                    label = { Text(subject.name) },
                    modifier = Modifier.testTag(TAG_EXAM_SUBJECT),
                )
            }
        }
    }
}

/**
 * The form's values ready to send, or null while one is missing.
 *
 * Format only: a title, a whole-number total of at least one, and a
 * subject key (empty when editing, where the subject stays).
 *
 * @param title The typed title
 * @param total The typed total
 * @param dateMillis The picked date
 * @param subjectId The chosen subject's key, or null
 * @return Title, ISO date, total and subject key, or null
 */
private fun submitOf(title: String, total: String, dateMillis: Long, subjectId: String?): ExamSubmission? {
    val totalMarks = total.toIntOrNull()?.takeIf { it >= 1 } ?: return null
    if (title.isBlank() || subjectId == null) return null
    return ExamSubmission(title.trim(), isoDate(dateMillis), totalMarks, subjectId)
}

/**
 * What the form sends.
 *
 * @property title The trimmed title
 * @property date The ISO date
 * @property totalMarks The total
 * @property subjectId The subject key, empty when editing
 */
private data class ExamSubmission(
    val title: String,
    val date: String,
    val totalMarks: Int,
    val subjectId: String,
)

/**
 * Submit and cancel.
 *
 * @param submitLabel The submit button's words
 * @param submit What to send, or null to keep submit disabled
 * @param onCreate Called with title, ISO date, total and subject key
 * @param onCancel Called when the teacher backs out
 */
@Composable
private fun ExamFormActions(
    submitLabel: String,
    submit: ExamSubmission?,
    onCreate: (String, String, Int, String) -> Unit,
    onCancel: () -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = { submit?.let { onCreate(it.title, it.date, it.totalMarks, it.subjectId) } },
            enabled = submit != null,
            modifier = Modifier.testTag(TAG_FORM_SUBMIT),
        ) {
            Text(submitLabel)
        }
        TextButton(onClick = onCancel, modifier = Modifier.testTag(TAG_FORM_CANCEL)) {
            Text(stringResource(R.string.action_cancel))
        }
    }
}
