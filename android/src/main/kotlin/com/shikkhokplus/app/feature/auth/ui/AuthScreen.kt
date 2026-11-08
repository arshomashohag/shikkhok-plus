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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BackArrow
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.BrandHero
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.PromptLink
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.ui.IdentifierField
import com.shikkhokplus.app.core.ui.IdentifierKindToggle
import com.shikkhokplus.app.core.ui.PasswordField
import com.shikkhokplus.app.core.ui.ResendCountdown
import com.shikkhokplus.app.core.ui.identifierIsWellFormed
import com.shikkhokplus.app.feature.auth.AuthStep
import com.shikkhokplus.app.feature.auth.AuthUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/**
 * Sign-in: the password form, the code flow (`O2` the identifier and
 * `O3` the code), choosing a password, and the authenticator step.
 *
 * **This composable renders a [AuthUiState] and nothing else.** There is
 * no conditional here that depends on a domain value — no comparison, no
 * threshold, no inference about whether an account exists. Every such
 * decision was made by `AuthStateMapper` or the server [TC-9, D-31].
 * Which refusal message is shown is the server's `message_key`, whether
 * the way to the code flow is offered beside it is the mapper's
 * `offerCodeFlow`, and the tries-left count is the server's `details`.
 *
 * **The identifier survives a rotation; no secret does** [L-20]. The
 * phone or email is kept in saved state; the password and the code are
 * kept in `remember` only, because saved instance state is a Bundle the
 * platform may write to disk, which this app never does with either.
 *
 * **Nothing is repeated back.** The code step says a code was sent if
 * the phone or email has an account, without naming it.
 *
 * Test tags are stable identifiers for the Compose UI test and the
 * device run; they are not user-visible text.
 *
 * @param state What to render
 * @param actions What each control does
 * @param modifier The layout modifier
 * @param codeDestination Whether the outstanding code went by SMS or by
 *   email, for the code step's copy
 */
@Composable
fun AuthScreen(
    state: AuthUiState,
    actions: AuthActions,
    modifier: Modifier = Modifier,
    codeDestination: IdentifierKind = IdentifierKind.PHONE,
) {
    var kind by rememberSaveable { mutableStateOf(IdentifierKind.PHONE) }
    var identifier by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }

    // Set when a form is submitted with a malformed identifier, which is
    // then refused here and named under the field rather than sent.
    var identifierRejected by remember { mutableStateOf(false) }

    // Which step is on screen. `Sending` belongs to whichever step sent
    // it: a resend from the code step must not flash the identifier step.
    var onCodeStep by remember { mutableStateOf(false) }
    onCodeStep = isCodeStep(state, wasCodeStep = onCodeStep)
    val onCodeRequest = isCodeRequestStep(state, onCodeStep)

    // Bumped each time a code is freshly sent, which restarts the
    // resend countdown.
    var codeSentCount by remember { mutableIntStateOf(0) }
    LaunchedEffect(state) {
        if (state == AuthUiState.AwaitingCode) codeSentCount++
        // A session exists or a code flow began: the typed password has
        // done its work, and is not kept on screen a moment longer.
        if (state == AuthUiState.SignedIn || state == AuthUiState.CodeFlowStart) password = ""
    }

    val typed = { Identifier(kind, identifier) }
    val identifierForm =
        IdentifierForm(
            kind = kind,
            value = identifier,
            rejected = identifierRejected,
            onKindChange = {
                kind = it
                identifier = ""
                identifierRejected = false
            },
            onValueChange = {
                identifier = it
                identifierRejected = false
            },
        )

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

            // The authenticator step [0028], after a password sign-in for
            // an account that has two-step verification on. Back goes to
            // the sign-in form: the challenge is spent.
            state is AuthUiState.SecondStep ->
                SecondStep(
                    state = state,
                    onSubmit = actions.onSubmitSecondStep,
                    onToggleRecovery = actions.onToggleRecoveryCode,
                    onBack = actions.onBackToSignIn,
                )

            state is AuthUiState.ChoosePassword ->
                ChoosePasswordStep(
                    state = state,
                    onSubmit = actions.onChoosePassword,
                    onToggleRecovery = actions.onToggleSetupRecovery,
                    onBack = {
                        code = ""
                        actions.onChangeNumber()
                    },
                )

            onCodeStep ->
                CodeStep(
                    code = code,
                    state = state,
                    codeSentCount = codeSentCount,
                    destination = codeDestination,
                    onCodeChange = { code = it },
                    onSubmit = { actions.onSubmitCode(code) },
                    onResend = {
                        code = ""
                        actions.onResendCode()
                    },
                    onChangeNumber = {
                        code = ""
                        actions.onChangeNumber()
                    },
                    onGoToSignup = actions.onGoToSignup,
                )

            onCodeRequest ->
                CodeRequestStep(
                    form = identifierForm,
                    state = state,
                    onSubmit = {
                        // A fresh code starts with empty boxes.
                        code = ""
                        if (identifierIsWellFormed(typed())) {
                            actions.onRequestCode(typed())
                        } else {
                            identifierRejected = true
                        }
                    },
                    onRetry = actions.onRetry,
                    onBack = actions.onBackToSignIn,
                )

            else ->
                SignInStep(
                    form = identifierForm,
                    password = password,
                    onPasswordChange = { password = it },
                    state = state,
                    onSubmit = {
                        if (identifierIsWellFormed(typed())) {
                            actions.onSignIn(typed(), password)
                        } else {
                            identifierRejected = true
                        }
                    },
                    actions = actions,
                )
        }

        // **Over the step, centred on the window.** The loader is the
        // app-wide overlay, by the person's own rule, and the step stays
        // visible beneath its scrim.
        WaitingOverlay(state)
    }
}

