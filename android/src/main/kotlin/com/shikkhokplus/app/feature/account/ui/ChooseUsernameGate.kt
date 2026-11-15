package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.ui.AutofillHint
import com.shikkhokplus.app.core.ui.AvailabilityHint
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.core.ui.UsernameField
import com.shikkhokplus.app.feature.account.ChooseUsernameUiState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.auth.SignupStateMapper

/** The choose-username gate's root. */
const val TAG_CHOOSE_USERNAME_GATE: String = "choose_username_gate"

/** Sign out, on the gate. */
const val TAG_CHOOSE_USERNAME_SIGN_OUT: String = "choose_username_sign_out"

/** The gate's username field. */
const val TAG_CHOOSE_USERNAME_FIELD: String = "choose_username_field"

/** Continue, on the gate. */
const val TAG_CHOOSE_USERNAME_CONTINUE: String = "choose_username_continue"

/** A refusal or a failure on the gate, shown as a banner. */
const val TAG_CHOOSE_USERNAME_ERROR: String = "choose_username_error"

/** The gate's retry. */
const val TAG_CHOOSE_USERNAME_RETRY: String = "choose_username_retry"

/** The loader over the gate while it waits. */
const val TAG_CHOOSE_USERNAME_BUSY: String = "choose_username_busy"

/**
 * "Choose your username": shown before anything else while the server
 * says the account has none [FR5.2, W4].
 *
 * **A root screen with no back arrow.** System Back finishes the app as
 * on any root; reopening it resolves the account and shows this again
 * while the server still says a username is required. The only other
 * way out is Sign out, which runs the app's one `endSession`.
 *
 * **Renders the state and nothing else.** A username refusal is shown
 * under the field; anything else is a banner, with Retry only when the
 * server said so or no answer arrived. The typed name survives a
 * rotation (it is not a secret, NFR3.4); there is no password here, the
 * first choice needs none [FR5.4].
 *
 * @param state What to render
 * @param availability What the live check says about the typed name
 * @param onEdited Called on each accepted edit
 * @param onSubmit Called from Continue with the name
 * @param onRetry Called from Retry
 * @param onSignOut Ends the session
 */
@Composable
fun ChooseUsernameGate(
    state: ChooseUsernameUiState,
    availability: AvailabilityState,
    onEdited: (String) -> Unit,
    onSubmit: (String) -> Unit,
    onRetry: () -> Unit,
    onSignOut: () -> Unit,
) {
    var username by rememberSaveable { mutableStateOf("") }
    val form = state as? ChooseUsernameUiState.Editing
    val busy = form?.saving == true || state == ChooseUsernameUiState.Rereading
    val fieldKey = form?.messageKey?.takeIf { it in SignupStateMapper.USERNAME_MESSAGE_KEYS }
    val bannerKey = form?.messageKey?.takeIf { fieldKey == null }

    Box(Modifier.fillMaxSize().testTag(TAG_CHOOSE_USERNAME_GATE)) {
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.choose_username_title),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.padding(top = 24.dp),
            )
            Text(
                text = stringResource(R.string.choose_username_body),
                style = MaterialTheme.typography.bodyMedium,
            )
            UsernameField(
                value = username,
                onValueChange = {
                    username = it
                    onEdited(it)
                },
                label = stringResource(R.string.signup_username_label),
                autofill = AutofillHint.USERNAME,
                error = fieldKey?.let { stringResource(MessageKeys.resolve(it)) },
                enabled = !busy,
                fieldModifier = Modifier.testTag(TAG_CHOOSE_USERNAME_FIELD),
            )
            if (fieldKey == null) AvailabilityHint(state = availability, help = null)
            bannerKey?.let { key ->
                Banner(
                    title = stringResource(MessageKeys.resolve(key)),
                    tone = BannerTone.ERROR,
                    modifier = Modifier.testTag(TAG_CHOOSE_USERNAME_ERROR),
                )
                if (form?.retryable == true) {
                    SecondaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = onRetry,
                        modifier = Modifier.fillMaxWidth().testTag(TAG_CHOOSE_USERNAME_RETRY),
                    )
                }
            }
            PrimaryButton(
                text = stringResource(R.string.choose_username_continue),
                onClick = { onSubmit(username) },
                enabled = username.isNotBlank() && !busy,
                modifier = Modifier.fillMaxWidth().testTag(TAG_CHOOSE_USERNAME_CONTINUE),
            )
            TextAction(
                text = stringResource(R.string.choose_username_sign_out),
                onClick = onSignOut,
                modifier = Modifier.testTag(TAG_CHOOSE_USERNAME_SIGN_OUT),
            )
        }
        if (busy) {
            LogoLoader(
                modifier = Modifier.testTag(TAG_CHOOSE_USERNAME_BUSY),
                size = 72.dp,
                label = stringResource(R.string.choose_username_continue),
            )
        }
    }
}
