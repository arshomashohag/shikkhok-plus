package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
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
import com.shikkhokplus.app.core.ui.AutofillHint
import com.shikkhokplus.app.core.ui.AvailabilityHint
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.core.ui.UsernameField
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.auth.SignupStateMapper

/** The replacement step's root. */
const val TAG_REPLACE_USERNAME: String = "auth_replace_username"

/** The replacement step's username field. */
const val TAG_REPLACE_USERNAME_FIELD: String = "auth_replace_username_field"

/** Continue, on the replacement step. */
const val TAG_REPLACE_USERNAME_CONTINUE: String = "auth_replace_username_continue"

/** The replacement step's back arrow. */
const val TAG_REPLACE_USERNAME_BACK: String = "auth_replace_username_back"

/**
 * "Choose another username": the code was right, but the name the
 * sign-up chose was taken meanwhile [FR2.2, W2 step 3].
 *
 * **Renders the state and nothing else.** Which refusal goes under the
 * field is the same key set the sign-up form uses; anything else is a
 * banner. The six digits are not here: the ViewModel holds them, which
 * is why the step still submits after a recreation.
 *
 * **The typed name survives a rotation** (`rememberSaveable`); it is not
 * a secret [NFR3.4]. There is no password field on this step.
 *
 * @param state What to render
 * @param availability What the live check says about the typed name
 * @param onEdited Called on each accepted edit
 * @param onSubmit Called from Continue and from Retry, with the name
 * @param onBack Called from the back arrow: back to the code flow's
 *   first step, forgetting the held code
 */
@Composable
fun ReplaceUsernameStep(
    state: AuthUiState.ReplaceUsername,
    availability: AvailabilityState,
    onEdited: (String) -> Unit,
    onSubmit: (String) -> Unit,
    onBack: () -> Unit,
) {
    var username by rememberSaveable { mutableStateOf("") }
    val fieldKey = state.messageKey?.takeIf { it in SignupStateMapper.USERNAME_MESSAGE_KEYS }
    val bannerKey = state.messageKey?.takeIf { fieldKey == null }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag(TAG_REPLACE_USERNAME)) {
        BackRow(onBack = onBack, tag = TAG_REPLACE_USERNAME_BACK)
        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.auth_replace_username_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = stringResource(R.string.auth_replace_username_body, state.previous),
                style = MaterialTheme.typography.bodyMedium,
            )
            UsernameField(
                value = username,
                onValueChange = {
                    username = it
                    onEdited(it)
                },
                label = stringResource(R.string.signup_username_label),
                autofill = AutofillHint.NEW_USERNAME,
                error = fieldKey?.let { stringResource(MessageKeys.resolve(it)) },
                enabled = !state.checking,
                fieldModifier = Modifier.testTag(TAG_REPLACE_USERNAME_FIELD),
            )
            if (fieldKey == null) AvailabilityHint(state = availability, help = null)
            bannerKey?.let { key ->
                Banner(
                    title = stringResource(MessageKeys.resolve(key)),
                    tone = BannerTone.ERROR,
                    modifier = Modifier.testTag(TAG_ERROR),
                )
                if (state.retryable) {
                    SecondaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = { onSubmit(username) },
                        modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                    )
                }
            }
            PrimaryButton(
                text = stringResource(R.string.auth_replace_username_continue),
                onClick = { onSubmit(username) },
                enabled = username.isNotBlank() && !state.checking,
                modifier = Modifier.fillMaxWidth().testTag(TAG_REPLACE_USERNAME_CONTINUE),
            )
        }
    }
    if (state.checking) {
        LogoLoader(
            modifier = Modifier.testTag(TAG_CHECKING_CODE),
            size = 72.dp,
            label = stringResource(R.string.auth_checking_code),
        )
    }
}