/**
 * Whether the code step is on screen.
 *
 * @param state What to render
 * @param wasCodeStep Whether it was on screen before this state: a
 *   resend from the code step sends, and must not flash another step
 * @return True for the code step
 */
private fun isCodeStep(state: AuthUiState, wasCodeStep: Boolean): Boolean =
    when (state) {
        AuthUiState.AwaitingCode,
        AuthUiState.CheckingCode,
        is AuthUiState.CodeRejected,
        -> true
        AuthUiState.Sending -> wasCodeStep
        else -> false
    }

/**
 * Whether the code flow's first step is on screen.
 *
 * @param state What to render
 * @param onCodeStep Whether the code step is
 * @return True for the identifier step of the code flow
 */
private fun isCodeRequestStep(state: AuthUiState, onCodeStep: Boolean): Boolean =
    when (state) {
        AuthUiState.CodeFlowStart -> true
        AuthUiState.Sending -> !onCodeStep
        is AuthUiState.Failed -> state.step == AuthStep.CODE_REQUEST
        else -> false
    }

/**
 * The app-wide loader over the step while something is with the server.
 *
 * @param state What to render
 */
@Composable
private fun WaitingOverlay(state: AuthUiState) {
    val (tag, label) =
        when (state) {
            AuthUiState.SigningIn -> TAG_SIGNING_IN to R.string.auth_signing_in
            AuthUiState.Sending -> TAG_SENDING to R.string.auth_sending
            AuthUiState.CheckingCode -> TAG_CHECKING_CODE to R.string.auth_checking_code
            else -> return
        }
    LogoLoader(modifier = Modifier.testTag(tag), size = 72.dp, label = stringResource(label))
}

/**
 * The identifier half of a form: its kind, what is typed, and whether a
 * submit refused its shape.
 *
 * @property kind Phone or email
 * @property value What is typed
 * @property rejected Whether a submit found it malformed
 * @property onKindChange Called when the toggle changes
 * @property onValueChange Called on each edit
 */
private data class IdentifierForm(
    val kind: IdentifierKind,
    val value: String,
    val rejected: Boolean,
    val onKindChange: (IdentifierKind) -> Unit,
    val onValueChange: (String) -> Unit,
)

