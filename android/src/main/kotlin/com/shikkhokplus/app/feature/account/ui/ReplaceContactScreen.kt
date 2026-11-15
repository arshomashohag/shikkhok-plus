package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import com.shikkhokplus.app.core.ui.PasswordField
import com.shikkhokplus.app.core.ui.identifierIsWellFormed
import com.shikkhokplus.app.feature.account.ReplaceContactUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The new value on the replace screen. */
const val TAG_REPLACE_VALUE: String = "replace_contact_value"

/** The current password on the replace screen. */
const val TAG_REPLACE_PASSWORD: String = "replace_contact_password"

/** Send code, on the replace screen. */
const val TAG_REPLACE_SEND: String = "replace_contact_send"

/** The code step's note, on the replace screen. */
const val TAG_REPLACE_CODE_STEP: String = "replace_contact_code_step"

/** A refusal on the replace screen. */
const val TAG_REPLACE_ERROR: String = "replace_contact_error"

/** Retry, on the replace screen. */
const val TAG_REPLACE_RETRY: String = "replace_contact_retry"

/** "Send a new code" on the code step: back to the entry step. */
const val TAG_REPLACE_RESEND: String = "replace_contact_resend"

/**
 * What the replace screen can ask for.
 *
 * @property onRequestCode Sends a code to the new value, with the password; also the retry
 * @property onSubmitCode Checks the six digits; also the retry
 * @property onChange Back to the entry step ("Change", "Send a new code")
 * @property onSetPassword Opens setting a password
 * @property onBack Leaves the screen
 */
data class ReplaceContactActions(
    val onRequestCode: (String, String) -> Unit = { _, _ -> },
    val onSubmitCode: (String) -> Unit = {},
    val onChange: () -> Unit = {},
    val onSetPassword: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Replace the account's phone or email [W6 step 4, FR8.2]: the new value
 * and the current password, then the code sent to the new value.
 *
 * **The new value survives a rotation; the password does not** [NFR3.4].
 * The value is held at the screen's level, so "Send a new code" returns
 * to the entry step with it kept; the password lives in the entry step's
 * `remember`, so it is gone once the code is sent and is typed again for
 * a new code.
 *
 * @param state What to render
 * @param actions What the controls call
 */
@Composable
fun ReplaceContactScreen(state: ReplaceContactUiState, actions: ReplaceContactActions) {
    var value by rememberSaveable { mutableStateOf("") }
    val phone = state.kind == IdentifierKind.PHONE
    ScreenScaffold(
        title =
            stringResource(
                if (phone) R.string.contacts_replace_phone_title else R.string.contacts_replace_email_title,
            ),
        onBack = actions.onBack,
    ) {
        when (state) {
            is ReplaceContactUiState.Entering -> Entry(state, value, { value = it }, actions)
            is ReplaceContactUiState.AwaitingCode -> CodeStep(state, actions)
            is ReplaceContactUiState.Replaced ->
                Banner(
                    title =
                        stringResource(
                            if (phone) R.string.contacts_replaced_phone else R.string.contacts_replaced_email,
                        ),
                    tone = BannerTone.NEUTRAL,
                )
        }
    }
    val busy =
        (state as? ReplaceContactUiState.Entering)?.sending == true ||
            (state as? ReplaceContactUiState.AwaitingCode)?.checking == true
    if (busy) LogoLoader(size = 72.dp, label = stringResource(R.string.auth_checking_code))
}

/**
 * The entry step: the new value, the current password, Send code.
 *
 * @param state The entry state
 * @param value The new value, held by the screen
 * @param onValueChange Called on each edit of it
 * @param actions What the controls call
 */
@Composable
private fun Entry(
    state: ReplaceContactUiState.Entering,
    value: String,
    onValueChange: (String) -> Unit,
    actions: ReplaceContactActions,
) {
    var password by remember { mutableStateOf("") }
    var rejected by remember { mutableStateOf(false) }
    val send = {
        if (identifierIsWellFormed(Identifier(state.kind, value))) {
            actions.onRequestCode(value, password)
        } else {
            rejected = true
        }
    }
    IdentifierField(
        kind = state.kind,
        value = value,
        onValueChange = {
            onValueChange(it)
            rejected = false
        },
        phoneLabel = stringResource(R.string.contacts_new_phone_label),
        error =
            when {
                rejected && state.kind == IdentifierKind.PHONE -> stringResource(R.string.phone_invalid)
                rejected -> stringResource(R.string.signup_email_invalid)
                else -> state.valueKey?.let { stringResource(MessageKeys.resolve(it)) }
            },
        fieldModifier = Modifier.testTag(TAG_REPLACE_VALUE),
    )
    PasswordField(
        value = password,
        onValueChange = { password = it },
        label = stringResource(R.string.account_password_current_label),
        error = state.passwordKey?.let { stringResource(MessageKeys.resolve(it)) },
        enabled = !state.sending,
        fieldModifier = Modifier.testTag(TAG_REPLACE_PASSWORD),
    )
    state.bannerKey?.let { key ->
        Banner(
            title = stringResource(MessageKeys.resolve(key)),
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_REPLACE_ERROR),
        )
        if (state.offerSetPassword) TextAction(stringResource(R.string.contacts_set_password), actions.onSetPassword)
        if (state.retryable) {
            SecondaryButton(
                text = stringResource(R.string.auth_retry),
                onClick = send,
                modifier = Modifier.fillMaxWidth().testTag(TAG_REPLACE_RETRY),
            )
        }
    }
    PrimaryButton(
        text = stringResource(R.string.auth_request_code),
        onClick = send,
        enabled = value.isNotBlank() && password.isNotEmpty() && !state.sending,
        modifier = Modifier.fillMaxWidth().testTag(TAG_REPLACE_SEND),
    )
}

/**
 * The code step: where the code went, the six digits, Change and a new code.
 *
 * @param state The code state
 * @param actions What the controls call
 */
@Composable
private fun CodeStep(state: ReplaceContactUiState.AwaitingCode, actions: ReplaceContactActions) {
    var code by remember { mutableStateOf("") }
    Text(
        text =
            stringResource(
                if (state.kind == IdentifierKind.PHONE) {
                    R.string.contacts_code_sent_new_phone
                } else {
                    R.string.contacts_code_sent_new_email
                },
            ),
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.testTag(TAG_REPLACE_CODE_STEP),
    )
    TextAction(stringResource(R.string.auth_change), actions.onChange, enabled = !state.checking)
    OtpField(
        code = code,
        onCodeChange = { code = it },
        onComplete = { actions.onSubmitCode(code) },
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
        if (key == WRONG_CODE && attempts != null) {
            Text(
                text = stringResource(R.string.auth_otp_wrong, attempts),
                style = BodyCompact,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag(TAG_REPLACE_ERROR),
            )
        } else {
            Banner(
                title = stringResource(MessageKeys.resolve(key)),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_REPLACE_ERROR),
            )
            if (state.retryable) {
                SecondaryButton(
                    text = stringResource(R.string.auth_retry),
                    onClick = { actions.onSubmitCode(code) },
                    modifier = Modifier.fillMaxWidth().testTag(TAG_REPLACE_RETRY),
                )
            }
        }
    }
    // A new code needs the password again, which is not kept: back to the entry step.
    TextAction(
        text = stringResource(R.string.auth_resend),
        onClick = actions.onChange,
        enabled = !state.checking,
        modifier = Modifier.testTag(TAG_REPLACE_RESEND),
    )
}

/** The refusal of a wrong code, which carries the tries left. */
private const val WRONG_CODE = "auth.otp.wrong"
