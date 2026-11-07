package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BackArrow
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.ui.RECOVERY_CODE_MAX
import com.shikkhokplus.app.core.ui.recoveryCodeSendable
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The second step's heading, either mode. */
const val TAG_SECOND_STEP: String = "auth_second_step"

/** The recovery-code field. */
const val TAG_RECOVERY_FIELD: String = "auth_recovery_field"

/** Continue, under the recovery-code field. */
const val TAG_RECOVERY_SUBMIT: String = "auth_recovery_submit"

/** The switch between the authenticator code and a recovery code. */
const val TAG_TOGGLE_RECOVERY: String = "auth_toggle_recovery"

/** The second step's refusal. */
const val TAG_SECOND_STEP_ERROR: String = "auth_second_step_error"

/** The second step's back arrow, which returns to the number. */
const val TAG_SECOND_STEP_BACK: String = "auth_second_step_back"

/**
 * The sign-in's second step [0028]: the code from the authenticator app,
 * or a recovery code instead.
 *
 * **Drawn like the SMS code step, on purpose.** Six boxes that check
 * themselves on the sixth digit, the same keyboard, the same back arrow;
 * a person who has just typed one code meets the same control for the
 * next. A recovery code is letters and a dash, so it gets an ordinary
 * field and a Continue button instead.
 *
 * **Renders the state and nothing else.** Which refusal is shown is the
 * server's `message_key`; whether a retry is offered is its `retryable`.
 * A lapsed challenge never reaches here: the mapper sends it back to the
 * number step, where a new SMS code is asked for.
 *
 * @param state The second step's state
 * @param onSubmit Called with the code to check, and to retry
 * @param onToggleRecovery Called to switch between the two kinds of code
 * @param onBack Called from the back arrow: back to the number
 */
@Composable
internal fun SecondStep(
    state: AuthUiState.SecondStep,
    onSubmit: (String) -> Unit,
    onToggleRecovery: () -> Unit,
    onBack: () -> Unit,
) {
    var code by remember { mutableStateOf("") }
    var recoveryCode by remember { mutableStateOf("") }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack, modifier = Modifier.testTag(TAG_SECOND_STEP_BACK)) {
                BackArrow(contentDescription = stringResource(R.string.action_back))
            }
        }

        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            val recovery = state.useRecovery
            val title = if (recovery) R.string.two_step_signin_recovery_title else R.string.two_step_signin_title
            val body = if (recovery) R.string.two_step_signin_recovery_body else R.string.two_step_signin_body
            Text(
                text = stringResource(title),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.testTag(TAG_SECOND_STEP),
            )
            Text(text = stringResource(body), style = MaterialTheme.typography.bodyMedium)

            if (recovery) {
                RecoveryEntry(
                    value = recoveryCode,
                    checking = state.checking,
                    onChange = { recoveryCode = it.take(RECOVERY_CODE_MAX) },
                    onSubmit = { onSubmit(recoveryCode.trim()) },
                )
            } else {
                OtpField(
                    code = code,
                    onCodeChange = { code = it },
                    onComplete = { onSubmit(code) },
                    state =
                        when {
                            state.checking -> OtpFieldState.CHECKING
                            state.messageKey != null -> OtpFieldState.WRONG
                            else -> OtpFieldState.EDITING
                        },
                    enabled = !state.checking,
                    modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
                )
            }

            state.messageKey?.let { key ->
                Text(
                    text = stringResource(MessageKeys.resolve(key)),
                    style = BodyCompact,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.testTag(TAG_SECOND_STEP_ERROR),
                )
                if (state.retryable) {
                    SecondaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = { onSubmit(if (recovery) recoveryCode.trim() else code) },
                        modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                    )
                }
            }

            if (state.checking) {
                LogoLoader(
                    modifier = Modifier.testTag(TAG_CHECKING_CODE),
                    size = 72.dp,
                    label = stringResource(R.string.auth_checking_code),
                )
            } else {
                TextAction(
                    text =
                        stringResource(
                            if (recovery) R.string.two_step_use_app else R.string.two_step_use_recovery,
                        ),
                    onClick = {
                        code = ""
                        recoveryCode = ""
                        onToggleRecovery()
                    },
                    modifier = Modifier.testTag(TAG_TOGGLE_RECOVERY),
                )
            }
        }
    }
}

/**
 * The recovery-code field and its Continue button.
 *
 * Continue waits for something the server could accept by length alone;
 * whether the code is right is the server's to say.
 *
 * @param value What is typed
 * @param checking Whether a code is with the server
 * @param onChange Called on each edit
 * @param onSubmit Called from Continue
 */
@Composable
private fun RecoveryEntry(
    value: String,
    checking: Boolean,
    onChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    ShikkhokTextField(
        value = value,
        onValueChange = onChange,
        label = stringResource(R.string.two_step_recovery_label),
        placeholder = RECOVERY_PLACEHOLDER,
        enabled = !checking,
        keyboardOptions =
            KeyboardOptions(
                keyboardType = KeyboardType.Ascii,
                capitalization = KeyboardCapitalization.Characters,
                autoCorrectEnabled = false,
            ),
        fieldModifier = Modifier.testTag(TAG_RECOVERY_FIELD),
    )
    PrimaryButton(
        text = stringResource(R.string.two_step_continue),
        onClick = onSubmit,
        enabled = !checking && recoveryCodeSendable(value),
        modifier = Modifier.fillMaxWidth().testTag(TAG_RECOVERY_SUBMIT),
    )
}

/**
 * The shape of a recovery code, as a placeholder. Not text to translate:
 * it is the code's format, the same in every language.
 */
internal const val RECOVERY_PLACEHOLDER = "XXXXX-XXXXX"
