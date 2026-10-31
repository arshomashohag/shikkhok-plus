package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BackArrow
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BrandHero
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.PromptLink
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.ui.PhoneNumberField
import com.shikkhokplus.app.core.ui.ResendCountdown
import com.shikkhokplus.app.core.ui.phoneIsValid
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/**
 * Sign-in: `O2` (the number) and `O3` (the code), as two steps.
 *
 * **This composable renders a [AuthUiState] and nothing else.** There is
 * no conditional here that depends on a domain value — no comparison, no
 * threshold, no inference about whether a number was recognised. Every
 * such decision was made by `AuthStateMapper` or the server [TC-9, D-31].
 * Which refusal message is shown is the server's `message_key`, and the
 * tries-left count is its `details`, shown as it arrived.
 *
 * **The two steps are two layouts.** `O2` carries the brand band and a
 * bar pinned to the foot; `O3` has no band at all, only a back arrow and
 * the heading "Enter the code". The earlier screen put the code boxes
 * under the band, which matched neither board.
 *
 * **The number is never repeated back.** The code step says a code was
 * sent if the number has an account, without naming the number.
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
    onResendCode: () -> Unit = {},
    onChangeNumber: () -> Unit = {},
) {
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }

    // Set when "Send code" is pressed on a malformed number, which is
    // then refused here and named under the field rather than sent.
    var phoneRejected by remember { mutableStateOf(false) }

    // Which step is on screen. `Sending` belongs to whichever step sent
    // it: a resend from the code step must not flash the number step.
    var onCodeStep by remember { mutableStateOf(false) }
    onCodeStep =
        when (state) {
            AuthUiState.AwaitingCode,
            AuthUiState.CheckingCode,
            is AuthUiState.CodeRejected,
            -> true
            AuthUiState.Sending -> onCodeStep
            else -> false
        }

    // Bumped each time a code is freshly sent, which restarts the
    // resend countdown.
    var codeSentCount by remember { mutableIntStateOf(0) }
    LaunchedEffect(state) {
        if (state == AuthUiState.AwaitingCode) codeSentCount++
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.surface,
    ) {
        when {
            state == AuthUiState.Restoring -> LogoLoader()

            state == AuthUiState.SignedIn ->
                Text(
                    text = stringResource(R.string.auth_verify),
                    modifier = Modifier.testTag(TAG_SIGNED_IN),
                )

            onCodeStep ->
                CodeStep(
                    code = code,
                    state = state,
                    codeSentCount = codeSentCount,
                    onCodeChange = { code = it },
                    onSubmit = { onSubmitCode(code) },
                    onResend = {
                        code = ""
                        onResendCode()
                    },
                    onChangeNumber = {
                        code = ""
                        onChangeNumber()
                    },
                    onGoToSignup = onGoToSignup,
                )

            else ->
                NumberStep(
                    phone = phone,
                    state = state,
                    phoneRejected = phoneRejected,
                    onPhoneChange = {
                        phone = it
                        phoneRejected = false
                    },
                    onSubmit = {
                        if (phoneIsValid(phone)) {
                            onRequestCode(phone)
                        } else {
                            phoneRejected = true
                        }
                    },
                    onRetry = onRetry,
                    onGoToSignup = onGoToSignup,
                )
        }

        // **Over the step, centred on the window.** The board shows a
        // spinner on the button; the loader is the app-wide overlay
        // instead, by the person's own rule, and the step stays visible
        // beneath its scrim.
        when (state) {
            AuthUiState.Sending ->
                LogoLoader(
                    modifier = Modifier.testTag(TAG_SENDING),
                    size = 72.dp,
                    label = stringResource(R.string.auth_sending),
                )
            AuthUiState.CheckingCode ->
                LogoLoader(
                    modifier = Modifier.testTag(TAG_CHECKING_CODE),
                    size = 72.dp,
                    label = stringResource(R.string.auth_checking_code),
                )
            else -> Unit
        }
    }
}

/**
 * `O2`: the brand band, the number, and a bar pinned to the foot.
 *
 * **One scrolling column at least the window's height.** The bar sits
 * at the foot of a tall phone, as the board draws it, and on a short
 * one the whole step scrolls rather than squeezing the field out of
 * sight -- the regression this screen already caught once, at 320x414.
 *
 * @param phone The number typed so far
 * @param state What to render
 * @param phoneRejected Whether "Send code" refused a malformed number
 * @param onPhoneChange Called on each edit
 * @param onSubmit Called from "Send code"
 * @param onRetry Called from a retryable failure's retry
 * @param onGoToSignup Called from "Create account"
 */
