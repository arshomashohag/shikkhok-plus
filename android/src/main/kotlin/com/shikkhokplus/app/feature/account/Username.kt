package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.UsernameChangeDto
import com.shikkhokplus.app.core.ui.UsernameAvailabilityChecker
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.SignupStateMapper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the Username screen in Settings renders (functional-spec 3.5).
 *
 * **The client never decides whether a rename is allowed** [FR11.3,
 * NFR3.11]: Change is always offered, and a refusal says when, in the
 * server's own words and with the server's own date.
 */
sealed interface UsernameUiState {
    /**
     * The stored username, read-only, and Change.
     *
     * @property username The display form as stored, or null before one
     *   is chosen (or read)
     * @property nextChangeAt When the next rename is allowed, as the
     *   server sent it in this screen's life, or null
     */
    data class Viewing(val username: String?, val nextChangeAt: String? = null) : UsernameUiState {
        override fun toString(): String = "Viewing(nextChangeAt=$nextChangeAt, username=***)"
    }

    /**
     * The rename form.
     *
     * @property current The stored username, or null
     * @property saving The rename is with the server
     * @property usernameKey A refusal shown under the new name, or null
     * @property passwordKey A refusal shown under the password, or null
     * @property bannerKey A refusal shown as a banner, or null
     * @property bannerDate The date a "too soon" banner names, as sent
     * @property offerSetPassword Whether to offer setting a password first
     * @property retryable True when sending the same form again could succeed
     */
    data class Editing(
        val current: String?,
        val saving: Boolean = false,
        val usernameKey: String? = null,
        val passwordKey: String? = null,
        val bannerKey: String? = null,
        val bannerDate: String? = null,
        val offerSetPassword: Boolean = false,
        val retryable: Boolean = false,
    ) : UsernameUiState {
        override fun toString(): String =
            "Editing(saving=$saving, usernameKey=$usernameKey, passwordKey=$passwordKey, bannerKey=$bannerKey, " +
                "bannerDate=$bannerDate, offerSetPassword=$offerSetPassword, retryable=$retryable, current=***)"
    }

    /**
     * Changed: the new name, and when it may change again.
     *
     * @property username The new display form, as stored
     * @property nextChangeAt When the next rename is allowed, or null
     */
    data class Changed(val username: String, val nextChangeAt: String?) : UsernameUiState {
        override fun toString(): String = "Changed(nextChangeAt=$nextChangeAt, username=***)"
    }
}

/**
 * Routes the rename's answers to a field or a banner. Pure; the unit
 * under test (functional-spec § 4).
 */
object UsernameStateMapper {
    /** The key shown when no answer arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** A rename inside the server's window. */
    const val TOO_SOON_KEY: String = "account.username.change_too_soon"

    /** A rename by an account with no password yet. */
    const val PASSWORD_REQUIRED_KEY: String = "account.username.password_required"

    /** The current password typed was wrong. */
    const val CURRENT_WRONG_KEY: String = "auth.password.current_wrong"

    /** Where a refusal carries the next allowed change. */
    const val NEXT_CHANGE_AT: String = "next_change_at"

    /**
     * The state the screen opens on, from the account as read.
     *
     * @param result The account read
     * @return Viewing, with the stored username or none
     */
    fun afterLoad(result: AuthResult<MeDto>): UsernameUiState =
        UsernameUiState.Viewing((result as? AuthResult.Ok)?.value?.username)

    /**
     * Map what a rename came to.
     *
     * @param result The repository's answer
     * @param form The form as it was when sent
     * @return Changed, or the form with the refusal where it belongs
     */
    fun afterChange(result: AuthResult<UsernameChangeDto>, form: UsernameUiState.Editing): UsernameUiState {
        val cleared = form.copy(saving = false)
        return when (result) {
            is AuthResult.Ok -> UsernameUiState.Changed(result.value.username, result.value.nextChangeAt)
            AuthResult.TransportFailure -> cleared.copy(bannerKey = OFFLINE_KEY, retryable = true)
            is AuthResult.Refused -> {
                val error = result.envelope.error
                when (error.messageKey) {
                    TOO_SOON_KEY ->
                        cleared.copy(bannerKey = TOO_SOON_KEY, bannerDate = error.details?.get(NEXT_CHANGE_AT))
                    PASSWORD_REQUIRED_KEY -> cleared.copy(bannerKey = PASSWORD_REQUIRED_KEY, offerSetPassword = true)
                    CURRENT_WRONG_KEY -> cleared.copy(passwordKey = CURRENT_WRONG_KEY)
                    in SignupStateMapper.USERNAME_MESSAGE_KEYS -> cleared.copy(usernameKey = error.messageKey)
                    else -> cleared.copy(bannerKey = error.messageKey, retryable = error.retryable)
                }
            }
        }
    }
}

/**
 * Holds the Username screen [FR7.1, FR7.2, FR7.5]. Holds no business logic.
 *
 * **The password passes through and is never kept**: it lives in the
 * screen's `remember` and reaches the repository once per Save.
 *
 * @property repository The authenticated account calls
 * @property profile Reads the stored username
 * @property onChanged Called after a rename, so More and the profile re-read
 */
class UsernameViewModel(
    private val repository: AccountRepository,
    private val profile: com.shikkhokplus.app.feature.profile.ProfileRepository,
    private val onChanged: () -> Unit = {},
) : ViewModel() {

    /** The live check, on the AUTHENTICATED lookup, so a released name reads available [W5 step 3]. */
    val availability: UsernameAvailabilityChecker =
        UsernameAvailabilityChecker(viewModelScope, repository::checkUsername)

    private val _state = MutableStateFlow<UsernameUiState>(UsernameUiState.Viewing(null))

    /** What the screen renders. */
    val state: StateFlow<UsernameUiState> = _state.asStateFlow()

    /** Read the stored username. */
    fun load() {
        viewModelScope.launch { _state.value = UsernameStateMapper.afterLoad(profile.profile()) }
    }

    /** Open the rename form; offered always, whatever the window [NFR3.11]. */
    fun startChange() {
        val current =
            when (val shown = _state.value) {
                is UsernameUiState.Viewing -> shown.username
                is UsernameUiState.Changed -> shown.username
                is UsernameUiState.Editing -> return
            }
        _state.value = UsernameUiState.Editing(current)
    }

    /** Leave the form without saving. */
    fun cancel() {
        val form = _state.value as? UsernameUiState.Editing ?: return
        if (form.saving) return
        _state.value = UsernameUiState.Viewing(form.current)
    }

    /**
     * The new name changed.
     *
     * @param text What the field holds
     */
    fun edited(text: String) {
        availability.edited(text)
        val form = _state.value as? UsernameUiState.Editing ?: return
        if (form.usernameKey != null) _state.value = form.copy(usernameKey = null)
    }

    /**
     * Save the rename; also the explicit retry. Ignored while one is with
     * the server.
     *
     * @param username The new name, as typed
     * @param password The current password; passed through, never kept
     */
    fun save(username: String, password: String) {
        val form = _state.value as? UsernameUiState.Editing ?: return
        if (form.saving || username.isBlank() || password.isEmpty()) return
        val sending = UsernameUiState.Editing(form.current, saving = true)
        _state.value = sending
        viewModelScope.launch {
            val next = UsernameStateMapper.afterChange(repository.changeUsername(username.trim(), password), sending)
            _state.value = next
            if (next is UsernameUiState.Changed) onChanged()
        }
    }
}
