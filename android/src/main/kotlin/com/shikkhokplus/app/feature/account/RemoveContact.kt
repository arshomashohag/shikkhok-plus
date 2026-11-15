package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the remove-contact sheet renders (functional-spec 3.6).
 */
sealed interface RemoveContactUiState {
    /**
     * The question, naming the contact, and the password.
     *
     * @property kind Phone or email
     * @property contact The value being removed, as the server last said
     * @property removing The removal is with the server
     * @property passwordKey A refusal shown under the password, or null
     * @property bannerKey A refusal shown in the sheet, or null
     * @property offerAddOther Whether to offer adding the other kind: set
     *   for `account.contact.last_one` only
     * @property offerSetPassword Whether to offer setting a password first
     * @property retryable True when sending the same removal again could succeed
     */
    data class Confirming(
        val kind: IdentifierKind,
        val contact: String,
        val removing: Boolean = false,
        val passwordKey: String? = null,
        val bannerKey: String? = null,
        val offerAddOther: Boolean = false,
        val offerSetPassword: Boolean = false,
        val retryable: Boolean = false,
    ) : RemoveContactUiState {
        // The person's own contact [NFR3.2].
        override fun toString(): String =
            "Confirming(kind=$kind, removing=$removing, passwordKey=$passwordKey, bannerKey=$bannerKey, " +
                "offerAddOther=$offerAddOther, offerSetPassword=$offerSetPassword, retryable=$retryable, contact=***)"
    }

    /** Removed; the sheet closes and Contacts re-reads. */
    data object Removed : RemoveContactUiState
}

/**
 * Routes the removal's answers. Pure; the unit under test.
 *
 * **The client never decides whether a contact may go** [NFR3.11]: the
 * last one is the server's to refuse, and the sheet says so in the
 * server's words and offers adding the other kind.
 */
object RemoveContactStateMapper {
    /** The key shown when no answer arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The account's only contact. */
    const val LAST_ONE_KEY: String = "account.contact.last_one"

    /** A removal by an account with no password yet. */
    const val PASSWORD_REQUIRED_KEY: String = "account.contact.password_required"

    /** The current password typed was wrong. */
    const val CURRENT_WRONG_KEY: String = "auth.password.current_wrong"

    /**
     * Map what a removal came to.
     *
     * @param result The repository's answer
     * @param form The sheet as it was when sent
     * @return Removed, or the sheet with the refusal
     */
    fun afterRemove(result: AuthResult<MeDto>, form: RemoveContactUiState.Confirming): RemoveContactUiState {
        val cleared = RemoveContactUiState.Confirming(form.kind, form.contact)
        return when (result) {
            is AuthResult.Ok -> RemoveContactUiState.Removed
            AuthResult.TransportFailure -> cleared.copy(bannerKey = OFFLINE_KEY, retryable = true)
            is AuthResult.Refused -> {
                val error = result.envelope.error
                when (error.messageKey) {
                    LAST_ONE_KEY -> cleared.copy(bannerKey = LAST_ONE_KEY, offerAddOther = true)
                    CURRENT_WRONG_KEY -> cleared.copy(passwordKey = CURRENT_WRONG_KEY)
                    PASSWORD_REQUIRED_KEY -> cleared.copy(bannerKey = PASSWORD_REQUIRED_KEY, offerSetPassword = true)
                    else -> cleared.copy(bannerKey = error.messageKey, retryable = error.retryable)
                }
            }
        }
    }
}

/**
 * Holds the remove-contact sheet [FR8.4]. Holds no business logic.
 *
 * The password passes from the sheet's `remember` to the repository and
 * is not kept; a retry is the sheet calling [remove] again with what is
 * still typed, so it resends the same `{kind, password}`.
 *
 * @property repository The authenticated account calls
 * @param kind Which contact is being removed
 * @param contact Its value, as the server last said, for the question
 */
class RemoveContactViewModel(
    private val repository: AccountRepository,
    kind: IdentifierKind,
    contact: String,
) : ViewModel() {

    private val _state = MutableStateFlow<RemoveContactUiState>(RemoveContactUiState.Confirming(kind, contact))

    /** What the sheet renders. */
    val state: StateFlow<RemoveContactUiState> = _state.asStateFlow()

    /**
     * Remove; also the explicit retry. Ignored while one is with the server.
     *
     * @param password The current password; passed through, never kept
     */
    fun remove(password: String) {
        val form = _state.value as? RemoveContactUiState.Confirming ?: return
        if (form.removing || password.isEmpty()) return
        val sending = RemoveContactUiState.Confirming(form.kind, form.contact, removing = true)
        _state.value = sending
        viewModelScope.launch {
            _state.value = RemoveContactStateMapper.afterRemove(repository.removeContact(form.kind, password), sending)
        }
    }
}