/**
 * The toggle and the field, with the shape refusal under the field.
 *
 * @param form The identifier half of the form
 * @param state What to render, for a refusal the server named
 * @param help The help line while the field is empty
 * @param enabled Whether it can be changed
 */
@Composable
private fun IdentifierInput(
    form: IdentifierForm,
    state: AuthUiState,
    help: String?,
    enabled: Boolean,
) {
    // A refused NUMBER or EMAIL belongs under the field, whoever refused it.
    val refusedKey = (state as? AuthUiState.Failed)?.messageKey
    val error =
        when {
            form.kind == IdentifierKind.PHONE && (form.rejected || refusedKey in PHONE_MESSAGE_KEYS) ->
                stringResource(R.string.phone_invalid)
            form.kind == IdentifierKind.EMAIL && (form.rejected || refusedKey in EMAIL_MESSAGE_KEYS) ->
                stringResource(R.string.signup_email_invalid)
            else -> null
        }
    IdentifierKindToggle(kind = form.kind, onKindChange = form.onKindChange, enabled = enabled)
    IdentifierField(
        kind = form.kind,
        value = form.value,
        onValueChange = form.onValueChange,
        help = help.takeIf { form.value.isEmpty() },
        error = error,
        large = true,
        fieldModifier = Modifier.testTag(TAG_IDENTIFIER_FIELD),
    )
}

/**
 * The password sign-in: the brand band, Phone | Email, the identifier,
 * the password, and a bar pinned to the foot.
 *
 * **One scrolling column at least the window's height.** The bar sits
 * at the foot of a tall phone, as the board draws it, and on a short
 * one the whole step scrolls rather than squeezing the fields out of
 * sight -- the regression this screen already caught once, at 320x414.
 *
 * @param form The identifier half of the form
 * @param password The password typed so far
 * @param onPasswordChange Called on each edit of it
 * @param state What to render
 * @param onSubmit Called from "Sign in"
 * @param actions The screen's callbacks, for the links and the retry
 */
@Composable
private fun SignInStep(
    form: IdentifierForm,
    password: String,
    onPasswordChange: (String) -> Unit,
    state: AuthUiState,
    onSubmit: () -> Unit,
    actions: AuthActions,
) {
    val busy = state == AuthUiState.SigningIn
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val roomForTallHero = maxHeight >= TALL_HERO_MIN_HEIGHT
        val minHeight: Dp = maxHeight

        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Column(
                modifier = Modifier.fillMaxWidth().heightIn(min = minHeight),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    // Tall on the empty first screen; compact once anything
                    // is typed, so the fields clear the keyboard.
                    BrandHero(
                        compact = form.value.isNotEmpty() || state !is AuthUiState.Idle || !roomForTallHero,
                        tagline = stringResource(R.string.auth_tagline),
                    )
                    Column(
                        modifier =
                            Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 12.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text(
                            text = stringResource(R.string.auth_signin_headline),
                            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                        )
                        IdentifierInput(form = form, state = state, help = null, enabled = !busy)
                        PasswordField(
                            value = password,
                            onValueChange = onPasswordChange,
                            label = stringResource(R.string.password_label),
                            enabled = !busy,
                            onImeAction = onSubmit,
                            fieldModifier = Modifier.testTag(TAG_PASSWORD_FIELD),
                        )
                        TextAction(
                            text = stringResource(R.string.auth_forgot_password),
                            onClick = actions.onStartCodeFlow,
                            enabled = !busy,
                            modifier = Modifier.testTag(TAG_FORGOT_PASSWORD),
                        )
                        SignInFailure(state = state, actions = actions)
                    }
                }
                SignInBar(
                    enabled = form.value.isNotBlank() && password.isNotEmpty() && !busy,
                    onSubmit = onSubmit,
                    actions = actions,
                )
            }
        }
    }
}

