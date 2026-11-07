package com.shikkhokplus.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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
     * Ask the server to send a code.
     *
     * @param phone The number the user typed
     * @return The server's reply, or an error envelope, or a transport failure
     */
    suspend fun issue(phone: String): AuthResult<IssueResponse>

    /**
     * Present a code for verification.
     *
     * @param phone The number the code was issued for
     * @param code The code the user entered
     * @return The token pair or the authenticator challenge, or an error
     *   envelope, or a transport failure
     */
    suspend fun verify(phone: String, code: String): AuthResult<VerifyResponse>

    /**
     * Finish signing in with the second step [0028]: exactly one of the
     * authenticator code and a recovery code.
     *
     * @param challenge What [verify] returned for this sign-in
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
 * Holds the OTP screen's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [AuthStateMapper], which is the unit
 * the tests target. This class owns the coroutine and the state holder
 * and nothing else — so there is no branch here that a test would need
 * a dispatcher to reach.
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

    private var lastPhone: String = ""
    private var lastAction: (() -> Unit)? = null

    // The authenticator challenge for the sign-in under way, in memory
    // only: it is useless after five minutes and grants nothing alone.
    private var challenge: String? = null

    /**
     * Try a stored session before showing the OTP screen.
     *
     * **"Remember the device" is this call**, not the storage. A
     * persisted token nothing redeems would leave the app holding a
     * credential and still asking for a code.
     *
     * A session that ENDED is deliberately SILENT: the person sees the
     * normal sign-in screen, which is where they were going anyway. An
     * error about a refresh they never asked for would be noise about
     * machinery they do not know exists. A session that could not be
     * verified stays signed in ([SessionResume.UNVERIFIED]).
     *
     * **It must always resolve.** The state starts at
     * [AuthUiState.Restoring], so a path that left it unchanged would
     * hold the loader forever — the opposite of the flash it fixes.
     *
     * @param resume Redeems the stored session and says what came of it
     */
    fun resumeSession(resume: suspend () -> SessionResume) {
        viewModelScope.launch {
            _state.value = AuthStateMapper.afterResume(resume())
        }
    }

    /**
     * Request a code for a number the user typed.
     *
     * @param phone The number, never read from the SIM [AC1.1.6]
     */
    fun requestCode(phone: String) {
        lastPhone = phone
        lastAction = { requestCode(phone) }
        _state.value = AuthUiState.Sending
        viewModelScope.launch {
            _state.value = when (val result = repository.issue(phone)) {
                is AuthResult.Ok -> AuthStateMapper.afterIssue(result.value)
                is AuthResult.Refused -> AuthStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure -> AuthStateMapper.afterTransportFailure()
            }
        }
    }

    /**
     * Adopt a code another screen already caused to be sent.
     *
     * **Signup issues an OTP without authenticating**, so a person who
     * has just registered arrives here with a code already in flight.
     * Without this the screen would sit at [AuthUiState.Idle] showing
     * the number field — asking them to request a second code, which
     * invalidates the one they are holding and spends another SMS.
     *
     * The number is carried rather than re-typed because [submitCode]
     * verifies against [lastPhone], and that is empty on a ViewModel
     * that has not issued anything itself.
     *
     * @param phone The number the code was sent to
     */
    fun adoptPendingCode(phone: String) {
        lastPhone = phone
        _state.value = AuthUiState.AwaitingCode
    }

    /**
     * Submit the code the user entered.
     *
     * @param code The code read from the SMS or typed
     */
    fun submitCode(code: String) {
        lastAction = { submitCode(code) }
        _state.value = AuthUiState.CheckingCode
        viewModelScope.launch {
            _state.value = when (val result = repository.verify(lastPhone, code)) {
                is AuthResult.Ok -> {
                    challenge = result.value.mfaChallenge
                    AuthStateMapper.afterVerify(result.value)
                }
                is AuthResult.Refused ->
                    AuthStateMapper.codeRejected(
                        AuthStateMapper.afterError(result.envelope),
                        result.envelope.error.details?.get(ATTEMPTS_LEFT),
                    )
                AuthResult.TransportFailure ->
                    AuthStateMapper.codeRejected(AuthStateMapper.afterTransportFailure())
            }
        }
    }

    /**
     * Submit the second step: the authenticator code, or a recovery code
     * when the person switched to one.
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
     * Ask for a new code to the same number, at the person's request.
     *
     * Never automatic: each one is an SMS the server pays for, and the
     * server's own ceilings decide whether it is sent.
     */
    fun resendCode() {
        if (lastPhone.isNotEmpty()) requestCode(lastPhone)
    }

    /**
     * Go back to the number field, to correct a mistyped number, or
     * from the second step to start the sign-in again.
     */
    fun changeNumber() {
        lastAction = null
        challenge = null
        _state.value = AuthUiState.Idle
    }

    /**
     * Re-run the last action, at the user's explicit request.
     *
     * Only reachable from a [AuthUiState.Failed] the server marked
     * retryable. There is no automatic retry anywhere: on the OTP path
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
        lastAction = null
        challenge = null
        _state.value = AuthUiState.Idle
    }
}

/** The detail a wrong sign-in code carries: how many tries are left. */
private const val ATTEMPTS_LEFT = "attempts_left"
