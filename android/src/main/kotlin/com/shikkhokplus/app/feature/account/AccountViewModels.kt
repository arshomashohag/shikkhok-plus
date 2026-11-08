package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds the set-or-change-password screen's state. Holds no business
 * logic [TC-9, D-31]; every decision is [AccountStateMapper]'s.
 *
 * **The passwords are never held here.** They live in the screen's
 * `remember` and pass through [submit] to the repository; the retry is
 * the screen calling [submit] again with what is still typed.
 *
 * @property repository Where the password is set
 * @param hasPassword Whether the account already has one, as `GET /v1/me`
 *   said, which decides whether the current one is asked for
 */
class PasswordChangeViewModel(
    private val repository: AccountRepository,
    hasPassword: Boolean,
) : ViewModel() {

    private val _state = MutableStateFlow<PasswordChangeUiState>(PasswordChangeUiState.Editing(hasPassword))

    /** What the screen renders. */
    val state: StateFlow<PasswordChangeUiState> = _state.asStateFlow()

    /**
     * Send the form; also the explicit retry after a failure.
     *
     * Ignored while a save is in flight, and once done.
     *
     * @param current The current password, or empty when none is asked for
     * @param newPassword The new password
     * @param confirm Its second copy
     */
    fun submit(current: String, newPassword: String, confirm: String) {
        val form = _state.value as? PasswordChangeUiState.Editing ?: return
        if (form.saving) return
        val refused = AccountStateMapper.checkPassword(form, current, newPassword, confirm)
        if (refused != null) {
            _state.value = refused
            return
        }
        _state.value = form.copy(saving = true, messageKey = null, retryable = false)
        viewModelScope.launch {
            val result = repository.setPassword(current.takeIf { form.hasPassword }, newPassword)
            _state.value = AccountStateMapper.afterPassword(result, form)
        }
    }
}

/**
 * Holds the add-a-phone-or-email screen's state. Holds no business logic
 * [TC-9, D-31]; every decision is [AccountStateMapper]'s.
 *
 * **V1 accepts no write without connectivity** [TC-8, D-9]: a failure is
 * shown with an explicit retry, and nothing is sent again by itself --
 * each code request is a message the server pays for.
 *
 * @property repository Where the contact is added
 * @param kind Whether a phone or an email is being added
 */
class AddContactViewModel(
    private val repository: AccountRepository,
    kind: IdentifierKind,
) : ViewModel() {

    private val _state = MutableStateFlow<AddContactUiState>(AddContactUiState.Entering(kind))

    /** What the screen renders. */
    val state: StateFlow<AddContactUiState> = _state.asStateFlow()

    // The phone or email the outstanding code went to.
    private var pending: Identifier? = null

    /**
     * Ask for a code to the phone or email typed; also the retry of a
     * failed request, and "Send a new code".
     *
     * @param value What was typed; its shape is the screen's to check
     */
    fun requestCode(value: String) {
        val kind = _state.value.kind
        val identifier = Identifier(kind, value)
        pending = identifier
        val form = AddContactUiState.Entering(kind)
        _state.value = form.copy(sending = true)
        viewModelScope.launch {
            _state.value = AccountStateMapper.afterContactRequested(repository.requestContact(identifier), form)
        }
    }

    /**
     * Ask again for a code to the same phone or email, at the person's
     * request. The code step stays on screen while it is sent.
     */
    fun resendCode() {
        val step = _state.value as? AddContactUiState.AwaitingCode ?: return
        val identifier = pending ?: return
        if (step.checking) return
        _state.value = step.copy(checking = true, messageKey = null, retryable = false)
        viewModelScope.launch {
            _state.value = AccountStateMapper.afterContactResent(repository.requestContact(identifier), step)
        }
    }

    /**
     * Present the code; also the explicit retry after a failure.
     *
     * @param code The six digits
     */
    fun submitCode(code: String) {
        val step = _state.value as? AddContactUiState.AwaitingCode ?: return
        val identifier = pending ?: return
        if (step.checking) return
        _state.value = step.copy(checking = true, messageKey = null, retryable = false)
        viewModelScope.launch {
            _state.value = AccountStateMapper.afterContactVerified(repository.verifyContact(identifier, code), step)
        }
    }

    /** Back from the code to the field, to correct what was typed. */
    fun changeValue() {
        pending = null
        _state.value = AddContactUiState.Entering(_state.value.kind)
    }
}
