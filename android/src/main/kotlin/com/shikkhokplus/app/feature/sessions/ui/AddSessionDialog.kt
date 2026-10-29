package com.shikkhokplus.app.feature.sessions.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.displayDate
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.todayAsUtcMillis
import com.shikkhokplus.app.core.ui.TimeDialog
import com.shikkhokplus.app.core.ui.displayTime

/** The confirm button. */
const val TAG_ADD_SESSION_CONFIRM: String = "add_session_confirm"

/**
 * Add a one-off class outside the weekly schedule [BR1.1].
 *
 * **Was never reachable.** The session list's "Add a class" callback was
 * left at its default, so a teacher holding an extra class had nowhere
 * to record its attendance.
 *
 * @param onAdd Called with the ISO date and `HH:MM` start
 * @param onDismiss Called when backed out of
 * @param todayUtcMillis Today as the date picker counts it; injected for tests
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddSessionDialog(
    onAdd: (String, String) -> Unit,
    onDismiss: () -> Unit,
    todayUtcMillis: Long = todayAsUtcMillis(),
) {
    var date by remember { mutableStateOf(todayUtcMillis) }
    var start by remember { mutableStateOf("16:00") }
    var picking by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.sessions_add)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.session_add_note))
                OutlinedButton(onClick = { picking = "date" }, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.session_add_date, displayDate(date)))
                }
                OutlinedButton(onClick = { picking = "time" }, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.schedule_start, displayTime(start)))
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onAdd(isoDate(date), start) },
                modifier = Modifier.testTag(TAG_ADD_SESSION_CONFIRM),
            ) { Text(stringResource(R.string.session_add_confirm)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
    )

    when (picking) {
        "date" -> {
            val state = rememberDatePickerState(initialSelectedDateMillis = date)
            DatePickerDialog(
                onDismissRequest = { picking = null },
                confirmButton = {
                    TextButton(
                        onClick = {
                            state.selectedDateMillis?.let { date = it }
                            picking = null
                        },
                    ) { Text(stringResource(R.string.action_ok)) }
                },
            ) { DatePicker(state = state) }
        }
        "time" ->
            TimeDialog(
                initial = start,
                onPicked = {
                    start = it
                    picking = null
                },
                onDismiss = { picking = null },
            )
    }
}
