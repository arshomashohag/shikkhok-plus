package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.auth.SignupUiState

/** Test tag for the phone field, stable across locales. */
const val TAG_SIGNUP_PHONE: String = "signup_phone"

/** Test tag for the name field. */
const val TAG_SIGNUP_NAME: String = "signup_name"

/** Test tag for the address field. */
const val TAG_SIGNUP_ADDRESS: String = "signup_address"

/** Test tag for the submit control. */
const val TAG_SIGNUP_SUBMIT: String = "signup_submit"

/** Test tag for the role chip group. */
const val TAG_SIGNUP_ROLE_GROUP: String = "signup_role_group"

/**
 * `O1`, signup, in its five states.
 *
 * **This composable renders a [SignupUiState] and nothing else.** There
 * is no conditional here that depends on a domain value: whether a
 * number was already added, whether a role is locked, whether a failure
 * can be retried are all decided by `SignupStateMapper` from what the
 * server said [TC-9, D-31].
 *
 * Two of this unit's rules are visible as *absences* in the code below,
 * which is why they are named here:
 *
 * * **The already-added notice names neither the teacher nor the
 *   batch** [BR2.3, AC1.12.2]. [SignupUiState.AlreadyAdded] holds
 *   neither value, so there is nothing here that could leak one even
 *   by accident. The lookup is an existence oracle by design and its
 *   width is bounded by what the state can carry.
 * * **The role is locked, not hidden** [BR4.5, AC1.12.1]. A person
 *   whose teacher added them sees which role the seat carries and
 *   cannot change it; hiding the control would leave them unable to
 *   tell whether the system understood them.
 *
 * @param state What to render
 * @param onSubmit Called with the whole payload, on the button. There
 *   is no per-keystroke lookup: signup makes one request.
 * @param onGoToLogin Called from the number-already-registered path
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 */
@Composable
fun SignupScreen(
    state: SignupUiState,
    onSubmit: (phone: String, name: String, address: String, role: SignupRole) -> Unit,
    onGoToLogin: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var phone by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }
    var role by remember { mutableStateOf(SignupRole.STUDENT) }

    ScreenScaffold(
        title = stringResource(R.string.signup_title),
        modifier = modifier,
    ) {
        Text(
            text = stringResource(R.string.signup_subhead),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (state) {
            // **No lookup while typing.** This called onPhoneLookup on
            // every keystroke, so an 11-digit number made four network
            // requests once it passed the length floor — and the
            // earlier prefixes each produced a state change the person
            // could see. Signup now sends one request, on the button.
            //
            // The already-added path still works: the server answers
            // the signup POST with its own refusal when a teacher has
            // already recorded the number, which is the same answer
            // the lookup was fetching early.
            SignupUiState.Empty -> SignupForm(
                phone = phone,
                onPhoneChange = { phone = it },
                name = name,
                onNameChange = { name = it },
                address = address,
                onAddressChange = { address = it },
                role = role,
                onRoleChange = { role = it },
                roleLocked = false,
                onSubmit = { onSubmit(phone, name, address, role) },
                invalidFieldKeys = emptyList(),
            )

            SignupUiState.CheckingNumber ->
                Progress(R.string.signup_checking_number)

            is SignupUiState.AlreadyAdded -> {
                Text(
                    text = stringResource(R.string.signup_already_added_notice),
                )
                Text(
                    text = stringResource(R.string.signup_role_locked_note),
                    style = MaterialTheme.typography.bodySmall,
                )
                SignupForm(
                    phone = phone,
                    onPhoneChange = { phone = it },
                    name = state.prefilledName,
                    onNameChange = { name = it },
                    address = address,
                    onAddressChange = { address = it },
                    role = state.lockedRole,
                    onRoleChange = { },
                    roleLocked = true,
                    onSubmit = {
                        onSubmit(
                            phone,
                            name.ifEmpty { state.prefilledName },
                            address,
                            state.lockedRole,
                        )
                    },
                    invalidFieldKeys = emptyList(),
                )
            }

            is SignupUiState.Invalid -> SignupForm(
                phone = phone,
                onPhoneChange = { phone = it },
                name = name,
                onNameChange = { name = it },
                address = address,
                onAddressChange = { address = it },
                role = role,
                onRoleChange = { role = it },
                roleLocked = false,
                onSubmit = { onSubmit(phone, name, address, role) },
                invalidFieldKeys = state.fieldKeys,
            )

            SignupUiState.Submitting ->
                Progress(R.string.signup_submitting)

            is SignupUiState.CodeSent -> Text(
                text = stringResource(
                    R.string.signup_code_sent,
                    state.codeSentTo,
                ),
            )

            is SignupUiState.Failed -> SignupFailure(
                state = state,
                onGoToLogin = onGoToLogin,
                onRetry = onRetry,
            )
        }
    }
}

