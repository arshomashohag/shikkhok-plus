package com.shikkhokplus.app.feature.classcalendar.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.feature.classcalendar.CLASS_TEXT_MAX

/** One subject choice on a class screen. */
const val TAG_CLASS_SUBJECT: String = "class_subject"

/**
 * The tag of a field's character counter.
 *
 * @param fieldTag The field's own tag
 * @return The counter's tag
 */
fun counterTag(fieldTag: String): String = "${fieldTag}_counter"

/**
 * A multi-line class field capped at [CLASS_TEXT_MAX], with a visible
 * count of what it holds.
 *
 * @param value The text
 * @param onValueChange Called with the text as typed, already capped
 * @param label The field's label
 * @param tag The field's test tag
 * @param enabled Whether it can be edited
 * @param minLines The least height, in lines
 * @param help A help line, or null
 */
@Composable
internal fun CappedClassField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    tag: String,
    enabled: Boolean,
    minLines: Int,
    help: String? = null,
) {
    Column {
        ShikkhokTextField(
            value = value,
            onValueChange = { onValueChange(it.take(CLASS_TEXT_MAX)) },
            label = label,
            help = help,
            singleLine = false,
            minLines = minLines,
            enabled = enabled,
            fieldModifier = Modifier.testTag(tag),
        )
        Text(
            stringResource(R.string.class_text_counter, value.length.toString(), CLASS_TEXT_MAX.toString()),
            modifier = Modifier.fillMaxWidth().testTag(counterTag(tag)),
            textAlign = TextAlign.End,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * The subject choice: chips when the batch has more than one, a plain
 * line when it has exactly one, nothing when it has none -- as the
 * record sheet offers it.
 *
 * @param subjects The batch's subjects
 * @param chosenId The chosen subject, if any
 * @param enabled Whether a different one can be chosen
 * @param onChoose Called with a subject id
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun SubjectChooser(
    subjects: List<SubjectOptionDto>,
    chosenId: String?,
    enabled: Boolean,
    onChoose: (String) -> Unit,
) {
    when (subjects.size) {
        0 -> Unit
        1 ->
            Text(
                stringResource(R.string.record_only_subject, Numerals.freeText(subjects.single().name)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        else ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.class_subject_label), style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    subjects.forEach { subject ->
                        FilterChip(
                            selected = subject.id == chosenId,
                            onClick = { onChoose(subject.id) },
                            enabled = enabled,
                            label = { Text(Numerals.freeText(subject.name)) },
                            modifier = Modifier.testTag(TAG_CLASS_SUBJECT),
                        )
                    }
                }
            }
    }
}
