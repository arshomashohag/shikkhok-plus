package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.ui.PasswordField
import com.shikkhokplus.app.feature.account.RemoveContactUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The remove sheet's password. */
const val TAG_REMOVE_PASSWORD: String = "remove_contact_password"

/** Remove, in the sheet. */
const val TAG_REMOVE_CONFIRM: String = "remove_contact_confirm"

/** A refusal in the sheet. */
const val TAG_REMOVE_ERROR: String = "remove_contact_error"

/** "Add another", offered when the last contact cannot go. */
const val TAG_REMOVE_ADD_OTHER: String = "remove_contact_add_other"

/** Retry, in the sheet. */
const val TAG_REMOVE_RETRY: String = "remove_contact_retry"

/**
 * What the remove sheet can ask for.
 *
 * @property onRemove Removes, with the password; also the retry
 * @property onAddOther Opens adding the other kind
 * @property onSetPassword Opens setting a password
 * @property onRemoved Called once the server removed it
 * @property onDismiss Closes the sheet with nothing sent
 */
data class RemoveContactActions(
    val onRemove: (String) -> Unit = {},
    val onAddOther: () -> Unit = {},
    val onSetPassword: () -> Unit = {},
    val onRemoved: () -> Unit = {},
    val onDismiss: () -> Unit = {},
)

/**
 * "Remove {contact}?": names the contact, says what stays, and asks for
 * the password [W6 step 5, FR8.4].
 *
 * **Whether it may go is the server's** [NFR3.11]: the last contact is
 * refused in the server's words, with a way to add the other kind. The
 * password lives in `remember` only [NFR3.4].
 *
 * @param state What to render
 * @param actions What the controls call
 */
@Composable
fun RemoveContactSheet(state: RemoveContactUiState, actions: RemoveContactActions) {
    LaunchedEffect(state) { if (state == RemoveContactUiState.Removed) actions.onRemoved() }
    val form = state as? RemoveContactUiState.Confirming ?: return
    var password by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = { if (!form.removing) actions.onDismiss() },
        title = { Text(stringResource(R.string.contacts_remove_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.contacts_remove_body, form.contact))
                PasswordField(
                    value = password,
                    onValueChange = { password = it },
                    label = stringResource(R.string.account_password_current_label),
                    error = form.passwordKey?.let { stringResource(MessageKeys.resolve(it)) },
                    enabled = !form.removing,
                    fieldModifier = Modifier.testTag(TAG_REMOVE_PASSWORD),
                )
                form.bannerKey?.let { key ->
                    Text(
                        text = stringResource(MessageKeys.resolve(key)),
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag(TAG_REMOVE_ERROR),
                    )
                }
                if (form.offerAddOther) {
                    TextAction(
                        text = stringResource(R.string.contacts_add_other),
                        onClick = actions.onAddOther,
                        modifier = Modifier.testTag(TAG_REMOVE_ADD_OTHER),
                    )
                }
                if (form.offerSetPassword) {
                    TextAction(stringResource(R.string.contacts_set_password), actions.onSetPassword)
                }
                if (form.retryable) {
                    TextAction(
                        text = stringResource(R.string.auth_retry),
                        onClick = { actions.onRemove(password) },
                        modifier = Modifier.fillMaxWidth().testTag(TAG_REMOVE_RETRY),
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { actions.onRemove(password) },
                enabled = password.isNotEmpty() && !form.removing,
                modifier = Modifier.testTag(TAG_REMOVE_CONFIRM),
            ) {
                Text(stringResource(R.string.contacts_remove_confirm), color = MaterialTheme.colorScheme.error)
            }
        },
        dismissButton = {
            TextButton(onClick = actions.onDismiss, enabled = !form.removing) {
                Text(stringResource(R.string.action_cancel))
            }
        },
    )
}
