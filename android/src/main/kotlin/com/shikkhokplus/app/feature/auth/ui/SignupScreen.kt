package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
 * @param onPhoneLookup Called when a complete number is entered
 * @param onSubmit Called with name, address and the chosen role
 * @param onGoToLogin Called from the number-already-registered path
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 */
@Composable
fun SignupScreen(
    state: SignupUiState,
    onPhoneLookup: (String) -> Unit,
    onSubmit: (name: String, address: String, role: SignupRole) -> Unit,
    onGoToLogin: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var phone by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }
    var role by remember { mutableStateOf(SignupRole.STUDENT) }

    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = stringResource(R.string.signup_title),
            style = MaterialTheme.typography.headlineSmall,
        )

        when (state) {
            SignupUiState.Empty -> SignupForm(
                phone = phone,
                onPhoneChange = {
                    phone = it
                    onPhoneLookup(it)
                },
                name = name,
                onNameChange = { name = it },
                address = address,
                onAddressChange = { address = it },
                role = role,
                onRoleChange = { role = it },
                roleLocked = false,
                onSubmit = { onSubmit(name, address, role) },
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
                onSubmit = { onSubmit(name, address, role) },
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
        modifier = Modifier.fillMaxWidth().testTag(TAG_SIGNUP_SUBMIT),
    ) {
        Text(stringResource(R.string.signup_submit))
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
    CircularProgressIndicator()
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
