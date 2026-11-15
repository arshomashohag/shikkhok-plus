package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the replace-contact screen renders (functional-spec 3.6): the new
 * value and the password, then the code sent to the new value.
 *
 * **No state here holds the new value or the password** [NFR3.2,
 * NFR3.4]: the value lives in the screen's saved state (it is the
 * person's own, not a secret) and the password in its `remember`, and
 * both reach the repository only through [ReplaceContactViewModel].
 */
sealed interface ReplaceContactUiState {
    /** Which kind is being replaced: fixed for the screen's life. */
    val kind: IdentifierKind

    /**
     * The new value and the current password.
     *
     * @property kind Phone or email
     * @property sending The request is with the server
     * @property valueKey A refusal shown under the new value, or null
     * @property passwordKey A refusal shown under the password, or null
     * @property bannerKey A refusal shown as a banner, or null
     * @property offerSetPassword Whether to offer setting a password first
     * @property retryable True when sending the same request again could succeed
     */
    data class Entering(
        override val kind: IdentifierKind,
        val sending: Boolean = false,
        val valueKey: String? = null,
        val passwordKey: String? = null,
        val bannerKey: String? = null,
        val offerSetPassword: Boolean = false,
        val retryable: Boolean = false,
    ) : ReplaceContactUiState

    /**
     * A code went to the new value.
     *
     * @property kind Phone or email
     * @property checking The code is with the server
     * @property messageKey Why the last code was refused, or null
     * @property retryable Read from the server's envelope
     * @property attemptsLeft The server's tries-left count, as sent, or null
     */
    data class AwaitingCode(
        override val kind: IdentifierKind,
        val checking: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
        val attemptsLeft: String? = null,
    ) : ReplaceContactUiState

    /**
     * Replaced; the old value was told.
     *
     * @property kind Phone or email
     */
    data class Replaced(override val kind: IdentifierKind) : ReplaceContactUiState
}

/**
 * Routes the replace flow's answers. Pure; the unit under test
 * (functional-spec § 4, W6 step 4).
 */
object ReplaceContactStateMapper {
    /** The key shown when no answer arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a reply cannot be acted on. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** A replacement by an account with no password yet. */
    const val PASSWORD_REQUIRED_KEY: String = "account.contact.password_required"

    /** The current password typed was wrong. */
    const val CURRENT_WRONG_KEY: String = "auth.password.current_wrong"

    /** Refusals about the new value itself, shown under it. */
    private val VALUE_KEYS: Set<String> = setOf("account.contact.already_set", "phone.invalid", "email.invalid")

    /** The detail a wrong code carries: how many tries are left. */
    private const val ATTEMPTS_LEFT = "attempts_left"

    /**
     * Map the code request.
     *
     * @param result The repository's answer
     * @param form The entry step as it was when sent
     * @return The code step, or the entry step with the refusal
     */
    fun afterRequest(result: AuthResult<IssueResponse>, form: ReplaceContactUiState.Entering): ReplaceContactUiState {
        val cleared = ReplaceContactUiState.Entering(form.kind)
        return when (result) {
            is AuthResult.Ok ->
                if (result.value.status.isEmpty()) {
                    cleared.copy(bannerKey = UNEXPECTED_KEY)
                } else {
                    ReplaceContactUiState.AwaitingCode(form.kind)
                }
            AuthResult.TransportFailure -> cleared.copy(bannerKey = OFFLINE_KEY, retryable = true)
            is AuthResult.Refused -> {
                val error = result.envelope.error
                when (error.messageKey) {
                    PASSWORD_REQUIRED_KEY -> cleared.copy(bannerKey = PASSWORD_REQUIRED_KEY, offerSetPassword = true)
                    CURRENT_WRONG_KEY -> cleared.copy(passwordKey = CURRENT_WRONG_KEY)
                    in VALUE_KEYS -> cleared.copy(valueKey = error.messageKey)
                    else -> cleared.copy(bannerKey = error.messageKey, retryable = error.retryable)
                }
            }
        }
    }

    /**
     * Map the code check. Every refusal stays on the code step; the code
     * stays unspent where the server says so (`taken`, `change_limit`).
     *
     * @param result The repository's answer
     * @param step The code step as it was when sent
     * @return Replaced, or the code step with the refusal
     */
    fun afterVerify(result: AuthResult<MeDto>, step: ReplaceContactUiState.AwaitingCode): ReplaceContactUiState =
        when (result) {
            is AuthResult.Ok -> ReplaceContactUiState.Replaced(step.kind)
            is AuthResult.Refused ->
                step.copy(
                    checking = false,
                    messageKey = result.envelope.error.messageKey,
                    retryable = result.envelope.error.retryable,
                    attemptsLeft = result.envelope.error.details?.get(ATTEMPTS_LEFT),
                )
            AuthResult.TransportFailure ->
                step.copy(checking = false, messageKey = OFFLINE_KEY, retryable = true, attemptsLeft = null)
        }
}

/**
 * Holds the replace-contact screen [FR8.2]. Holds no business logic.
 *
 * **The password is held for one request and no longer** [NFR3.4]: it
 * passes from the screen to the repository and is not kept, so "Send a
 * new code" returns to the entry step, where it is typed again. Keeping
 * it for a resend would hold a secret past its use (frontend-components
 * § 3, which records why this differs from Add).
 *
 * @property repository The authenticated account calls
 * @param kind Whether a phone or an email is being replaced
 */
class ReplaceContactViewModel(
    private val repository: AccountRepository,
    kind: IdentifierKind,
) : ViewModel() {

    private val _state = MutableStateFlow<ReplaceContactUiState>(ReplaceContactUiState.Entering(kind))

    /** What the screen renders. */
    val state: StateFlow<ReplaceContactUiState> = _state.asStateFlow()

    // The new value the outstanding code went to.
    private var pending: Identifier? = null

    /**
     * Ask for a code to the new value; also the retry of a failed request.
     * Ignored while one is with the server.
     *
     * @param value The new phone or email; its shape is the screen's to check
     * @param password The current password; passed through, never kept
     */
    fun requestCode(value: String, password: String) {
        val form = _state.value as? ReplaceContactUiState.Entering ?: return
        if (form.sending) return
        val identifier = Identifier(form.kind, value)
        pending = identifier
        val sending = ReplaceContactUiState.Entering(form.kind, sending = true)
        _state.value = sending
        viewModelScope.launch {
            val result = repository.replaceContact(identifier, password)
            _state.value = ReplaceContactStateMapper.afterRequest(result, sending)
        }
    }

    /**
     * Present the code; also the explicit retry after a failure.
     *
     * @param code The six digits
     */
    fun submitCode(code: String) {
        val step = _state.value as? ReplaceContactUiState.AwaitingCode ?: return
        val identifier = pending ?: return
        if (step.checking) return
        val checking = step.copy(checking = true, messageKey = null, retryable = false, attemptsLeft = null)
        _state.value = checking
        viewModelScope.launch {
            _state.value = ReplaceContactStateMapper.afterVerify(repository.verifyContact(identifier, code), checking)
        }
    }

    /**
     * "Send a new code" or "Change": back to the entry step, where the
     * password is typed again because it was not kept.
     */
    fun changeValue() {
        pending = null
        _state.value = ReplaceContactUiState.Entering(_state.value.kind)
    }
}