/**
 * A refused or failed sign-in: the server's sentence, the way to the
 * code flow when the mapper offers it, and a retry when the server
 * allows one.
 *
 * @param state What to render
 * @param actions The screen's callbacks
 */
@Composable
private fun SignInFailure(state: AuthUiState, actions: AuthActions) {
    if (state !is AuthUiState.Failed || state.messageKey in IDENTIFIER_MESSAGE_KEYS) return
    Banner(
        title = stringResource(MessageKeys.resolve(state.messageKey)),
        body = stringResource(R.string.auth_password_wrong_hint).takeIf { state.offerCodeFlow },
        tone = BannerTone.ERROR,
        action =
            if (state.offerCodeFlow) {
                {
                    TextAction(
                        text = stringResource(R.string.auth_get_code),
                        onClick = actions.onStartCodeFlow,
                        modifier = Modifier.testTag(TAG_HINT_GET_CODE),
                    )
                }
            } else {
                null
            },
        modifier = Modifier.testTag(TAG_ERROR),
    )
    if (state.retryable) {
        SecondaryButton(
            text = stringResource(R.string.auth_retry),
            onClick = actions.onRetry,
            modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
        )
    }
}

/**
 * The bar pinned to the sign-in step's foot.
 *
 * @param enabled Whether "Sign in" can be pressed
 * @param onSubmit Called from "Sign in"
 * @param actions The screen's callbacks, for the two links
 */
@Composable
private fun SignInBar(
    enabled: Boolean,
    onSubmit: () -> Unit,
    actions: AuthActions,
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PrimaryButton(
            text = stringResource(R.string.auth_sign_in),
            onClick = onSubmit,
            // Disabled until there is something to send, rather than
            // letting the server refuse an empty form.
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().testTag(TAG_SIGN_IN),
        )
        // **The way in for an account from before passwords.** It has no
        // password yet, so the form above can only refuse it; this says
        // so before the person tries, as well as after.
        PromptLink(
            prompt = stringResource(R.string.auth_first_password_prompt),
            link = stringResource(R.string.auth_get_code),
            onClick = actions.onStartCodeFlow,
            linkModifier = Modifier.testTag(TAG_FIRST_PASSWORD),
        )
        PromptLink(
            prompt = stringResource(R.string.auth_new_here),
            link = stringResource(R.string.auth_go_to_signup),
            onClick = actions.onGoToSignup,
            linkModifier = Modifier.testTag(TAG_GO_TO_SIGNUP),
        )
    }
}

/**
 * The code flow's first step: which phone or email the code goes to.
 *
 * @param form The identifier half of the form
 * @param state What to render
 * @param onSubmit Called from "Send code"
 * @param onRetry Called from a retryable failure's retry
 * @param onBack Called from the back arrow: back to the sign-in form
 */
@Composable
private fun CodeRequestStep(
    form: IdentifierForm,
    state: AuthUiState,
    onSubmit: () -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    val sending = state == AuthUiState.Sending
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        BackRow(onBack = onBack, tag = TAG_CODE_REQUEST_BACK)
        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.auth_code_flow_title),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.testTag(TAG_CODE_REQUEST),
            )
            Text(
                text = stringResource(R.string.auth_code_flow_body),
                style = MaterialTheme.typography.bodyMedium,
            )
            IdentifierInput(
                form = form,
                state = state,
                help =
                    stringResource(
                        if (form.kind == IdentifierKind.PHONE) R.string.auth_subhead else R.string.auth_subhead_email,
                    ),
                enabled = !sending,
            )
            val failed = state as? AuthUiState.Failed
            if (failed != null && failed.messageKey !in IDENTIFIER_MESSAGE_KEYS) {
                Banner(
                    title = stringResource(MessageKeys.resolve(failed.messageKey)),
                    tone = BannerTone.ERROR,
                    modifier = Modifier.testTag(TAG_ERROR),
                )
                if (failed.retryable) {
                    SecondaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = onRetry,
                        modifier = Modifier.fillMaxWidth().testTag(TAG_RETRY),
                    )
                }
            }
            PrimaryButton(
                text = stringResource(R.string.auth_request_code),
                onClick = onSubmit,
                enabled = form.value.isNotBlank() && !sending,
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
            }
        }
    }
}

