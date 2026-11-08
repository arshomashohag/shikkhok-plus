package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.ui.AUTHENTICATOR_CODE_LENGTH
import com.shikkhokplus.app.core.ui.NewPasswordFields
import com.shikkhokplus.app.core.ui.RECOVERY_CODE_MAX
import com.shikkhokplus.app.core.ui.authenticatorCodeSendable
import com.shikkhokplus.app.core.ui.recoveryCodeSendable
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The choose-password step's heading. */
const val TAG_CHOOSE_PASSWORD: String = "auth_choose_password"

/** Its authenticator-or-recovery code field. */
const val TAG_SETUP_SECOND_CODE: String = "auth_setup_second_code"

/** Its switch between the authenticator code and a recovery code. */
const val TAG_SETUP_TOGGLE_RECOVERY: String = "auth_setup_toggle_recovery"

/** Its save button. */
const val TAG_SETUP_SUBMIT: String = "auth_setup_submit"

/** Its refusal. */
const val TAG_SETUP_ERROR: String = "auth_setup_error"

/** Its back arrow, to the code flow's first step. */
const val TAG_SETUP_BACK: String = "auth_setup_back"

/** The loader while the password is with the server. */
const val TAG_SETUP_CHECKING: String = "auth_setup_checking"

/**
 * The code flow's last step: choose a password, and with it the code
 * from the authenticator app when the account has one on.
 *
 * **Renders the state and nothing else.** Whether the authenticator field
 * appears is the server's `mfa_required`, carried by the state; which
 * refusal shows is a key the mapper or the server chose; whether a retry
 * is offered is the server's `retryable`.
 *
 * **Both passwords live in `remember`, never in saved state**, and are
 * gone when this step leaves composition.
 *
 * @param state The step's state
 * @param onSubmit Called with the password, its second copy and the
 *   authenticator or recovery code (empty when none is asked for); also
 *   the explicit retry
 * @param onToggleRecovery Called to switch the kind of code
 * @param onBack Called from the back arrow: back to the code flow's start
 */
@Composable
internal fun ChoosePasswordStep(
    state: AuthUiState.ChoosePassword,
    onSubmit: (String, String, String) -> Unit,
    onToggleRecovery: () -> Unit,
    onBack: () -> Unit,
) {
    var password by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var secondCode by remember { mutableStateOf("") }
    val submit = { onSubmit(password, confirm, secondCode.trim()) }
    val secondReady =
        !state.mfaRequired ||
            if (state.useRecovery) recoveryCodeSendable(secondCode) else authenticatorCodeSendable(secondCode)

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        BackRow(onBack = onBack, tag = TAG_SETUP_BACK)
        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = stringResource(R.string.auth_choose_password_title),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.testTag(TAG_CHOOSE_PASSWORD),
            )
            Text(
                text = stringResource(R.string.auth_choose_password_body),
                style = MaterialTheme.typography.bodyMedium,
            )
            NewPasswordFields(
                password = password,
                onPasswordChange = { password = it },
                confirm = confirm,
                onConfirmChange = { confirm = it },
                enabled = !state.checking,
            )
            if (state.mfaRequired) {
                SecondCodeField(
                    useRecovery = state.useRecovery,
                    value = secondCode,
                    enabled = !state.checking,
                    onChange = { secondCode = it },
                    onToggle = {
                        secondCode = ""
                        onToggleRecovery()
                    },
                )
            }
            state.messageKey?.let { key ->
                Text(
                    text = stringResource(MessageKeys.resolve(key)),
                    style = BodyCompact,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.testTag(TAG_SETUP_ERROR),
                )
                if (state.retryable) {
                    SecondaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = submit,
                        modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                    )
                }
            }
            PrimaryButton(
                text = stringResource(R.string.auth_choose_password_submit),
                onClick = submit,
                enabled = !state.checking && password.isNotEmpty() && confirm.isNotEmpty() && secondReady,
                modifier = Modifier.fillMaxWidth().testTag(TAG_SETUP_SUBMIT),
            )
        }
    }
    if (state.checking) {
        LogoLoader(
            modifier = Modifier.testTag(TAG_SETUP_CHECKING),
            size = 72.dp,
            label = stringResource(R.string.auth_saving_password),
        )
    }
}

/**
 * The authenticator code, or a recovery code instead, with the switch
 * between them.
 *
 * A plain field rather than the six self-submitting boxes: here the code
 * is one of three things sent together, so nothing should go on the
 * sixth digit.
 *
 * @param useRecovery Whether a recovery code is asked for
 * @param value What is typed
 * @param enabled Whether it can be edited
 * @param onChange Called on each edit
 * @param onToggle Called to switch the kind of code
 */
@Composable
private fun SecondCodeField(
    useRecovery: Boolean,
    value: String,
    enabled: Boolean,
    onChange: (String) -> Unit,
    onToggle: () -> Unit,
) {
    ShikkhokTextField(
        value = value,
        onValueChange = { typed ->
            onChange(
                if (useRecovery) {
                    typed.take(RECOVERY_CODE_MAX)
                } else {
                    typed.filter { it in '0'..'9' }.take(AUTHENTICATOR_CODE_LENGTH)
                },
            )
        },
        label =
            stringResource(
                if (useRecovery) R.string.two_step_recovery_label else R.string.auth_setup_authenticator_label,
            ),
        help =
            stringResource(
                if (useRecovery) R.string.two_step_signin_recovery_body else R.string.two_step_signin_body,
            ),
        placeholder = RECOVERY_PLACEHOLDER.takeIf { useRecovery },
        enabled = enabled,
        keyboardOptions =
            if (useRecovery) {
                KeyboardOptions(
                    keyboardType = KeyboardType.Ascii,
                    capitalization = KeyboardCapitalization.Characters,
                    autoCorrectEnabled = false,
                )
            } else {
                KeyboardOptions(keyboardType = KeyboardType.NumberPassword)
            },
        fieldModifier = Modifier.testTag(TAG_SETUP_SECOND_CODE),
    )
    TextAction(
        text = stringResource(if (useRecovery) R.string.two_step_use_app else R.string.two_step_use_recovery),
        onClick = onToggle,
        enabled = enabled,
        modifier = Modifier.testTag(TAG_SETUP_TOGGLE_RECOVERY),
    )
}
