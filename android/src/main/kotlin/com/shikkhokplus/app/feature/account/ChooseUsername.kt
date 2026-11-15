package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.UsernameChangeDto
import com.shikkhokplus.app.core.ui.UsernameAvailabilityChecker
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the choose-username gate renders (functional-spec 3.4).
 *
 * Holds no username, contact or password, so it needs no masked
 * `toString` [NFR3.2].
 */
sealed interface ChooseUsernameUiState {
    /**
     * The field, and Continue.
     *
     * @property saving The choice is with the server
     * @property messageKey Why the last choice was refused, or null
     * @property retryable True when sending the same choice again could
     *   succeed (no answer arrived, or the server said so)
     */
    data class Editing(
        val saving: Boolean = false,
        val messageKey: String? = null,
        val retryable: Boolean = false,
    ) : ChooseUsernameUiState

    /** Another device chose a name first; the account is being read again. */
    data object Rereading : ChooseUsernameUiState

    /** A username is chosen; the gate goes. */
    data object Done : ChooseUsernameUiState
}

/**
 * Maps the gate's answers. Pure; the unit under test.
 */
object ChooseUsernameStateMapper {
    /** The key shown when no answer arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * The refusal a FIRST choice gets when the account already has a name:
     * another device chose one first (U1 W7 step 3). Not shown; it
     * triggers a re-read, which lifts the gate.
     */
    const val PASSWORD_REQUIRED_KEY: String = "account.username.password_required"

    /**
     * Map what a choice came to.
     *
     * @param result The repository's answer
     * @return Done, Rereading, or the form with the refusal
     */
    fun afterChoice(result: AuthResult<UsernameChangeDto>): ChooseUsernameUiState =
        when (result) {
            is AuthResult.Ok -> ChooseUsernameUiState.Done
            is AuthResult.Refused ->
                if (result.envelope.error.messageKey == PASSWORD_REQUIRED_KEY) {
                    ChooseUsernameUiState.Rereading
                } else {
                    ChooseUsernameUiState.Editing(
                        messageKey = result.envelope.error.messageKey,
                        retryable = result.envelope.error.retryable,
                    )
                }
            AuthResult.TransportFailure -> ChooseUsernameUiState.Editing(messageKey = OFFLINE_KEY, retryable = true)
        }

    /**
     * Map what the re-read came to.
     *
     * @param read Whether the re-read lifted the gate; false when it
     *   failed or the account still requires a username
     * @return Done, or the form with a retry
     */
    fun afterReread(read: Boolean): ChooseUsernameUiState =
        if (read) {
            ChooseUsernameUiState.Done
        } else {
            ChooseUsernameUiState.Editing(messageKey = OFFLINE_KEY, retryable = true)
        }
}

/**
 * Holds the choose-username gate [FR5.2, FR5.4]. Holds no business logic.
 *
 * The first choice needs no password, so none is held. The gate is
 * lifted by the session, never by this: [onChosen] publishes the state
 * the session was holding back, and [reread] reads the account again
 * when the server says the account already has a name.
 *
 * @property repository The authenticated account calls
 * @property onChosen Lifts the gate after a 200 (`SessionViewModel.usernameChosen`)
 * @property reread Reads the account again, quietly; true when the read lifted the gate
 */
class ChooseUsernameViewModel(
    private val repository: AccountRepository,
    private val onChosen: () -> Unit,
    private val reread: suspend () -> Boolean,
) : ViewModel() {

    /** The live check, on the AUTHENTICATED lookup [W4 step 3]. */
    val availability: UsernameAvailabilityChecker =
        UsernameAvailabilityChecker(viewModelScope, repository::checkUsername)

    private val _state = MutableStateFlow<ChooseUsernameUiState>(ChooseUsernameUiState.Editing())

    /** What the gate renders. */
    val state: StateFlow<ChooseUsernameUiState> = _state.asStateFlow()

    // The last thing sent, for an explicit Retry; never a secret here.
    private var lastAction: (() -> Unit)? = null

    /**
     * The field changed.
     *
     * @param text What it holds
     */
    fun edited(text: String) = availability.edited(text)

    /**
     * Send the choice. Ignored while one is with the server, or once done.
     *
     * @param username What was typed
     */
    fun submit(username: String) {
        val form = _state.value as? ChooseUsernameUiState.Editing ?: return
        if (form.saving) return
        val name = username.trim()
        if (name.isEmpty()) return
        lastAction = { submit(name) }
        _state.value = ChooseUsernameUiState.Editing(saving = true)
        viewModelScope.launch {
            val next = ChooseUsernameStateMapper.afterChoice(repository.changeUsername(name, null))
            _state.value = next
            when (next) {
                ChooseUsernameUiState.Done -> onChosen()
                ChooseUsernameUiState.Rereading -> rereadAccount()
                is ChooseUsernameUiState.Editing -> Unit
            }
        }
    }

    /** Repeat what failed, when the person asks and only if it may help. */
    fun retry() {
        val form = _state.value as? ChooseUsernameUiState.Editing ?: return
        if (!form.retryable) return
        _state.value = form.copy(retryable = false)
        lastAction?.invoke()
    }

    private suspend fun rereadAccount() {
        lastAction = {
            _state.value = ChooseUsernameUiState.Rereading
            viewModelScope.launch { rereadAccount() }
        }
        _state.value = ChooseUsernameStateMapper.afterReread(reread())
    }
}
