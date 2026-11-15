package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.ui.AutofillHint
import com.shikkhokplus.app.core.ui.AvailabilityHint
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.core.ui.PasswordField
import com.shikkhokplus.app.core.ui.UsernameField
import com.shikkhokplus.app.feature.account.UsernameStateMapper
import com.shikkhokplus.app.feature.account.UsernameUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The stored username, on the Username screen. */
const val TAG_USERNAME_CURRENT: String = "username_current"

/** Change, on the Username screen. */
const val TAG_USERNAME_CHANGE: String = "username_change"

/** The new name on the rename form. */
const val TAG_USERNAME_NEW: String = "username_new"

/** The current password on the rename form. */
const val TAG_USERNAME_PASSWORD: String = "username_password"

/** Save, on the rename form. */
const val TAG_USERNAME_SAVE: String = "username_save"

/** A refusal on the rename form, as a banner. */
const val TAG_USERNAME_ERROR: String = "username_error"

/** Retry, on the rename form. */
const val TAG_USERNAME_RETRY: String = "username_retry"

/** "Set a password", offered when a rename needs one. */
const val TAG_USERNAME_SET_PASSWORD: String = "username_set_password"

/** The "changed" note. */
const val TAG_USERNAME_CHANGED: String = "username_changed"

/**
 * What the Username screen can ask for.
 *
 * @property onChange Opens the rename form
 * @property onCancel Leaves the form
 * @property onEdited The new name changed
 * @property onSave Saves the new name with the current password; also the retry
 * @property onSetPassword Opens setting a password
 * @property onBack Leaves the screen
 */
data class UsernameActions(
    val onChange: () -> Unit = {},
    val onCancel: () -> Unit = {},
    val onEdited: (String) -> Unit = {},
    val onSave: (String, String) -> Unit = { _, _ -> },
    val onSetPassword: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The account's username, and changing it [W5, FR7.1].
 *
 * **Change is always offered** [NFR3.11]; whether a rename is allowed
 * now is the server's, and its refusal names the date it sent. The new
 * name survives a rotation; the password lives in `remember` only and is
 * gone after a recreation, a success or leaving the form [NFR3.4].
 *
 * @param state What to render
 * @param availability The live check on the new name
 * @param actions What the controls call
 */
@Composable
fun UsernameScreen(
    state: UsernameUiState,
    availability: AvailabilityState,
    actions: UsernameActions,
) {
    val editing = state as? UsernameUiState.Editing
    ScreenScaffold(
        title = stringResource(R.string.username_title),
        onBack = if (editing != null) actions.onCancel else actions.onBack,
    ) {
        when (state) {
            is UsernameUiState.Viewing -> Showing(state.username, changed = false, nextChangeAt = null, actions)
            is UsernameUiState.Changed -> Showing(state.username, changed = true, state.nextChangeAt, actions)
            is UsernameUiState.Editing -> RenameForm(state, availability, actions)
        }
    }
    if (editing?.saving == true) {
        LogoLoader(size = 72.dp, label = stringResource(R.string.username_save))
    }
}

/**
 * The stored name, a "changed" note after a rename, and Change.
 *
 * @param username The stored name, or null
 * @param changed Whether this is the answer to a rename
 * @param nextChangeAt The next change's instant as the server sent it,
 *   or null; the note is shown without a date then
 * @param actions What the controls call
 */
@Composable
private fun Showing(username: String?, changed: Boolean, nextChangeAt: String?, actions: UsernameActions) {
    Text(stringResource(R.string.username_current_label), style = MaterialTheme.typography.labelLarge)
    Text(
        text = username ?: stringResource(R.string.more_username_choose),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.testTag(TAG_USERNAME_CURRENT),
    )
    if (changed) {
        Banner(
            title =
                nextChangeAt?.let { stringResource(R.string.username_changed_on, dateTimeLabel(it)) }
                    ?: stringResource(R.string.username_changed),
            tone = BannerTone.NEUTRAL,
            modifier = Modifier.testTag(TAG_USERNAME_CHANGED),
        )
    }
    PrimaryButton(
        text = stringResource(R.string.username_change),
        onClick = actions.onChange,
        modifier = Modifier.fillMaxWidth().testTag(TAG_USERNAME_CHANGE),
    )
}

/**
 * The rename form: the new name with its hint, the rule note, the current
 * password, and Save.
 *
 * @param form The form's state
 * @param availability The live check on the new name
 * @param actions What the controls call
 */
@Composable
private fun RenameForm(form: UsernameUiState.Editing, availability: AvailabilityState, actions: UsernameActions) {
    var username by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val save = { actions.onSave(username, password) }
    UsernameField(
        value = username,
        onValueChange = {
            username = it
            actions.onEdited(it)
        },
        label = stringResource(R.string.username_new_label),
        autofill = AutofillHint.NEW_USERNAME,
        error = form.usernameKey?.let { stringResource(MessageKeys.resolve(it)) },
        enabled = !form.saving,
        fieldModifier = Modifier.testTag(TAG_USERNAME_NEW),
    )
    if (form.usernameKey == null) AvailabilityHint(state = availability, help = null)
    Text(
        text = stringResource(R.string.username_rule_note),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    PasswordField(
        value = password,
        onValueChange = { password = it },
        label = stringResource(R.string.account_password_current_label),
        error = form.passwordKey?.let { stringResource(MessageKeys.resolve(it)) },
        enabled = !form.saving,
        onImeAction = save,
        fieldModifier = Modifier.testTag(TAG_USERNAME_PASSWORD),
    )
    form.bannerKey?.let { key ->
        val date = form.bannerDate
        Banner(
            title =
                if (key == UsernameStateMapper.TOO_SOON_KEY && date != null) {
                    stringResource(R.string.account_username_change_too_soon_on, dateTimeLabel(date))
                } else {
                    stringResource(MessageKeys.resolve(key))
                },
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_USERNAME_ERROR),
        )
        if (form.offerSetPassword) {
            TextAction(
                text = stringResource(R.string.contacts_set_password),
                onClick = actions.onSetPassword,
                modifier = Modifier.testTag(TAG_USERNAME_SET_PASSWORD),
            )
        }
        if (form.retryable) {
            SecondaryButton(
                text = stringResource(R.string.auth_retry),
                onClick = save,
                modifier = Modifier.fillMaxWidth().testTag(TAG_USERNAME_RETRY),
            )
        }
    }
    PrimaryButton(
        text = stringResource(R.string.username_save),
        onClick = save,
        enabled = username.isNotBlank() && password.isNotEmpty() && !form.saving,
        modifier = Modifier.fillMaxWidth().testTag(TAG_USERNAME_SAVE),
    )
}
