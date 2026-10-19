package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/**
 * Screen one: OTP entry.
 *
 * **This composable renders a [AuthUiState] and nothing else.** There is
 * no conditional here that depends on a domain value — no comparison, no
 * threshold, no inference about whether a number was recognised. Every
 * such decision was made by `AuthStateMapper`, which is where the tests
 * target it [TC-9, D-31].
 *
 * The retry button appears because the *state* says `retryable`, which
 * the server set. The client never decides that from a status code.
 *
 * Test tags are stable identifiers for the Compose UI test and the
 * device run; they are not user-visible text.
 */
@Composable
fun AuthScreen(
    state: AuthUiState,
    onRequestCode: (String) -> Unit,
    onSubmitCode: (String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.app_name))

        when (state) {
            AuthUiState.Idle,
            is AuthUiState.Failed,
            -> PhoneEntry(
                phone = phone,
                onPhoneChange = { phone = it },
                onSubmit = { onRequestCode(phone) },
            )

            AuthUiState.Sending -> CircularProgressIndicator(
                modifier = Modifier.testTag(TAG_SENDING),
            )

            AuthUiState.AwaitingCode -> CodeEntry(
                code = code,
                onCodeChange = { code = it },
                onSubmit = { onSubmitCode(code) },
            )

            AuthUiState.SignedIn -> Text(
                text = stringResource(R.string.auth_verify),
                modifier = Modifier.testTag(TAG_SIGNED_IN),
            )
        }

        // The failure block is OUTSIDE the when, so a failure that
        // happened while awaiting a code still shows beneath the field
        // the user was using rather than replacing the screen.
        if (state is AuthUiState.Failed) {
            Text(
                text = stringResource(MessageKeys.resolve(state.messageKey)),
                modifier = Modifier.testTag(TAG_ERROR),
            )
            if (state.retryable) {
                Button(
                    onClick = onRetry,
                    modifier = Modifier.testTag(TAG_RETRY),
                ) {
                    Text(text = stringResource(R.string.auth_retry))
                }
            }
        }
    }
}

@Composable
private fun PhoneEntry(
    phone: String,
    onPhoneChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    OutlinedTextField(
        value = phone,
        onValueChange = onPhoneChange,
        label = { Text(stringResource(R.string.auth_phone_label)) },
        placeholder = { Text(stringResource(R.string.auth_phone_hint)) },
        // The number is TYPED. There is no autofill hint reading it from
        // the SIM, and the app holds no permission that would allow it
        // [AC1.1.6, TC-4, D-35].
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
        singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag(TAG_PHONE_FIELD),
    )
    Button(
        onClick = onSubmit,
        modifier = Modifier.fillMaxWidth().testTag(TAG_REQUEST_CODE),
    ) {
        Text(text = stringResource(R.string.auth_request_code))
    }
}

@Composable
private fun CodeEntry(
    code: String,
    onCodeChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    // Shown for ANY number, known or not: the server's response is
    // identical either way, and the copy says "if that number is
    // registered" so the screen does not imply recognition [BR2.7].
    Text(text = stringResource(R.string.auth_code_sent))
    OutlinedTextField(
        value = code,
        onValueChange = onCodeChange,
        label = { Text(stringResource(R.string.auth_code_label)) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
        singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag(TAG_CODE_FIELD),
    )
    Button(
        onClick = onSubmit,
        modifier = Modifier.fillMaxWidth().testTag(TAG_VERIFY),
    ) {
        Text(text = stringResource(R.string.auth_verify))
    }
}

const val TAG_PHONE_FIELD = "auth_phone_field"
const val TAG_REQUEST_CODE = "auth_request_code"
const val TAG_CODE_FIELD = "auth_code_field"
const val TAG_VERIFY = "auth_verify"
const val TAG_RETRY = "auth_retry"
const val TAG_ERROR = "auth_error"
const val TAG_SENDING = "auth_sending"
const val TAG_SIGNED_IN = "auth_signed_in"
