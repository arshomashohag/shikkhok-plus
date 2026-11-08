package com.shikkhokplus.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the auth repository must provide.
 *
 * An interface rather than a concrete Retrofit service, so the ViewModel
 * is testable without a server and the state machine can be driven
 * through every branch including the transport failure.
 */
interface AuthRepository {
    /**
     * Ask the server to send a code, by SMS or by email.
     *
     * @param identifier The phone or email the user typed
     * @return The server's reply, or an error envelope, or a transport failure
     */
    suspend fun issue(identifier: Identifier): AuthResult<IssueResponse>

    /**
     * Present a code for verification.
     *
     * @param identifier The phone or email the code was issued for
     * @param code The code the user entered
     * @return The password-setup token, or an error envelope, or a
     *   transport failure
     */
    suspend fun verify(identifier: Identifier, code: String): AuthResult<VerifyResponse>

    /**
     * Sign in with an identifier and a password.
     *
     * @param identifier The phone or email the user typed
     * @param password What the user typed; never stored or logged
     * @return The token pair or the authenticator challenge, or an error
     *   envelope, or a transport failure
     */
    suspend fun signIn(identifier: Identifier, password: String): AuthResult<VerifyResponse>

    /**
     * Finish the code flow by choosing a password.
     *
     * @param token The setup token [verify] returned
     * @param password The chosen password
     * @param code The authenticator code when the account has one on, or null
     * @param recoveryCode A recovery code instead, or null
     * @return The token pair, or an error envelope, or a transport failure
     */
    suspend fun setupPassword(
        token: String,
        password: String,
        code: String?,
        recoveryCode: String?,
    ): AuthResult<TokenResponse>

    /**
     * Finish signing in with the second step [0028]: exactly one of the
     * authenticator code and a recovery code.
     *
     * @param challenge What [signIn] returned for this sign-in
     * @param code Six digits from the authenticator app, or null
     * @param recoveryCode A recovery code, or null
     * @return The token pair, or an error envelope, or a transport failure
     */
    suspend fun verifySecondStep(
        challenge: String,
        code: String?,
        recoveryCode: String?,
    ): AuthResult<TokenResponse>
}

/**
 * What one call to the server produced.
 *
 * Three cases, not two, because a transport failure and a server
 * refusal need different handling: the server tells us whether a retry
 * is appropriate, and when no response arrived there is nothing to read
 * it from [TC-9].
 */
sealed interface AuthResult<out T> {
    /**
     * The server answered successfully.
     *
     * @property value The answer
     * @property savedAt Set when no answer arrived and this is the copy
     *   the phone kept from an earlier one: when that was read. A screen
     *   shows such a value as offline. Null for a live answer.
     */
    data class Ok<T>(val value: T, val savedAt: Long? = null) : AuthResult<T>

    /** The server refused, with an envelope saying why. */
    data class Refused(val envelope: ErrorEnvelope) : AuthResult<Nothing>

    /** No response arrived at all. */
    data object TransportFailure : AuthResult<Nothing>
}

/**
 * What redeeming the stored session at a cold start came to.
 *
 * **Three outcomes, because "the refresh did not succeed" is two
 * different facts.** The server refusing the credential means it is
 * dead and the person must sign in again. No answer arriving -- the
 * phone is offline, or the server is down -- means nothing at all about
 * the credential, and treating it as a refusal sent a signed-in teacher
 * to the sign-in screen on every offline cold start: the offline
 * attendance queue was unreachable exactly when it was needed, and an
 * OTP (an SMS, a cost) was the only way back in.
 */
enum class SessionResume {
    /** The server issued a fresh pair; the session is verified. */
    RENEWED,

    /**
     * The stored session is kept but not yet verified: no answer
     * arrived, or the server failed to answer (a 5xx or a 429).
     *
     * **Signed in, not a separate screen state.** Nothing renders
     * differently: every screen already answers an unreachable server
     * with its own retry, the offline queue keeps working, and the first
     * request that does reach the server and finds the access token
     * expired is renewed by `SessionRenewal` -- under the same lock --
     * which is the lazy verification this state defers to. A refusal
     * there ends the session the ordinary way.
     */
    UNVERIFIED,

    /** No stored session, or the server refused it: sign in again. */
    ENDED,
}

