package com.shikkhokplus.app.feature.record.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.record.RecordSheet

/** The topic field. */
const val TAG_RECORD_TOPIC: String = "record_topic"

/** The "continue" suggestion. */
const val TAG_RECORD_SUGGESTION: String = "record_suggestion"

/** One subject choice. */
const val TAG_RECORD_SUBJECT: String = "record_subject"

/** The save button. */
const val TAG_RECORD_SAVE: String = "record_save"

/** The link to attendance. */
const val TAG_RECORD_ATTENDANCE: String = "record_attendance"

/**
 * T2: record what a class covered, mid-class, in a few seconds.
 *
 * **Save is never disabled for an empty topic.** A topic saved blank is
 * a deliberate record that the class happened without one [BR2.2]; the
 * board's disabled-when-empty button would make that unrecordable.
 *
 * @param sheet The sheet's state
 * @param onType Called with the topic as typed
 * @param onChoose Called with a subject id
 * @param onSuggestion Called to use the suggestion
 * @param onSave Called to save
 * @param onAttendance Called to take attendance for this class instead
 * @param onDismiss Called to close without saving
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordClassSheet(
    sheet: RecordSheet,
    onType: (String) -> Unit,
    onChoose: (String) -> Unit,
    onSuggestion: () -> Unit,
    onSave: () -> Unit,
    onAttendance: () -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Column {
                Text(stringResource(R.string.record_title), style = MaterialTheme.typography.titleLarge)
                Text(
                    stringResource(
                        R.string.record_subtitle,
                        Numerals.freeText(sheet.target.title),
                        displayTime(sheet.target.startTime),
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            SubjectPicker(sheet, onChoose)
            ShikkhokTextField(
                value = sheet.typed,
                onValueChange = onType,
                label = stringResource(R.string.record_question),
                help = stringResource(R.string.record_help).takeIf { sheet.suggestion == null },
                singleLine = false,
                minLines = 3,
                fieldModifier = Modifier.testTag(TAG_RECORD_TOPIC),
            )
            sheet.suggestion?.let { suggestion ->
                SuggestionChip(
                    onClick = onSuggestion,
                    label = {
                        Text(
                            stringResource(R.string.record_continue, Numerals.freeText(suggestion)),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    },
                    modifier = Modifier.testTag(TAG_RECORD_SUGGESTION),
                )
            }
            sheet.errorKey?.let { key ->
                Banner(stringResource(MessageKeys.resolve(key)), tone = BannerTone.ERROR)
            }
            PrimaryButton(
                text = stringResource(R.string.record_save),
                onClick = onSave,
                enabled = !sheet.saving,
                modifier = Modifier.fillMaxWidth().testTag(TAG_RECORD_SAVE),
            )
            TextAction(
                stringResource(R.string.record_take_attendance),
                onAttendance,
                Modifier.fillMaxWidth().testTag(TAG_RECORD_ATTENDANCE),
            )
        }
    }
}

/**
 * The subject choice: chips when the batch has more than one, a plain
 * line when it has exactly one, nothing when it has none.
 *
 * @param sheet The sheet's state
 * @param onChoose Called with a subject id
 */
@Composable
private fun SubjectPicker(sheet: RecordSheet, onChoose: (String) -> Unit) {
    when (sheet.subjects.size) {
        0 -> Unit
        1 ->
            Text(
                stringResource(R.string.record_only_subject, Numerals.freeText(sheet.subjects.single().name)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        else ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                sheet.subjects.forEach { subject ->
                    FilterChip(
                        selected = subject.id == sheet.subjectId,
                        onClick = { onChoose(subject.id) },
                        label = { Text(Numerals.freeText(subject.name)) },
                        modifier = Modifier.weight(1f).testTag(TAG_RECORD_SUBJECT),
                    )
                }
            }
    }
}
