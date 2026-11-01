package com.shikkhokplus.app.feature.classcalendar.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.displayTime

/** One class in the day's list. */
const val TAG_CLASS_PICK_ROW: String = "class_pick_row"

/** The start time and subject of a class, for lists and headings. */
internal fun classLine(clazz: CalendarClassUi): String =
    listOfNotNull(displayTime(clazz.startTime.take(HHMM)), clazz.subjectName).joinToString(" · ")

/**
 * A day with several classes: pick one by its time and subject.
 *
 * @param classes The day's classes
 * @param onPick Called with the class chosen
 * @param onDismiss Called to close without choosing
 */
@Composable
fun ClassPickList(
    classes: List<CalendarClassUi>,
    onPick: (CalendarClassUi) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.classpick_title)) },
        text = {
            Column {
                classes.forEach { clazz ->
                    Text(
                        classLine(clazz),
                        Modifier
                            .fillMaxWidth()
                            .clickable { onPick(clazz) }
                            .heightIn(min = 48.dp)
                            .padding(vertical = 12.dp)
                            .testTag(TAG_CLASS_PICK_ROW),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    HorizontalDivider()
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.classpick_close)) }
        },
    )
}

private const val HHMM = 5
