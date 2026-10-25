package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.foundation.text.KeyboardOptions
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.TAG_OTP_FIELD
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
    onGoToSignup: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }

    ScreenScaffold(
        title = stringResource(R.string.app_name),
        modifier = modifier,
    ) {
        // **A heading and a sentence, where there was an unstyled app
        // name.** The screen previously opened with `Text(app_name)` at
        // default body size and went straight into a field, so nothing
        // said what the screen was for or what would happen next. The
        // name moved to the bar, which is where a product name belongs.
        Text(
            text = stringResource(R.string.auth_headline),
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(
            text = stringResource(R.string.auth_subhead),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (state) {
            AuthUiState.Idle,
            is AuthUiState.Failed,
            -> {
                PhoneEntry(
                    phone = phone,
                    onPhoneChange = { phone = it },
                    onSubmit = { onRequestCode(phone) },
                )

                // Directly beneath the control that failed, and ABOVE
                // the signup link, so a retry is never below the fold.
                if (state is AuthUiState.Failed) {
                    FailureBlock(state = state, onRetry = onRetry)
                }

                // **The way out of the dead end.** The code-sent
                // message says one is on its way "if this number is
                // registered", which is literally true and left a
                // person whose teacher had not recorded them with
                // nowhere to go: `SignupScreen` shipped in D1 and
                // nothing could open it.
                //
                // A TextButton rather than a second filled one: there
                // is one primary action on this screen and it is
                // requesting the code. Signing up is the path for the
                // minority who need it, and competing emphasis would
                // make the common case harder to see.
                TextButton(
                    onClick = onGoToSignup,
                    modifier = Modifier.testTag(TAG_GO_TO_SIGNUP),
                ) {
                    Text(text = stringResource(R.string.auth_go_to_signup))
                }
            }

            AuthUiState.Sending -> CircularProgressIndicator(
                modifier = Modifier.testTag(TAG_SENDING),
            )

            AuthUiState.AwaitingCode -> CodeEntry(
                code = code,
                onCodeChange = { code = it },
                onSubmit = { onSubmitCode(code) },
            )
            // A failure that happened while awaiting a code is handled
            // by the `Failed` arm above, which re-renders the phone
            // entry. That is deliberate and unchanged: a verify that
            // failed is recoverable by correcting the number, and the
            // state carries no memory of which field was in use.

            AuthUiState.SignedIn -> Text(
                text = stringResource(R.string.auth_verify),
                modifier = Modifier.testTag(TAG_SIGNED_IN),
            )
        }

    }
}

/**
 * The failure block, rendered beneath the control that failed.
 *
 * **Placed before the signup link rather than after it.** The link was
 * added below the entry controls, which pushed this block to the
 * bottom of a now-scrollable column — so on a small screen a retry
 * sat below the fold and the Robolectric tests caught it as "not
 * displayed". A retry the person has to scroll to find is worse than
 * no retry, because the screen looks like it offers nothing.
 *
 * @param state The failure to render
 * @param onRetry Called when the person asks to try again
 */
@Composable
private fun FailureBlock(
    state: AuthUiState.Failed,
    onRetry: () -> Unit,
) {
    Text(
        text = stringResource(MessageKeys.resolve(state.messageKey)),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.testTag(TAG_ERROR),
    )
    if (state.retryable) {
        Button(
            onClick = onRetry,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = Reach.touch)
                    .testTag(TAG_RETRY),
        ) {
            Text(
                text = stringResource(R.string.auth_retry),
                style = MaterialTheme.typography.labelLarge,
            )
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
        // **`Reach.touch`, which the design system specified and no
        // screen used.** A default Button is 40dp tall — under the
        // 48dp floor this project set for anything tappable, and the
        // phones it targets are not ones you tap precisely.
        modifier =
            Modifier
                .fillMaxWidth()
                .heightIn(min = Reach.touch)
                .testTag(TAG_REQUEST_CODE),
    ) {
        Text(
            text = stringResource(R.string.auth_request_code),
            style = MaterialTheme.typography.labelLarge,
        )
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
    Text(
        text = stringResource(R.string.auth_code_sent),
        style = MaterialTheme.typography.bodyMedium,
    )

    // **No verify button.** The code is exactly six digits, so when
    // the sixth arrives there is nothing left to decide — a button
    // would be one more tap between a teacher and their classes, and
    // it would leave the SMS-autofill path waiting on a gesture after
    // Android has already filled all six.
    OtpField(
        code = code,
        onCodeChange = onCodeChange,
        onComplete = onSubmit,
        state = OtpFieldState.EDITING,
        modifier = Modifier.fillMaxWidth(),
    )

    Text(
        text = stringResource(R.string.auth_code_auto_checks),
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

const val TAG_PHONE_FIELD = "auth_phone_field"
const val TAG_REQUEST_CODE = "auth_request_code"
const val TAG_RETRY = "auth_retry"
const val TAG_ERROR = "auth_error"
const val TAG_SENDING = "auth_sending"

/** The link to self-registration, for a number no teacher recorded. */
const val TAG_GO_TO_SIGNUP = "auth_go_to_signup"
const val TAG_SIGNED_IN = "auth_signed_in"
