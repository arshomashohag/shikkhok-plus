package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.ui.IdentifierField
import com.shikkhokplus.app.core.ui.NewPasswordFields
import com.shikkhokplus.app.core.ui.PasswordField
import com.shikkhokplus.app.core.ui.ResendCountdown
import com.shikkhokplus.app.core.ui.identifierIsWellFormed
import com.shikkhokplus.app.feature.account.AddContactUiState
import com.shikkhokplus.app.feature.account.PasswordChangeUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The current-password field. */
const val TAG_CURRENT_PASSWORD: String = "account_current_password"

/** The save button on the password screen. */
const val TAG_PASSWORD_SAVE: String = "account_password_save"

/** A refusal on either account screen. */
const val TAG_ACCOUNT_ERROR: String = "account_error"

/** The retry on either account screen. */
const val TAG_ACCOUNT_RETRY: String = "account_retry"

/** The loader on either account screen. */
const val TAG_ACCOUNT_BUSY: String = "account_busy"

/** The phone or email field on the add-contact screen. */
const val TAG_CONTACT_FIELD: String = "account_contact_field"

/** Send code, on the add-contact screen. */
const val TAG_CONTACT_SEND: String = "account_contact_send"

/** The six code boxes, on the add-contact screen. */
const val TAG_CONTACT_CODE_STEP: String = "account_contact_code_step"

/** Change, on the add-contact code step. */
const val TAG_CONTACT_CHANGE: String = "account_contact_change"

/** Send a new code, on the add-contact code step. */
const val TAG_CONTACT_RESEND: String = "account_contact_resend"

/**
 * Set a first password, or change the current one.
 *
 * **Renders the state and nothing else.** Whether the current password is
 * asked for, and whether the title says "Set" or "Change", is
 * [PasswordChangeUiState.Editing.hasPassword], which the server decided.
 *
 * **Every password lives in `remember`, never in saved state.**
 *
 * @param state What to render
 * @param onSubmit Called with the current password (empty when none is
 *   asked for), the new one and its second copy; also the retry
 * @param onBack Called from the back arrow
 */