/**
 * The form itself, shared by the empty, already-added and invalid
 * states so the three cannot drift apart.
 *
 * @param phone The number typed so far
 * @param onPhoneChange Called on each edit
 * @param name The name field's value
 * @param onNameChange Called on each edit
 * @param address The address field's value
 * @param onAddressChange Called on each edit
 * @param role The selected role
 * @param onRoleChange Called when a role chip is chosen
 * @param roleLocked Whether the role may be changed
 * @param onSubmit Called when the form is submitted
 * @param invalidFieldKeys String keys naming fields that need fixing
 */
@Composable
private fun SignupForm(
    phone: String,
    onPhoneChange: (String) -> Unit,
    name: String,
    onNameChange: (String) -> Unit,
    address: String,
    onAddressChange: (String) -> Unit,
    role: SignupRole,
    onRoleChange: (SignupRole) -> Unit,
    roleLocked: Boolean,
    onSubmit: () -> Unit,
    invalidFieldKeys: List<String>,
) {
    OutlinedTextField(
        value = phone,
        onValueChange = onPhoneChange,
        label = { Text(stringResource(R.string.signup_phone_label)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
        singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag(TAG_SIGNUP_PHONE),
    )
    OutlinedTextField(
        value = name,
        onValueChange = onNameChange,
        label = { Text(stringResource(R.string.signup_name_label)) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag(TAG_SIGNUP_NAME),
    )
    OutlinedTextField(
        value = address,
        onValueChange = onAddressChange,
        label = { Text(stringResource(R.string.signup_address_label)) },
        modifier = Modifier.fillMaxWidth().testTag(TAG_SIGNUP_ADDRESS),
    )

    Text(text = stringResource(R.string.signup_role_label))
    Column(
        modifier = Modifier.selectableGroup().testTag(TAG_SIGNUP_ROLE_GROUP),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SignupRole.entries.forEach { option ->
            FilterChip(
                selected = option == role,
                onClick = { onRoleChange(option) },
                enabled = !roleLocked,
                label = { Text(stringResource(labelOf(option))) },
                // A default chip is 32dp tall, well under the 48dp
                // floor. These sit in a vertical group where a miss
                // selects the neighbouring role, which is the field
                // the server locks a person's identity to.
                modifier = Modifier.heightIn(min = Reach.touch),
            )
        }
    }

    invalidFieldKeys.forEach { key ->
        Text(
            text = stringResource(MessageKeys.resolve(key)),
            color = MaterialTheme.colorScheme.error,
        )
    }

    Button(
        onClick = onSubmit,
        modifier =
            Modifier
                .fillMaxWidth()
                .heightIn(min = Reach.touch)
                .testTag(TAG_SIGNUP_SUBMIT),
    ) {
        // **`signup_submit` takes the number as an argument.** Fetched
        // without one, Android renders the placeholder itself, so the
        // button read "Send code to %1$s" on a device. Found by a
        // person using the build; no test caught it, because a
        // Robolectric assertion on a tag never reads the text.
        //
        // Before a number is typed there is nothing to name, and
        // "Send code to " with a trailing space is worse than a plain
        // label — so the generic string is used until the field has
        // something in it.
        Text(
            text =
                if (phone.isBlank()) {
                    stringResource(R.string.signup_submit_generic)
                } else {
                    stringResource(R.string.signup_submit, phone)
                },
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

/**
 * The failure state, including the number-already-registered path.
 *
 * `O1` state 5 offers a way to log in rather than only an error, which
 * is the one failure here a person can act on immediately [BR4.4].
 *
 * @param state The failure to render
 * @param onGoToLogin Called from the log-in path
 * @param onRetry Called when the server said the failure is retryable
 */
@Composable
private fun SignupFailure(
    state: SignupUiState.Failed,
    onGoToLogin: () -> Unit,
    onRetry: () -> Unit,
) {
    Text(
        text = stringResource(MessageKeys.resolve(state.messageKey)),
        color = MaterialTheme.colorScheme.error,
    )
    TextButton(onClick = onGoToLogin) {
        Text(stringResource(R.string.signup_go_to_login))
    }
    if (state.retryable) {
        Button(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.auth_retry))
        }
    }
}

/**
 * A labelled progress indicator.
 *
 * @param labelRes The string resource naming what is in flight
 */
@Composable
private fun Progress(labelRes: Int) {
    LogoLoader()
    Text(text = stringResource(labelRes))
}

/**
 * The string resource naming a role.
 *
 * A `when` rather than a map so a fourth role fails to compile here
 * instead of rendering nothing.
 *
 * @param role The role to label
 * @return Its string resource id
 */
private fun labelOf(role: SignupRole): Int = when (role) {
    SignupRole.TEACHER -> R.string.signup_role_teacher
    SignupRole.STUDENT -> R.string.signup_role_student
    SignupRole.GUARDIAN -> R.string.signup_role_guardian
}
