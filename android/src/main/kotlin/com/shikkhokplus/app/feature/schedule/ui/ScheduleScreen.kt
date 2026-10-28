package com.shikkhokplus.app.feature.schedule.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.ui.ScheduleDraft
import com.shikkhokplus.app.core.ui.ScheduleEditor

/** The save button. */
const val TAG_SCHEDULE_SAVE: String = "schedule_save"

/** Why the schedule could not be read or saved. */
const val TAG_SCHEDULE_ERROR: String = "schedule_error"

/**
 * Edit one batch's weekly classes.
 *
 * **Where an existing batch gets a schedule.** Until now nothing could
 * set one, so every batch created before this has none -- and so no
 * sessions, and no way to take attendance. Saving generates sessions at
 * once.
 *
 * **What saving does not do is said on the screen** [BR1.2]: classes
 * already listed stay as they are, so moving Tuesday to Wednesday leaves
 * the Tuesdays already generated for the teacher to cancel. Silence here
 * would read as a promise the server does not keep.
 *
 * @param stored The current schedule, or null while it loads
 * @param onSave Called with the complete new schedule
 * @param onBack Called to leave without saving
 * @param saving True while the save is in flight
 * @param error Why the last read or save failed, resolved, or null
 */
@Composable
fun ScheduleScreen(
    stored: List<ScheduleSlotDto>?,
    onSave: (List<ScheduleSlotDto>) -> Unit,
    onBack: () -> Unit,
    saving: Boolean = false,
    error: String? = null,
) {
    ScreenScaffold(title = stringResource(R.string.screen_title_schedule), onBack = onBack) {
        if (stored == null) {
            if (error != null) {
                Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag(TAG_SCHEDULE_ERROR))
            } else {
                LogoLoader()
            }
            return@ScreenScaffold
        }
        // Keyed on what was loaded, so a reload replaces the draft.
        var draft by remember(stored) { mutableStateOf(ScheduleDraft.of(stored)) }

        ScheduleEditor(draft = draft, onChange = { draft = it })
        Text(
            stringResource(
                if (draft.days.isEmpty()) R.string.schedule_none else R.string.schedule_keeps_sessions,
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag(TAG_SCHEDULE_ERROR))
        }
        Button(
            onClick = { onSave(draft.toSlots()) },
            enabled = !saving && draft.isValid,
            modifier = Modifier.fillMaxWidth().testTag(TAG_SCHEDULE_SAVE),
        ) { Text(stringResource(R.string.schedule_save)) }
    }
}
