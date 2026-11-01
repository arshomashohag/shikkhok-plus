package com.shikkhokplus.app.feature.classcalendar.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.classTopicsEmpty
import com.shikkhokplus.app.core.ui.classTopicsHeading

/** The read-only class's topics. */
const val TAG_CLASS_READ_TOPIC: String = "class_read_topic"

/** The read-only class's notes. */
const val TAG_CLASS_READ_NOTES: String = "class_read_notes"

/** Shown in place of the topics when a read-only class has none. */
const val TAG_CLASS_READ_EMPTY: String = "class_read_empty"

/**
 * A class the server allows neither recording nor planning: what is
 * known about it, with no controls.
 *
 * @param clazz The class
 * @param onBack Called by the back arrow
 */
@Composable
fun ClassReadOnlyScreen(clazz: CalendarClassUi, onBack: () -> Unit) {
    ListScreenScaffold(
        title = stringResource(R.string.classread_title),
        subtitle = classHeading(clazz),
        onBack = onBack,
    ) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            val topic = clazz.topic?.takeIf { it.isNotBlank() }
            val notes = clazz.notes?.takeIf { it.isNotBlank() }
            Text(stringResource(classTopicsHeading(clazz.state)), style = MaterialTheme.typography.labelLarge)
            if (topic != null) {
                Text(Numerals.freeText(topic), Modifier.padding(bottom = 12.dp).testTag(TAG_CLASS_READ_TOPIC))
            } else {
                Text(
                    stringResource(classTopicsEmpty(clazz.state)),
                    Modifier.padding(bottom = 12.dp).testTag(TAG_CLASS_READ_EMPTY),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            notes?.let {
                Text(stringResource(R.string.classday_notes), style = MaterialTheme.typography.labelLarge)
                Text(Numerals.freeText(it), Modifier.testTag(TAG_CLASS_READ_NOTES))
            }
        }
    }
}

/** The class's date, time and subject on one line. */
internal fun classHeading(clazz: CalendarClassUi): String =
    listOfNotNull(clazz.date, classLine(clazz)).joinToString(" · ")
