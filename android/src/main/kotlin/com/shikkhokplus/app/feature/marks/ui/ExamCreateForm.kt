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
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.ui.TAG_FORM_CANCEL
import com.shikkhokplus.app.core.ui.TAG_FORM_ERROR
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import com.shikkhokplus.app.core.ui.TAG_FORM_SUBMIT
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

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
) {
    var title by remember { mutableStateOf("") }
    var total by remember { mutableStateOf("") }
    var dateMillis by remember { mutableStateOf(todayUtcMillis) }
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
                        onClick = { chosen = subject.id },
                        label = { Text(subject.name) },
                        modifier = Modifier.testTag(TAG_EXAM_SUBJECT),
                    )
                }
            }
        }

        error?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_FORM_ERROR),
            )
        }

        val totalMarks = total.toIntOrNull()
        val subjectId = chosen
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    if (totalMarks != null && subjectId != null) {
                        onCreate(title.trim(), isoDate(dateMillis), totalMarks, subjectId)
                    }
                },
                enabled =
                    !saving &&
                        title.isNotBlank() &&
                        totalMarks != null &&
                        totalMarks >= 1 &&
                        subjectId != null,
                modifier = Modifier.testTag(TAG_FORM_SUBMIT),
            ) {
                Text(stringResource(R.string.exam_create_submit))
            }
            TextButton(onClick = onCancel, modifier = Modifier.testTag(TAG_FORM_CANCEL)) {
                Text(stringResource(R.string.action_cancel))
            }
        }
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
 * Today's date as the date picker counts it: UTC midnight.
 *
 * The picker speaks UTC midnights. Today must be the LOCAL calendar
 * date expressed that way, or a teacher in Bangladesh (UTC+6) opening
 * the form before 6 am would be offered yesterday.
 *
 * @return Midnight UTC of today's local date
 */
internal fun todayAsUtcMillis(): Long {
    val local = Calendar.getInstance()
    val utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
    utc.clear()
    utc.set(
        local.get(Calendar.YEAR),
        local.get(Calendar.MONTH),
        local.get(Calendar.DAY_OF_MONTH),
    )
    return utc.timeInMillis
}

/**
 * The wire form of a picked date.
 *
 * **Formatted in UTC**, because the picker's millis are UTC midnight.
 * Formatted in local time they read correctly east of UTC -- so a test
 * run in Dhaka would pass -- and show the previous day anywhere west of
 * it. Formatting in UTC is right in every zone.
 *
 * @param utcMillis A date as the picker reports it
 * @return `yyyy-MM-dd`
 */
internal fun isoDate(utcMillis: Long): String = utcFormat("yyyy-MM-dd").format(utcMillis)

/**
 * A picked date for display, with Latin digits per the numeral rule.
 *
 * @param utcMillis A date as the picker reports it
 * @return e.g. `4 Nov 2026`
 */
internal fun displayDate(utcMillis: Long): String = utcFormat("d MMM yyyy").format(utcMillis)

/**
 * A formatter fixed to UTC and English, so digits are always Latin.
 *
 * @param pattern The date pattern
 * @return The formatter
 */
private fun utcFormat(pattern: String): SimpleDateFormat =
    SimpleDateFormat(pattern, Locale.ENGLISH).apply { timeZone = TimeZone.getTimeZone("UTC") }