@Composable
private fun NumberStep(
    phone: String,
    state: AuthUiState,
    phoneRejected: Boolean,
    onPhoneChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onRetry: () -> Unit,
    onGoToSignup: () -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val roomForTallHero = maxHeight >= TALL_HERO_MIN_HEIGHT
        val minHeight: Dp = maxHeight

        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Column(
                modifier = Modifier.fillMaxWidth().heightIn(min = minHeight),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    // Tall on the empty first screen; compact once a
                    // number is in, so the field clears the keyboard.
                    BrandHero(
                        compact = phone.isNotEmpty() || state !is AuthUiState.Idle || !roomForTallHero,
                        tagline = stringResource(R.string.auth_tagline),
                    )
                    NumberBody(
                        phone = phone,
                        state = state,
                        phoneRejected = phoneRejected,
                        onPhoneChange = onPhoneChange,
                        onRetry = onRetry,
                    )
                }
                NumberBar(
                    sending = state == AuthUiState.Sending,
                    enabled = phone.isNotBlank() && state != AuthUiState.Sending,
                    onSubmit = onSubmit,
                    onGoToSignup = onGoToSignup,
                )
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
 * The number step's body: heading, field, and any failure.
 *
 * @param phone The number typed so far
 * @param state What to render
 * @param phoneRejected Whether "Send code" refused a malformed number
 * @param onPhoneChange Called on each edit
 * @param onRetry Called from a retryable failure's retry
 */
@Composable
private fun NumberBody(
    phone: String,
    state: AuthUiState,
    phoneRejected: Boolean,
    onPhoneChange: (String) -> Unit,
    onRetry: () -> Unit,
) {
    // A refused NUMBER belongs under the number, whoever refused it;
    // every other failure is a banner beneath the field.
    val numberRefused = state is AuthUiState.Failed && state.messageKey in PHONE_MESSAGE_KEYS
    val fieldError =
        if (phoneRejected || numberRefused) stringResource(R.string.phone_invalid) else null

    Column(
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.auth_headline),
            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
        )
        PhoneNumberField(
            value = phone,
            onValueChange = onPhoneChange,
            label = stringResource(R.string.auth_phone_label),
            help = if (phone.isEmpty()) stringResource(R.string.auth_subhead) else null,
            error = fieldError,
            large = true,
            fieldModifier = Modifier.testTag(TAG_PHONE_FIELD),
        )
        if (state is AuthUiState.Failed && !numberRefused) {
            Banner(
                title = stringResource(MessageKeys.resolve(state.messageKey)),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_ERROR),
            )
            if (state.retryable) {
                SecondaryButton(
                    text = stringResource(R.string.auth_retry),
                    onClick = onRetry,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                )
            }
        }
    }
}

/**
 * The bar pinned to the number step's foot.
 *
 * @param sending Whether a code is on its way
 * @param enabled Whether "Send code" can be pressed
 * @param onSubmit Called from "Send code"
 * @param onGoToSignup Called from "Create account"
 */
@Composable
private fun NumberBar(
    sending: Boolean,
    enabled: Boolean,
    onSubmit: () -> Unit,
    onGoToSignup: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PrimaryButton(
            text = stringResource(R.string.auth_request_code),
            onClick = onSubmit,
            // Disabled until there is something to send, rather than
            // letting the server refuse an empty number.
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().testTag(TAG_REQUEST_CODE),
        )
        if (sending) {
            Text(
                text = stringResource(R.string.auth_sending_note),
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth(),
            )
        } else {
            PromptLink(
                prompt = stringResource(R.string.auth_new_here),
                link = stringResource(R.string.auth_go_to_signup),
                onClick = onGoToSignup,
                linkModifier = Modifier.testTag(TAG_GO_TO_SIGNUP),
            )
        }
    }
}

/** Message keys naming a malformed number, from either route. */
internal val PHONE_MESSAGE_KEYS: Set<String> =
    setOf("phone.invalid", "signup.phone.invalid")

/**
 * `O3`: the code step, with a back arrow and no brand band.
 *
 * **No verify button.** The code is exactly six digits, so when the
 * sixth arrives there is nothing left to decide — a button would be one
 * more tap between a teacher and their classes, and it would leave the
 * SMS-autofill path waiting on a gesture after Android has already
 * filled all six.
 *
 * @param code The digits typed so far
 * @param state What to render
 * @param codeSentCount Restarts the resend countdown when it changes
 * @param onCodeChange Called on each edit
 * @param onSubmit Called on the sixth digit, or from a retry
 * @param onResend Called to ask for a new code
 * @param onChangeNumber Called from Back and from "Change"
 * @param onGoToSignup Called from "Create account"
 */
