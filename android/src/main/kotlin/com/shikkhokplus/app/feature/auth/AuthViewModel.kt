package com.shikkhokplus.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
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
     * @return The token pair, or an error envelope, or a transport failure
     */
    suspend fun verify(phone: String, code: String): AuthResult<TokenResponse>
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
    /** The server answered successfully. */
    data class Ok<T>(val value: T) : AuthResult<T>

    /** The server refused, with an envelope saying why. */
    data class Refused(val envelope: ErrorEnvelope) : AuthResult<Nothing>

    /** No response arrived at all. */
    data object TransportFailure : AuthResult<Nothing>
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

    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    private var lastPhone: String = ""
    private var lastAction: (() -> Unit)? = null

    /**
     * Try a stored session before showing the OTP screen.
     *
     * **"Remember the device" is this call**, not the storage. A
     * persisted token nothing redeems would leave the app holding a
     * credential and still asking for a code.
     *
     * A failure here is deliberately SILENT: the teacher sees the
     * normal sign-in screen, which is where they were going anyway. An
     * error about a refresh they never asked for would be noise about
     * machinery they do not know exists.
     *
     * @param refresh Exchanges the stored token for a fresh pair
     */
    fun resumeSession(refresh: suspend () -> AuthResult<TokenResponse>) {
        viewModelScope.launch {
            if (refresh() is AuthResult.Ok) {
                _state.value = AuthUiState.SignedIn
            }
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
        _state.value = AuthUiState.Sending
        viewModelScope.launch {
            _state.value = when (val result = repository.verify(lastPhone, code)) {
                is AuthResult.Ok -> AuthStateMapper.afterVerify(result.value)
                is AuthResult.Refused -> AuthStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure -> AuthStateMapper.afterTransportFailure()
            }
        }
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
}