/**
 * A row holding only the back arrow, as `O3` draws it.
 *
 * @param onBack Called from the arrow
 * @param tag The arrow's test tag
 */
@Composable
internal fun BackRow(onBack: () -> Unit, tag: String) {
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack, modifier = Modifier.testTag(tag)) {
            BackArrow(contentDescription = stringResource(R.string.action_back))
        }
    }
}

/**
 * The shortest screen that can hold the tall branding band and still
 * show the fields and their action without scrolling.
 *
 * Below this the compact band is used instead. 560dp is comfortably
 * under any current phone in portrait and above the 414dp the tests
 * render at, which is what makes the short case covered rather than
 * assumed.
 */
private val TALL_HERO_MIN_HEIGHT = 560.dp

/** Message keys naming a malformed number, from either route. */
internal val PHONE_MESSAGE_KEYS: Set<String> =
    setOf("phone.invalid", "signup.phone.invalid")

/** Message keys naming a malformed email, from the server or the form. */
internal val EMAIL_MESSAGE_KEYS: Set<String> =
    setOf("email.invalid", "signup.email.invalid")

/** Refusals shown under the identifier field rather than as a banner. */
internal val IDENTIFIER_MESSAGE_KEYS: Set<String> = PHONE_MESSAGE_KEYS + EMAIL_MESSAGE_KEYS

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
 * @param destination Whether the code went by SMS or by email
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
    destination: IdentifierKind,
    onCodeChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onResend: () -> Unit,
    onChangeNumber: () -> Unit,
    onGoToSignup: () -> Unit,
) {
    val byEmail = destination == IdentifierKind.EMAIL
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        BackRow(onBack = onChangeNumber, tag = TAG_CODE_BACK)

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
                    text = stringResource(if (byEmail) R.string.auth_code_sent_email else R.string.auth_code_sent),
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
                    Hint(stringResource(codeHint(typing = code.isNotEmpty(), byEmail = byEmail)))
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
                        style = BodyCompact,
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
 * The guidance under empty or half-typed code boxes.
 *
 * @param typing Whether a digit is in
 * @param byEmail Whether the code went by email, where no SMS autofill helps
 * @return Its string resource
 */
private fun codeHint(typing: Boolean, byEmail: Boolean): Int =
    when {
        typing -> R.string.auth_code_auto_checks
        byEmail -> R.string.auth_code_email_hint
        else -> R.string.auth_code_autofill_hint
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

/** The phone or email field, on the sign-in form and the code flow's first step. */
const val TAG_IDENTIFIER_FIELD = "auth_identifier_field"

/** Kept as the identifier field's old name, for the device run's scripts. */
const val TAG_PHONE_FIELD = TAG_IDENTIFIER_FIELD

/** The password on the sign-in form. */
const val TAG_PASSWORD_FIELD = "auth_password_field"

/** "Sign in", on the sign-in form. */
const val TAG_SIGN_IN = "auth_sign_in"

/** The loader over the sign-in form. */
const val TAG_SIGNING_IN = "auth_signing_in"

/** "Forgot password?", which opens the code flow. */
const val TAG_FORGOT_PASSWORD = "auth_forgot_password"

/** "First time with a password? Get a code", which opens the code flow. */
const val TAG_FIRST_PASSWORD = "auth_first_password"

/** "Get a code" beside a refused password. */
const val TAG_HINT_GET_CODE = "auth_hint_get_code"

/** The code flow's first step's heading. */
const val TAG_CODE_REQUEST = "auth_code_request"

/** The code flow's first step's back arrow, to the sign-in form. */
const val TAG_CODE_REQUEST_BACK = "auth_code_request_back"
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