/**
 * Holds the sign-in screen's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [AuthStateMapper], which is the unit
 * the tests target. This class owns the coroutine, the state holder and
 * the in-memory secrets of one flow, and nothing else.
 *
 * **Three ways in, one way to a session.** A password sign-in returns a
 * pair (or the authenticator step). The code flow -- a forgotten
 * password, or a first password for an account from before passwords --
 * verifies a code, receives a setup token, and ends with a chosen
 * password. Sign-up is the code flow with the password already chosen on
 * the sign-up form, so it is sent the moment the code is verified.
 *
 * **What is secret is held in memory only, and dropped as soon as it is
 * spent**: the password between sign-up and setup, the setup token, the
 * authenticator challenge, and a sign-in's retry closure. None of them
 * is written to saved state, a Bundle or storage, and each is cleared on
 * success, on leaving the step, and when this ViewModel is cleared.
 *
 * **V1 accepts no write without connectivity** [TC-8, D-9]: there is no
 * local queue and no silent retry. A failure surfaces a state the screen
 * renders with an explicit retry affordance, and [retry] runs only when
 * the user asks.
 */
class AuthViewModel(
    private val repository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Restoring)

    /** What the screen renders. */
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    private val _codeDestination = MutableStateFlow(IdentifierKind.PHONE)

    /**
     * Whether the outstanding code went by SMS or by email, so the code
     * step can say where to look. Never the address itself: the server
     * answers every identifier alike [BR2.7].
     */
    val codeDestination: StateFlow<IdentifierKind> = _codeDestination.asStateFlow()

    private var lastIdentifier: Identifier? = null
    private var lastAction: (() -> Unit)? = null

    // The authenticator challenge for the sign-in under way, in memory
    // only: it is useless after five minutes and grants nothing alone.
    private var challenge: String? = null

    // The setup token a verified code returned, in memory only: it
    // lapses after ten minutes and is spent by one setup.
    private var setupToken: String? = null

    // The password chosen on the sign-up form, held only between the
    // code being sent and being verified, then sent and dropped.
    private var pendingPassword: String? = null

    /**
     * Try a stored session before showing the sign-in screen.
     *
     * **"Remember the device" is this call**, not the storage. A
     * persisted token nothing redeems would leave the app holding a
     * credential and still asking for a password.
     *
     * A session that ENDED is deliberately SILENT: the person sees the
     * normal sign-in screen, which is where they were going anyway. A
     * session that could not be verified stays signed in
     * ([SessionResume.UNVERIFIED]).
     *
     * **It must always resolve.** The state starts at
     * [AuthUiState.Restoring], so a path that left it unchanged would
     * hold the loader forever.
     *
     * @param resume Redeems the stored session and says what came of it
     */
    fun resumeSession(resume: suspend () -> SessionResume) {
        viewModelScope.launch {
            _state.value = AuthStateMapper.afterResume(resume())
        }
    }

    /**
     * Sign in with an identifier and a password.
     *
     * The shape of the identifier is the screen's to check before this
     * is called; whether the password is right is the server's.
     *
     * @param identifier The phone or email typed, never read from the SIM
     * @param password What was typed; held only in the retry closure,
     *   which is dropped once the sign-in resolves or is left
     */
    fun signIn(identifier: Identifier, password: String) {
        lastIdentifier = identifier
        lastAction = { signIn(identifier, password) }
        _state.value = AuthUiState.SigningIn
        viewModelScope.launch {
            val result = repository.signIn(identifier, password)
            if (result is AuthResult.Ok) challenge = result.value.mfaChallenge
            _state.value = AuthStateMapper.afterSignIn(result)
            // Only a lost connection keeps the closure, for its retry.
            if (result !is AuthResult.TransportFailure) lastAction = null
        }
    }

    /**
     * Open the code flow: "Forgot password?" or "First time with a
     * password? Get a code".
     */
    fun startCodeFlow() {
        forgetSecrets()
        _state.value = AuthUiState.CodeFlowStart
    }

    /** Return to the password sign-in, from anywhere in the code flow. */
    fun backToSignIn() {
        forgetSecrets()
        _state.value = AuthUiState.Idle
    }

    /**
     * Request a code for an identifier the user typed.
     *
     * @param identifier The phone or email, never read from the SIM [AC1.1.6]
     */
    fun requestCode(identifier: Identifier) {
        lastIdentifier = identifier
        _codeDestination.value = identifier.kind
        lastAction = { requestCode(identifier) }
        _state.value = AuthUiState.Sending
        viewModelScope.launch {
            _state.value =
                when (val result = repository.issue(identifier)) {
                    is AuthResult.Ok -> AuthStateMapper.afterIssue(result.value)
                    is AuthResult.Refused -> AuthStateMapper.afterError(result.envelope, AuthStep.CODE_REQUEST)
                    AuthResult.TransportFailure -> AuthStateMapper.afterTransportFailure(AuthStep.CODE_REQUEST)
                }
        }
    }

    /**
     * Adopt a code sign-up already caused to be sent, with the password
     * chosen on the sign-up form.
     *
     * **Sign-up issues a code without authenticating**, so a person who
     * has just registered arrives here with a code already in flight.
     * Without this the screen would show the sign-in form and the person
     * would have no field for the code they are holding.
     *
     * The password is held here, in memory, until the code is verified,
     * then sent to set it and dropped. The sign-up ViewModel does not keep
     * its own copy.
     *
     * @param identifier The phone or email the code was sent to
     * @param password The password chosen on the sign-up form, or null
     *   to ask for one after the code
     */
    fun adoptPendingCode(identifier: Identifier, password: String? = null) {
        forgetSecrets()
        lastIdentifier = identifier
        pendingPassword = password
        _codeDestination.value = identifier.kind
        _state.value = AuthUiState.AwaitingCode
    }

    /**
     * Submit the code the user entered.
     *
     * A verified code yields a setup token. With a password already
     * chosen at sign-up it is sent straight away and the code boxes stay
     * up while it is; otherwise the screen asks for one.
     *
     * @param code The code read from the SMS or email, or typed
     */
    fun submitCode(code: String) {
        val identifier = lastIdentifier ?: return
        lastAction = { submitCode(code) }
        _state.value = AuthUiState.CheckingCode
        viewModelScope.launch {
            when (val result = repository.verify(identifier, code)) {
                is AuthResult.Ok -> {
                    lastAction = null
                    setupToken = result.value.passwordSetupToken
                    val next = PasswordStateMapper.afterCodeVerified(result.value)
                    val chosen = pendingPassword
                    if (next is AuthUiState.ChoosePassword && chosen != null && !next.mfaRequired) {
                        sendPassword(next, chosen, secondCode = null)
                    } else {
                        pendingPassword = null
                        _state.value = next
                    }
                }
                is AuthResult.Refused ->
                    _state.value =
                        AuthStateMapper.codeRejected(
                            AuthStateMapper.afterError(result.envelope),
                            result.envelope.error.details?.get(ATTEMPTS_LEFT),
                        )
                AuthResult.TransportFailure ->
                    _state.value = AuthStateMapper.codeRejected(AuthStateMapper.afterTransportFailure())
            }
        }
    }

    /**
     * Choose the password that finishes the code flow.
     *
     * Length and match are checked here first, through the mapper, so a
     * short password never reaches the network; everything else is the
     * server's to refuse.
     *
     * **Also the explicit retry** after a failure: the screen keeps what
     * was typed and calls this again. Nothing retries by itself.
     *
     * @param password The chosen password
     * @param confirm Its second copy
     * @param secondCode The authenticator or recovery code, when the form
     *   asks for one; ignored otherwise
     */
    fun choosePassword(password: String, confirm: String, secondCode: String = "") {
        val form = _state.value as? AuthUiState.ChoosePassword ?: return
        if (form.checking) return
        val refused = PasswordStateMapper.checkChosen(form, password, confirm)
        if (refused != null) {
            _state.value = refused
            return
        }
        _state.value = form.copy(checking = true, messageKey = null, retryable = false)
        viewModelScope.launch { sendPassword(form, password, secondCode.takeIf { form.mfaRequired }) }
    }

    /**
     * Send the setup and publish what it came to.
     *
     * @param form The form being answered
     * @param password The password to set
     * @param secondCode The authenticator or recovery code, or null
     */
    private suspend fun sendPassword(
        form: AuthUiState.ChoosePassword,
        password: String,
        secondCode: String?,
    ) {
        // Always set: the form is reached only from a verified code that
        // carried a token, and leaving the form forgets both together.
        val token = setupToken ?: return
        _state.value = form.copy(checking = true, messageKey = null, retryable = false)
        val result =
            repository.setupPassword(
                token = token,
                password = password,
                code = secondCode.takeUnless { form.useRecovery },
                recoveryCode = secondCode.takeIf { form.useRecovery },
            )
        // Spent, refused or sent: either way it is not sent again by
        // itself. A refusal asks the person to choose again.
        pendingPassword = null
        _state.value = PasswordStateMapper.afterPasswordSetup(result, form)
        if (_state.value !is AuthUiState.ChoosePassword) setupToken = null
    }

    /**
     * Switch the choose-password form between the authenticator code and
     * a recovery code, clearing any refusal shown for the other.
     */
    fun toggleSetupRecoveryCode() {
        val form = _state.value as? AuthUiState.ChoosePassword ?: return
        if (form.checking || !form.mfaRequired) return
        _state.value = form.copy(useRecovery = !form.useRecovery, messageKey = null, retryable = false)
    }

    /**
     * Submit the second step of a password sign-in: the authenticator
     * code, or a recovery code when the person switched to one.
     *
     * **Also the explicit retry** after a failure: the screen keeps what
     * was typed and calls this again. Nothing retries by itself.
     *
     * @param code What the person typed, trimmed by the screen
     */
    fun submitSecondStep(code: String) {
        val recovery = (_state.value as? AuthUiState.SecondStep)?.useRecovery ?: return
        val pending = challenge ?: return
        lastAction = null
        _state.value = AuthUiState.SecondStep(useRecovery = recovery, checking = true)
        viewModelScope.launch {
            val result =
                repository.verifySecondStep(
                    challenge = pending,
                    code = code.takeUnless { recovery },
                    recoveryCode = code.takeIf { recovery },
                )
            _state.value = AuthStateMapper.afterSecondStep(result, recovery)
            if (_state.value !is AuthUiState.SecondStep) challenge = null
        }
    }

    /**
     * Switch the second step between the authenticator code and a
     * recovery code, clearing any refusal shown for the other.
     */
    fun toggleRecoveryCode() {
        val current = _state.value as? AuthUiState.SecondStep ?: return
        if (current.checking) return
        _state.value = AuthUiState.SecondStep(useRecovery = !current.useRecovery)
    }

    /**
     * Ask for a new code to the same phone or email, at the person's
     * request.
     *
     * Never automatic: each SMS is one the server pays for, and the
     * server's own ceilings decide whether it is sent. A password held
     * from sign-up is kept: the new code finishes the same sign-up.
     */
    fun resendCode() {
        lastIdentifier?.let(::requestCode)
    }

    /**
     * Go back from the code step or the choose-password step to the code
     * flow's first step, to correct a mistyped phone or email.
     */
    fun changeNumber() {
        forgetSecrets()
        _state.value = AuthUiState.CodeFlowStart
    }

    /**
     * Re-run the last action, at the user's explicit request.
     *
     * Only reachable from a [AuthUiState.Failed] the server marked
     * retryable. There is no automatic retry anywhere: on the code path
     * an automatic retry would spend money and send a second SMS.
     */
    fun retry() {
        val failed = _state.value as? AuthUiState.Failed ?: return
        if (!failed.retryable) return
        lastAction?.invoke()
    }

    /**
     * Return to the signed-out state.
     *
     * **State only.** Clearing the stored tokens and the device's queue
     * is the caller's, because this ViewModel does not own them; the
     * app's one `endSession` action does all three together so none
     * can be forgotten.
     */
    fun signOut() {
        forgetSecrets()
        _state.value = AuthUiState.Idle
    }

    override fun onCleared() {
        forgetSecrets()
        super.onCleared()
    }

    /** Drop everything secret this flow held: retry closure, challenge, token, password. */
    private fun forgetSecrets() {
        lastAction = null
        challenge = null
        setupToken = null
        pendingPassword = null
    }
}

/** The detail a wrong sign-in code carries: how many tries are left. */
private const val ATTEMPTS_LEFT = "attempts_left"
