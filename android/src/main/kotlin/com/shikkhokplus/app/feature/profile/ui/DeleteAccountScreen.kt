package com.shikkhokplus.app.feature.profile.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.profile.DeletionState
import com.shikkhokplus.app.feature.profile.numberMatches

/** The field the person types their number into. */
const val TAG_DELETE_NUMBER: String = "delete_number"

/** The button that deletes. */
const val TAG_DELETE_CONFIRM: String = "delete_confirm"

/** The button that backs out. */
const val TAG_DELETE_KEEP: String = "delete_keep"

/** Why the server refused. */
const val TAG_DELETE_ERROR: String = "delete_error"

/** The done screen. */
const val TAG_DELETE_DONE: String = "delete_done"

/** The done screen's close button, which ends the session. */
const val TAG_DELETE_CLOSE: String = "delete_close"

/**
 * Deleting one's own account from inside the app (O5) [TC-19].
 *
 * **The second deletion path, and a release blocker without it.** The
 * web route existed; this did not, and `project.md` makes both paths
 * release-blocking V1 deliverables. Both reach the same server function,
 * so they delete the same rows [BR3.1].
 *
 * **What goes and what stays is said before, not after.** The person
 * types their number back -- one stray tap cannot delete an account --
 * and reads the two lists the Data Safety form and the privacy policy
 * also make: their login and profile go, their teachers' records of
 * their classes stay.
 *
 * O5 also draws a teacher deleting while still owning batches. The
 * server refuses that ("hand them over or close them first"), so this
 * screen shows the server's refusal rather than the drawn variant.
 *
 * @param state Where deletion stands
 * @param onDelete Called with the typed number
 * @param onKeep Called to back out
 * @param onDone Called from the done screen; ends the session
 */
@Composable
fun DeleteAccountScreen(
    state: DeletionState,
    onDelete: (String) -> Unit,
    onKeep: () -> Unit,
    onDone: () -> Unit,
) {
    if (state == DeletionState.Deleted) {
        DeletedBody(onDone)
        return
    }

    var typed by remember { mutableStateOf("") }
    val phone =
        when (state) {
            is DeletionState.Confirming -> state.phone
            is DeletionState.Failed -> state.phone
            else -> null
        }
    val deleting = state == DeletionState.Deleting

    ScreenScaffold(
        title = stringResource(R.string.delete_title),
        onBack = if (deleting) null else onKeep,
    ) {
        Card(
            border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.error),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(
                Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    stringResource(R.string.delete_cannot_undo),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.error,
                )
                Text(stringResource(R.string.delete_type_number))
                OutlinedTextField(
                    value = typed,
                    onValueChange = { typed = it },
                    label = { Text(stringResource(R.string.delete_number_field)) },
                    singleLine = true,
                    enabled = !deleting,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth().testTag(TAG_DELETE_NUMBER),
                )
            }
        }

        ListCard(
            heading = R.string.delete_deleted_heading,
            lines = listOf(R.string.delete_deleted_login, R.string.delete_deleted_payments),
        )
        ListCard(
            heading = R.string.delete_kept_heading,
            lines = listOf(R.string.delete_kept_records),
            note = R.string.delete_kept_note,
        )

        (state as? DeletionState.Failed)?.let {
            Text(
                text = stringResource(MessageKeys.resolve(it.messageKey)),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag(TAG_DELETE_ERROR),
            )
        }

        if (deleting) {
            LogoLoader()
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = onKeep,
                    modifier = Modifier.weight(1f).testTag(TAG_DELETE_KEEP),
                ) { Text(stringResource(R.string.delete_keep)) }
                Button(
                    onClick = { onDelete(typed) },
                    // Disabled until the number matches, which is the
                    // point of asking for it (O5's "Delete" is drawn
                    // faded for exactly this state).
                    enabled = numberMatches(typed, phone),
                    colors =
                        ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error,
                            contentColor = MaterialTheme.colorScheme.onError,
                        ),
                    modifier = Modifier.weight(1f).testTag(TAG_DELETE_CONFIRM),
                ) { Text(stringResource(R.string.delete_confirm)) }
            }
        }
    }
}

/**
 * One "Deleted" or "Kept" card.
 *
 * @param heading The card's heading
 * @param lines What it lists
 * @param note A closing note, or null
 */
@Composable
private fun ListCard(heading: Int, lines: List<Int>, note: Int? = null) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(stringResource(heading), style = MaterialTheme.typography.titleMedium)
            lines.forEach { Text("· " + stringResource(it)) }
            note?.let {
                Text(
                    stringResource(it),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * The account is gone (O5, "Done").
 *
 * No app bar and no back: there is no account to go back into. Close
 * ends the session, which wipes the tokens and the device's queue.
 *
 * @param onDone Called when the person closes it
 */
@Composable
private fun DeletedBody(onDone: () -> Unit) {
    ScreenScaffold(title = "") {
        Column(
            Modifier.testTag(TAG_DELETE_DONE),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                stringResource(R.string.delete_done_title),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                stringResource(R.string.delete_done_body),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                stringResource(R.string.delete_done_kept),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(
                onClick = onDone,
                modifier = Modifier.fillMaxWidth().testTag(TAG_DELETE_CLOSE),
            ) { Text(stringResource(R.string.delete_done_close)) }
        }
    }
}