@Composable
private fun CodeStep(
    code: String,
    state: AuthUiState,
    codeSentCount: Int,
    onCodeChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onResend: () -> Unit,
    onChangeNumber: () -> Unit,
    onGoToSignup: () -> Unit,
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onChangeNumber, modifier = Modifier.testTag(TAG_CODE_BACK)) {
                BackArrow(contentDescription = stringResource(R.string.action_back))
            }
        }

        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 4.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = stringResource(R.string.auth_code_label),
                style = MaterialTheme.typography.headlineMedium,
            )

            // Shown for ANY number, known or not: the server's response
            // is identical either way, and the copy says "if this number
            // has an account" so the screen does not imply recognition
            // [BR2.7]. "Change" sits at its end, as the board draws it.
            Column(verticalArrangement = Arrangement.spacedBy(0.dp)) {
                Text(
                    text = stringResource(R.string.auth_code_sent),
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (state != AuthUiState.CheckingCode) {
                    TextAction(
                        text = stringResource(R.string.auth_change),
                        onClick = onChangeNumber,
                        modifier = Modifier.testTag(TAG_CHANGE_NUMBER),
                    )
                }
            }

            val rejected = state as? AuthUiState.CodeRejected
            val wrong = rejected?.messageKey == WRONG_KEY && rejected.attemptsLeft != null
            OtpField(
                code = code,
                onCodeChange = onCodeChange,
                onComplete = onSubmit,
                state =
                    when {
                        state == AuthUiState.CheckingCode -> OtpFieldState.CHECKING
                        rejected != null -> OtpFieldState.WRONG
                        else -> OtpFieldState.EDITING
                    },
                enabled = state != AuthUiState.CheckingCode,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
            )

            when {
                rejected == null -> {
                    Hint(
                        stringResource(
                            if (code.isEmpty()) R.string.auth_code_autofill_hint else R.string.auth_code_auto_checks,
                        ),
                    )
                    ResendCountdown(
                        restartKey = codeSentCount,
                        onResend = onResend,
                        actionModifier = Modifier.testTag(TAG_RESEND_CODE),
                        waitModifier = Modifier.testTag(TAG_RESEND_WAIT),
                    )
                }

                wrong -> {
                    Text(
                        text = stringResource(R.string.auth_otp_wrong, rejected!!.attemptsLeft!!),
                        style = MaterialTheme.typography.bodyMedium.copy(fontSize = 15.sp, lineHeight = 24.sp),
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag(TAG_CODE_ERROR),
                    )
                    Hint(stringResource(R.string.auth_otp_wrong_hint))
                    ResendCountdown(
                        restartKey = codeSentCount,
                        onResend = onResend,
                        actionModifier = Modifier.testTag(TAG_RESEND_CODE),
                        waitModifier = Modifier.testTag(TAG_RESEND_WAIT),
                    )
                }

                else -> {
                    // Expired, spent, or not checkable: this code is done
                    // with, so the way on is a new one.
                    val expired = rejected!!.messageKey == EXPIRED_KEY
                    Banner(
                        title = stringResource(MessageKeys.resolve(rejected.messageKey)),
                        body = if (expired) stringResource(R.string.auth_otp_expired_body) else null,
                        tone = BannerTone.ERROR,
                        modifier = Modifier.testTag(TAG_CODE_ERROR),
                    )
                    if (rejected.retryable) {
                        SecondaryButton(
                            text = stringResource(R.string.auth_retry),
                            onClick = onSubmit,
                            modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                        )
                    }
                    PrimaryButton(
                        text = stringResource(R.string.auth_resend),
                        onClick = onResend,
                        modifier = Modifier.fillMaxWidth().testTag(TAG_RESEND_CODE),
                    )
                }
            }

            // **The way out for a number nobody registered.** The server
            // answers every number alike, so reaching this screen says
            // nothing about registration -- and an unregistered number,
            // including one a teacher added, is sent no code. Reported
            // from a device: a student added by a teacher pressed Sign in
            // and waited here with no route onward.
            if (state != AuthUiState.CheckingCode) {
                Hint(stringResource(R.string.auth_no_code_hint))
                TextAction(
                    text = stringResource(R.string.auth_create_account),
                    onClick = onGoToSignup,
                    modifier = Modifier.testTag(TAG_NO_CODE_SIGNUP),
                )
            }
        }
    }
}

/**
 * A grey line of guidance under the code boxes.
 *
 * @param text What it says
 */
@Composable
private fun Hint(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** The refusal of a wrong code, which carries the tries left. */
private const val WRONG_KEY = "auth.otp.wrong"

/** The refusal of a code presented too late. */
private const val EXPIRED_KEY = "auth.otp.expired"

const val TAG_PHONE_FIELD = "auth_phone_field"
const val TAG_REQUEST_CODE = "auth_request_code"
const val TAG_RETRY = "auth_retry"
const val TAG_ERROR = "auth_error"
const val TAG_SENDING = "auth_sending"
const val TAG_CHECKING_CODE = "auth_checking_code"
const val TAG_CODE_ERROR = "auth_code_error"
const val TAG_RESEND_CODE = "auth_resend_code"
const val TAG_CHANGE_NUMBER = "auth_change_number"

/** The code step's back arrow, which returns to the number. */
const val TAG_CODE_BACK = "auth_code_back"

/** The countdown before a new code may be asked for. */
const val TAG_RESEND_WAIT = "auth_resend_wait"

/** The link to self-registration, for a number no teacher recorded. */
const val TAG_GO_TO_SIGNUP = "auth_go_to_signup"

/** The same route, offered on the code step to a number sent no code. */
const val TAG_NO_CODE_SIGNUP = "auth_no_code_signup"
const val TAG_SIGNED_IN = "auth_signed_in"
