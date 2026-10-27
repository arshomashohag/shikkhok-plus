package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.BrandHero
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.Spacing
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

    // **`O2`'s three bands**, which the app did not have: a blue
    // branding hero, the content centred in what is left, and the
    // action pinned at the bottom. It was a single top-aligned column
    // instead, so the number field sat under the app bar with the
    // whole screen empty beneath it.
    //
    // No `ScreenScaffold` here: this screen has no app bar at all in
    // the design — the hero IS the top, and a bar above it would be a
    // second header over a branding band.
    // **One scrolling column, not three competing bands.** The
    // artboard draws a hero, a centred body and a pinned action bar,
    // and translating that as a fixed hero plus a weighted body plus
    // a fixed bar fails on a short screen: on a 320x414 viewport the
    // hero alone takes 260px, so the weighted band collapsed to 6px
    // and the number field scrolled out of a window too small to see
    // it. Found by printing the semantic tree, not by guessing.
    //
    // Scrolling the whole screen keeps the artboard's ORDER and
    // proportions on a tall phone — hero, content, action at the foot
    // — while guaranteeing that nothing is ever unreachable on a
    // short one. `Arrangement.Center` on the inner column is what
    // gives the vertical centring the design asks for when there is
    // room to spare.
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        // **The hero's height is a function of the screen, not only
        // the state.** The artboard draws the tall band on a 760dp
        // phone; on a short screen the same band leaves no room for
        // the field and the action beneath it. `BoxWithConstraints`
        // lets the tall version appear only where it fits.
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val roomForTallHero = maxHeight >= TALL_HERO_MIN_HEIGHT

            Column(
                modifier =
                    Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState()),
            ) {
            BrandHero(
                compact = state !is AuthUiState.Idle || !roomForTallHero,
                tagline = stringResource(R.string.auth_tagline),
            )

            Column(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .padding(
                            horizontal = Spacing.screen,
                            vertical = Spacing.section,
                        ),
                verticalArrangement = Arrangement.spacedBy(Spacing.listItem),
            ) {
                when (state) {
                    AuthUiState.Restoring -> LogoLoader()

                    AuthUiState.Idle,
                    is AuthUiState.Failed,
                    -> {
                        Text(
                            text = stringResource(R.string.auth_headline),
                            style = MaterialTheme.typography.titleLarge,
                        )
                        PhoneEntry(
                            phone = phone,
                            onPhoneChange = { phone = it },
                        )
                        if (state is AuthUiState.Failed) {
                            FailureBlock(state = state, onRetry = onRetry)
                        }
                        ActionBar(
                            onSubmit = { onRequestCode(phone) },
                            onGoToSignup = onGoToSignup,
                            enabled = phone.isNotBlank(),
                        )
                    }

                    AuthUiState.Sending -> LogoLoader(
                        modifier = Modifier.testTag(TAG_SENDING),
                        size = 72.dp,
                        label = stringResource(R.string.auth_sending),
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
            }
            }
        }
    }
}

/**
 * The shortest screen that can hold the tall branding band and still
 * show the number field and its action without scrolling.
 *
 * Below this the compact band is used instead. 560dp is comfortably
 * under any current phone in portrait and above the 414dp the tests
 * render at, which is what makes the short case covered rather than
 * assumed.
 */
private val TALL_HERO_MIN_HEIGHT = 560.dp

/**
 * The pinned foot of the sign-in screen.
 *
 * @param onSubmit Called to request a code
 * @param onGoToSignup Called to open self-registration
 * @param enabled Whether a number has been entered
 */
@Composable
private fun ActionBar(
    onSubmit: () -> Unit,
    onGoToSignup: () -> Unit,
    enabled: Boolean,
) {
    Column(
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(
                    start = Spacing.screen,
                    end = Spacing.screen,
                    top = Spacing.tight,
                    bottom = Spacing.section,
                ),
        verticalArrangement = Arrangement.spacedBy(Spacing.tight),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Button(
            onClick = onSubmit,
            // Disabled until there is something to send, rather than
            // letting the server refuse an empty number.
            enabled = enabled,
            shape = RoundedCornerShape(28.dp),
            modifier =
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = Reach.moneyButton)
                    .testTag(TAG_REQUEST_CODE),
        ) {
            Text(
                text = stringResource(R.string.auth_request_code),
                style = MaterialTheme.typography.labelLarge,
            )
        }
        TextButton(
            onClick = onGoToSignup,
            modifier = Modifier.testTag(TAG_GO_TO_SIGNUP),
        ) {
            Text(text = stringResource(R.string.auth_go_to_signup))
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