@Composable
fun PasswordChangeScreen(
    state: PasswordChangeUiState,
    onSubmit: (String, String, String) -> Unit,
    onBack: () -> Unit,
) {
    var current by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    val form = state as? PasswordChangeUiState.Editing
    val change = form?.hasPassword == true
    val busy = form?.saving == true
    val submit = { onSubmit(current, password, confirm) }

    ScreenScaffold(
        title =
            stringResource(
                if (change) R.string.account_password_change_title else R.string.account_password_set_title,
            ),
        onBack = onBack,
    ) {
        Text(
            text =
                stringResource(
                    if (change) R.string.account_password_change_body else R.string.account_password_set_body,
                ),
            style = MaterialTheme.typography.bodyMedium,
        )
        if (change) {
            PasswordField(
                value = current,
                onValueChange = { current = it },
                label = stringResource(R.string.account_password_current_label),
                enabled = !busy,
                fieldModifier = Modifier.testTag(TAG_CURRENT_PASSWORD),
            )
        }
        NewPasswordFields(
            password = password,
            onPasswordChange = { password = it },
            confirm = confirm,
            onConfirmChange = { confirm = it },
            enabled = !busy,
            onDone = submit,
        )
        form?.messageKey?.let { key ->
            Refusal(key = key, retryable = form.retryable, onRetry = submit)
        }
        PrimaryButton(
            text = stringResource(R.string.account_password_save),
            onClick = submit,
            enabled = !busy && password.isNotEmpty() && confirm.isNotEmpty() && (!change || current.isNotEmpty()),
            modifier = Modifier.fillMaxWidth().testTag(TAG_PASSWORD_SAVE),
        )
        Text(
            text = stringResource(R.string.account_password_sessions_note),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    if (busy) Busy(stringResource(R.string.auth_saving_password))
}

/**
 * Add a phone number or an email address the account lacks: the field,
 * then the code sent to it.
 *
 * **Renders the state and nothing else.** Which kind is being added is
 * fixed by the route; whether the code step shows is the state's type.
 * Adding a phone says why it matters: teachers find students and
 * guardians by number, so an email-only account sees its seats only once
 * a phone is on it.
 *
 * @param state What to render
 * @param onRequestCode Called with what was typed, to send a code; also
 *   the retry of a failed request
 * @param onSubmitCode Called with the six digits; also the retry
 * @param onResend Called to ask for a new code
 * @param onChange Called to go back and correct what was typed
 * @param onBack Called from the back arrow
 */
@Composable
fun AddContactScreen(
    state: AddContactUiState,
    onRequestCode: (String) -> Unit,
    onSubmitCode: (String) -> Unit,
    onResend: () -> Unit,
    onChange: () -> Unit,
    onBack: () -> Unit,
) {
    val phone = state.kind == IdentifierKind.PHONE
    ScreenScaffold(
        title = stringResource(if (phone) R.string.account_add_phone_title else R.string.account_add_email_title),
        onBack = onBack,
    ) {
        when (state) {
            is AddContactUiState.Entering -> ContactEntry(state, onRequestCode)
            is AddContactUiState.AwaitingCode -> ContactCode(state, onSubmitCode, onResend, onChange)
            is AddContactUiState.Added ->
                Banner(
                    title = stringResource(if (phone) R.string.account_phone_added else R.string.account_email_added),
                    tone = BannerTone.NEUTRAL,
                )
        }
    }
    val busy =
        (state as? AddContactUiState.Entering)?.sending == true ||
            (state as? AddContactUiState.AwaitingCode)?.checking == true
    if (busy) Busy(stringResource(R.string.auth_checking_code))
}

/**
 * The add-contact field and Send code.
 *
 * @param state The entry state
 * @param onRequestCode Called with what was typed
 */
@Composable
private fun ContactEntry(
    state: AddContactUiState.Entering,
    onRequestCode: (String) -> Unit,
) {
    // The phone or email survives a rotation; it is not a secret.
    var value by rememberSaveable { mutableStateOf("") }
    var rejected by remember { mutableStateOf(false) }
    val phone = state.kind == IdentifierKind.PHONE
    Text(
        text = stringResource(if (phone) R.string.account_add_phone_body else R.string.account_add_email_body),
        style = MaterialTheme.typography.bodyMedium,
    )
    IdentifierField(
        kind = state.kind,
        value = value,
        onValueChange = {
            value = it
            rejected = false
        },
        error =
            when {
                !rejected -> null
                phone -> stringResource(R.string.phone_invalid)
                else -> stringResource(R.string.signup_email_invalid)
            },
        fieldModifier = Modifier.testTag(TAG_CONTACT_FIELD),
    )
    state.messageKey?.let { Refusal(key = it, retryable = state.retryable, onRetry = { onRequestCode(value) }) }
    PrimaryButton(
        text = stringResource(R.string.auth_request_code),
        onClick = {
            if (identifierIsWellFormed(Identifier(state.kind, value))) onRequestCode(value) else rejected = true
        },
        enabled = value.isNotBlank() && !state.sending,
        modifier = Modifier.fillMaxWidth().testTag(TAG_CONTACT_SEND),
    )
}

/**
 * The add-contact code step.
 *
 * @param state The code state
 * @param onSubmitCode Called on the sixth digit, and from the retry
 * @param onResend Called to ask for a new code
 * @param onChange Called to correct what was typed
 */
@Composable
private fun ContactCode(
    state: AddContactUiState.AwaitingCode,
    onSubmitCode: (String) -> Unit,
    onResend: () -> Unit,
    onChange: () -> Unit,
) {
    var code by remember { mutableStateOf("") }
    var sentCount by remember { mutableIntStateOf(0) }
    LaunchedEffect(state) { if (state == AddContactUiState.AwaitingCode(state.kind)) sentCount++ }
    Text(
        text =
            stringResource(
                if (state.kind == IdentifierKind.PHONE) {
                    R.string.account_code_sent_phone
                } else {
                    R.string.account_code_sent_email
                },
            ),
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.testTag(TAG_CONTACT_CODE_STEP),
    )
    TextAction(
        text = stringResource(R.string.auth_change),
        onClick = onChange,
        enabled = !state.checking,
        modifier = Modifier.testTag(TAG_CONTACT_CHANGE),
    )
    OtpField(
        code = code,
        onCodeChange = { code = it },
        onComplete = { onSubmitCode(code) },
        state =
            when {
                state.checking -> OtpFieldState.CHECKING
                state.messageKey != null -> OtpFieldState.WRONG
                else -> OtpFieldState.EDITING
            },
        enabled = !state.checking,
        modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
    )
    state.messageKey?.let { key ->
        val attempts = state.attemptsLeft
        if (key == WRONG_CODE_KEY && attempts != null) {
            Text(
                text = stringResource(R.string.auth_otp_wrong, attempts),
                style = BodyCompact,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag(TAG_ACCOUNT_ERROR),
            )
        } else {
            Refusal(key = key, retryable = state.retryable, onRetry = { onSubmitCode(code) })
        }
    }
    ResendCountdown(
        restartKey = sentCount,
        onResend = {
            code = ""
            onResend()
        },
        actionModifier = Modifier.testTag(TAG_CONTACT_RESEND),
    )
}

/**
 * A refusal, in the server's words, with a retry when the server allows one.
 *
 * @param key The message key
 * @param retryable Whether to offer the retry
 * @param onRetry Called from the retry
 */
@Composable
private fun Refusal(key: String, retryable: Boolean, onRetry: () -> Unit) {
    Banner(
        title = stringResource(MessageKeys.resolve(key)),
        tone = BannerTone.ERROR,
        modifier = Modifier.testTag(TAG_ACCOUNT_ERROR),
    )
    if (retryable) {
        SecondaryButton(
            text = stringResource(R.string.auth_retry),
            onClick = onRetry,
            modifier = Modifier.fillMaxWidth().testTag(TAG_ACCOUNT_RETRY),
        )
    }
}

/**
 * The app-wide loader over a screen while it waits for the server.
 *
 * @param label What it is waiting for
 */
@Composable
private fun Busy(label: String) {
    LogoLoader(modifier = Modifier.testTag(TAG_ACCOUNT_BUSY), size = 72.dp, label = label)
}

/** The refusal of a wrong code, which carries the tries left. */
private const val WRONG_CODE_KEY = "auth.otp.wrong"
