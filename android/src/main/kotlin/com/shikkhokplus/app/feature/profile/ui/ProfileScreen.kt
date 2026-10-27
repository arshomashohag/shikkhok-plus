package com.shikkhokplus.app.feature.profile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.profile.ProfileUiState

/** Test tag for the self-authored name field. */
const val TAG_PROFILE_NAME: String = "profile_name"

/** Test tag for the address field. */
const val TAG_PROFILE_ADDRESS: String = "profile_address"

/** Test tag for the save control. */
const val TAG_PROFILE_SAVE: String = "profile_save"

/**
 * `O5`, the profile edit half.
 *
 * **The edit half only.** The mockups draw four deletion states on this
 * same screen because one screen is where they live, but both
 * account-deletion paths are D6's: release-blocking V1 deliverables
 * with their own tests [TC-19, RC-4, RC-5]. A half-built deletion flow
 * is worse than none, so nothing here hints at one.
 *
 * **What is written here changes no teacher's roster** [BR3.1,
 * AC1.5.3]. The name a person writes about themselves lands on their
 * own private profile; each teacher keeps seeing the name that teacher
 * typed. The screen says so rather than leaving a person to discover it
 * — the two names answer different questions and only the server knows
 * which table it read.
 *
 * The address is the most consequential field in this product's
 * personal data and is owner-private by table, by row-level security
 * and by response schema [BR3.2, BR3.4]. None of that is visible here,
 * which is the point: this screen is not where the boundary is held.
 *
 * @param state What to render
 * @param onEdit Called to open the form
 * @param onSave Called with the edited name and address
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 * @param bottomBar The navigation bar, supplied by the route so this
 *   screen stays renderable in a test without one
 */
@Composable
fun ProfileScreen(
    state: ProfileUiState,
    onEdit: () -> Unit,
    onSave: (name: String, address: String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ScreenScaffold(
        title = stringResource(R.string.profile_title),
        modifier = modifier,
        bottomBar = bottomBar,
    ) {
        // The title is in the app bar. It was rendered here too,
        // so every screen showed its name twice.

        when (state) {
            ProfileUiState.Loading -> LogoLoader()

            is ProfileUiState.Viewing -> {
                ProfileField(
                    labelRes = R.string.profile_name_label,
                    value = state.selfName,
                )
                ProfileField(
                    labelRes = R.string.profile_address_label,
                    value = state.address,
                )
                Text(
                    text = stringResource(R.string.profile_teacher_name_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                Button(onClick = onEdit, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.profile_edit))
                }
            }

            is ProfileUiState.Editing -> ProfileForm(
                initialName = state.selfName,
                initialAddress = state.address,
                onSave = onSave,
            )

            ProfileUiState.Saving -> {
                LogoLoader()
                Text(text = stringResource(R.string.profile_saving))
            }

            is ProfileUiState.Saved -> {
                Text(text = stringResource(R.string.profile_saved))
                ProfileField(
                    labelRes = R.string.profile_name_label,
                    value = state.selfName,
                )
                ProfileField(
                    labelRes = R.string.profile_address_label,
                    value = state.address,
                )
            }

            is ProfileUiState.Failed -> {
                Text(
                    text = stringResource(
                        MessageKeys.resolve(state.messageKey),
                    ),
                    color = MaterialTheme.colorScheme.error,
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.auth_retry))
                    }
                }
            }
        }
    }
}

/**
 * One read-only labelled value.
 *
 * An unset field renders its label and an empty value rather than
 * disappearing, so a person can see that the field exists and is
 * theirs to fill.
 *
 * @param labelRes The string resource labelling the field
 * @param value The value, or null when unset
 */
@Composable
private fun ProfileField(labelRes: Int, value: String?) {
    Text(
        text = stringResource(labelRes),
        style = MaterialTheme.typography.labelMedium,
    )
    Text(text = value.orEmpty())
}

/**
 * The edit form.
 *
 * @param initialName The name as it stands
 * @param initialAddress The address as it stands
 * @param onSave Called with both values
 */
@Composable
private fun ProfileForm(
    initialName: String,
    initialAddress: String,
    onSave: (String, String) -> Unit,
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
    OutlinedTextField(
        value = address,
        onValueChange = { address = it },
        label = { Text(stringResource(R.string.profile_address_label)) },
        modifier = Modifier.fillMaxWidth().testTag(TAG_PROFILE_ADDRESS),
    )
    Text(
        text = stringResource(R.string.profile_teacher_name_note),
        style = MaterialTheme.typography.bodySmall,
    )
    Button(
        onClick = { onSave(name, address) },
        modifier = Modifier.fillMaxWidth().testTag(TAG_PROFILE_SAVE),
    ) {
        Text(stringResource(R.string.profile_save))
    }
}
