package com.shikkhokplus.app.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.profile.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One of the account's two contacts, as the server last said.
 *
 * @property kind Phone or email
 * @property contact The value, or null when the account has none
 */
data class ContactCard(val kind: IdentifierKind, val contact: String?) {
    // The person's own contact [NFR3.2].
    override fun toString(): String = "ContactCard(kind=$kind, present=${contact != null}, contact=***)"

    /** Whether there is one: decides Replace and Remove versus Add. */
    val present: Boolean get() = contact != null
}

/**
 * What the Contacts screen renders (functional-spec 3.6).
 *
 * **Whatever the server answers is what is shown** [W6 step 6]: the
 * screen re-reads after every write and never edits its own copy.
 */
sealed interface ContactsUiState {
    /** The account is being read. */
    data object Loading : ContactsUiState

    /**
     * The two cards.
     *
     * @property phone The phone card
     * @property email The email card
     * @property passwordNote Whether to say a password is needed, from
     *   the server's `has_password`; the actions stay enabled [NFR3.11]
     * @property removedKind The kind just removed, for a "Removed" note, or null
     */
    data class Loaded(
        val phone: ContactCard,
        val email: ContactCard,
        val passwordNote: Boolean,
        val removedKind: IdentifierKind? = null,
    ) : ContactsUiState {
        override fun toString(): String =
            "Loaded(phone=$phone, email=$email, passwordNote=$passwordNote, removedKind=$removedKind)"
    }

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ContactsUiState
}

/**
 * Maps the account read to the cards. Pure; the unit under test.
 */
object ContactsStateMapper {
    /** The key shown when no answer arrived. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map the account read.
     *
     * **Remove is offered for every present contact, one alone included**
     * [NFR3.11]: whether the last one may go is the server's to refuse.
     *
     * @param result The account read
     * @param removedKind The kind just removed, or null
     * @return Loaded, or Failed
     */
    fun afterLoad(result: AuthResult<MeDto>, removedKind: IdentifierKind? = null): ContactsUiState =
        when (result) {
            is AuthResult.Ok ->
                ContactsUiState.Loaded(
                    phone = ContactCard(IdentifierKind.PHONE, result.value.phone),
                    email = ContactCard(IdentifierKind.EMAIL, result.value.email),
                    passwordNote = !result.value.hasPassword,
                    removedKind = removedKind,
                )
            is AuthResult.Refused ->
                ContactsUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> ContactsUiState.Failed(OFFLINE_KEY, retryable = true)
        }
}

/**
 * Holds the Contacts screen [FR8.1]. Holds no business logic.
 *
 * Reads `GET /v1/me` through the existing [ProfileRepository], so the
 * cards are the server's answer and nothing else.
 *
 * @property profile Reads the account
 */
class ContactsViewModel(
    private val profile: ProfileRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ContactsUiState>(ContactsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ContactsUiState> = _state.asStateFlow()

    /**
     * Read the account.
     *
     * @param removedKind The kind just removed, for its note, or null
     */
    fun load(removedKind: IdentifierKind? = null) {
        _state.value = ContactsUiState.Loading
        viewModelScope.launch { _state.value = ContactsStateMapper.afterLoad(profile.profile(), removedKind) }
    }

    /** Read again after a failure, when the person asks. */
    fun retry() = load()
}
