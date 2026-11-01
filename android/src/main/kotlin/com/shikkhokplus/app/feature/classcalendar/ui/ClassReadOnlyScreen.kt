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

/** The read-only class's topics. */
const val TAG_CLASS_READ_TOPIC: String = "class_read_topic"

/** The read-only class's notes. */
const val TAG_CLASS_READ_NOTES: String = "class_read_notes"

/** Shown when a read-only class has neither topics nor notes. */
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
            topic?.let {
                Text(stringResource(R.string.classday_topics_covered), style = MaterialTheme.typography.labelLarge)
                Text(Numerals.freeText(it), Modifier.padding(bottom = 12.dp).testTag(TAG_CLASS_READ_TOPIC))
            }
            notes?.let {
                Text(stringResource(R.string.classday_notes), style = MaterialTheme.typography.labelLarge)
                Text(Numerals.freeText(it), Modifier.testTag(TAG_CLASS_READ_NOTES))
            }
            if (topic == null && notes == null) {
                Text(stringResource(R.string.classread_nothing), Modifier.testTag(TAG_CLASS_READ_EMPTY))
            }
        }
    }
}

/** The class's date, time and subject on one line. */
internal fun classHeading(clazz: CalendarClassUi): String =
    listOfNotNull(clazz.date, classLine(clazz)).joinToString(" · ")
