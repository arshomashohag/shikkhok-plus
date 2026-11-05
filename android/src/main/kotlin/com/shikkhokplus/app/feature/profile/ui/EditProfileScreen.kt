package com.shikkhokplus.app.feature.profile.ui

import com.shikkhokplus.app.core.ui.AddressFields
import com.shikkhokplus.app.core.model.PostalAddress
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.MenuIcons
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.profile.ProfileUiState

/** The close control in Edit profile's bar. */
const val TAG_EDIT_PROFILE_CLOSE: String = "edit_profile_close"

/**
 * Edit profile (S4), pushed over More.
 *
 * **Its own screen, closed with an X**, as the artboard draws it: an
 * edit is something a person opens on purpose and leaves either by
 * saving or by closing, and More underneath never changes until the
 * server confirms the save.
 *
 * **What is written here changes no teacher's roster** [BR3.1,
 * AC1.5.3]. The name a person writes about themselves lands on their
 * own private profile; each teacher keeps seeing the name that teacher
 * typed. The note says so here, where the change is made.
 *
 * The address is the most consequential field in this product's
 * personal data and is owner-private by table, by row-level security
 * and by response schema [BR3.2, BR3.4]. None of that is visible here,
 * which is the point: this screen is not where the boundary is held.
 *
 * @param state What to render; `Editing` draws the form
 * @param phone The sign-in number, shown read-only, or null
 * @param onSave Called with the edited name and address. Save waits
 *   for all four address parts (decided 2026-11-05)
 * @param onClose Called by the X
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 */
@Composable
fun EditProfileScreen(
    state: ProfileUiState,
    phone: String?,
    onSave: (name: String, address: PostalAddress) -> Unit,
    onClose: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.edit_profile_title),
        modifier = modifier,
        leading = {
            IconButton(onClick = onClose, modifier = Modifier.testTag(TAG_EDIT_PROFILE_CLOSE)) {
                Icon(
                    imageVector = MenuIcons.Close,
                    contentDescription = stringResource(R.string.action_close),
                )
            }
        },
    ) {
        when (state) {
            is ProfileUiState.Editing ->
                ProfileForm(
                    initialName = state.selfName,
                    initialAddress = state.address,
                    phone = phone,
                    onSave = onSave,
                )

            ProfileUiState.Saving -> LogoLoader(label = stringResource(R.string.profile_saving))

            is ProfileUiState.Failed -> {
                Text(
                    text = stringResource(MessageKeys.resolve(state.messageKey)),
                    color = MaterialTheme.colorScheme.error,
                )
                if (state.retryable) {
                    PrimaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = onRetry,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }

            // Viewing, Saved or Loading: the route closes the screen on a
            // save and never opens it before a read, so there is nothing
            // to draw but the wait.
            else -> LogoLoader()
        }
    }
}

/**
 * The edit form.
 *
 * @param initialName The name as it stands
 * @param initialAddress The address as it stands, in its four parts
 * @param phone The sign-in number, or null
 * @param onSave Called with both values
 */
@Composable
private fun ProfileForm(
    initialName: String,
    initialAddress: PostalAddress,
    phone: String?,
    onSave: (String, PostalAddress) -> Unit,
) {
    var name by remember(initialName) { mutableStateOf(initialName) }
    var address by remember(initialAddress) { mutableStateOf(initialAddress) }

    OutlinedTextField(
        value = name,
        onValueChange = { name = it },
        label = { Text(stringResource(R.string.profile_name_label)) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag(TAG_PROFILE_NAME),
    )
    Text(
        text = stringResource(R.string.profile_teacher_name_note),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        text = stringResource(R.string.profile_address_label),
        style = MaterialTheme.typography.labelLarge,
    )
    AddressFields(address = address, onChange = { address = it }, showMissing = true)

    // **Read-only, and said so** (O5). The number is the login; changing
    // it would go through the OTP path, never a profile edit, and that
    // path does not exist yet.
    Text(
        text = stringResource(R.string.profile_phone_label),
        style = MaterialTheme.typography.labelLarge,
    )
    Text(
        text = phone?.let(Numerals::phone).orEmpty(),
        style = MaterialTheme.typography.bodyLarge,
        modifier = Modifier.testTag(TAG_PROFILE_PHONE),
    )
    Text(
        text = stringResource(R.string.profile_phone_note),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    PrimaryButton(
        text = stringResource(R.string.profile_save),
        onClick = { onSave(name, address) },
        // The address is required, so Save waits for all four parts.
        enabled = address.isComplete,
        modifier = Modifier.fillMaxWidth().testTag(TAG_PROFILE_SAVE),
    )
}
