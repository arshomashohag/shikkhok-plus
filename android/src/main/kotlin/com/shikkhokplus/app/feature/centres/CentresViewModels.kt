package com.shikkhokplus.app.feature.centres

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.CentreDto
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MembershipDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** The longest name the server stores, for a centre or a person. */
internal const val NAME_MAX: Int = 120

/** A member's role, as the server names it. */
enum class MemberRole(val wire: String) {
    /** Has every permission in the centre. */
    MANAGER("manager"),

    /** Teaches the classes assigned to them. */
    TEACHER("teacher"),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `role`
         * @return The role; anything unrecognised reads as teacher, the narrower
         */
        fun fromWire(wire: String): MemberRole = if (wire == MANAGER.wire) MANAGER else TEACHER
    }
}

/**
 * The open-a-centre form.
 *
 * @property name The centre's name
 * @property managerName The opener's name as the centre shows it
 * @property saving Whether the request is in flight
 * @property opened The centre, once the server opened it
 * @property failureKey Message key for the last refusal, or null
 */
data class OpenCentreUiState(
    val name: String = "",
    val managerName: String = "",
    val saving: Boolean = false,
    val opened: CentreDto? = null,
    val failureKey: String? = null,
) {
    /** Whether the form can be sent: both names given. */
    val canOpen: Boolean get() = !saving && opened == null && name.isNotBlank() && managerName.isNotBlank()
}

/**
 * Holds the open-a-centre form.
 *
 * @property repository The network
 * @param managerName The account's own name, to start the form from
 */
class OpenCentreViewModel(
    private val repository: CentresRepository,
    managerName: String = "",
) : ViewModel() {

    private val _state = MutableStateFlow(OpenCentreUiState(managerName = managerName.take(NAME_MAX)))

    /** What the form renders. */
    val state: StateFlow<OpenCentreUiState> = _state.asStateFlow()

    /**
     * Name the centre.
     *
     * @param text The centre's name
     */
    fun name(text: String) = _state.update { it.copy(name = text.take(NAME_MAX), failureKey = null) }

    /**
     * Name the opener.
     *
     * @param text Their name as the centre shows it
     */
    fun managerName(text: String) = _state.update { it.copy(managerName = text.take(NAME_MAX), failureKey = null) }

    /** Open the centre, when the form can be sent. */
    fun open() {
        val form = _state.value
        if (!form.canOpen) return
        _state.update { it.copy(saving = true, failureKey = null) }
        viewModelScope.launch {
            when (val result = repository.open(form.name.trim(), form.managerName.trim())) {
                is AuthResult.Ok -> _state.update { it.copy(saving = false, opened = result.value) }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }
}

/** A centre's members, as its managers see them. */
sealed interface MembersBody {
    /** Waiting for the list. */
    data object Loading : MembersBody

    /**
     * The members, live ones first as the server ordered them.
     *
     * @property members The server's rows
     */
    data class Loaded(val members: List<MemberDto>) : MembersBody

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MembersBody
}

/**
 * The members screen.
 *
 * @property body The list
 * @property inviteName The invite form's name
 * @property invitePhone The invite form's phone
 * @property inviteRole The invite form's role
 * @property inviting Whether an invitation is in flight
 * @property invited The name last invited, for the confirmation, or null
 * @property failureKey Message key for the last refused write, or null
 */
data class MembersUiState(
    val body: MembersBody = MembersBody.Loading,
    val inviteName: String = "",
    val invitePhone: String = "",
    val inviteRole: MemberRole = MemberRole.TEACHER,
    val inviting: Boolean = false,
    val invited: String? = null,
    val failureKey: String? = null,
) {
    /** Whether the invite form can be sent: a name and a phone, which the server checks. */
    val canInvite: Boolean get() = !inviting && inviteName.isNotBlank() && invitePhone.isNotBlank()
}

/**
 * Holds a centre's members: the list, inviting by phone, and removing.
 *
 * @property repository The network
 */
class MembersViewModel(
    private val repository: CentresRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MembersUiState())

    /** What the screen renders. */
    val state: StateFlow<MembersUiState> = _state.asStateFlow()

    /** Read the members. */
    fun load() {
        viewModelScope.launch { _state.update { it.copy(body = read()) } }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.update { it.copy(body = MembersBody.Loading) }
        load()
    }

    /**
     * Type the invitee's name.
     *
     * @param text Their name
     */
    fun inviteName(text: String) = _state.update { it.copy(inviteName = text.take(NAME_MAX), failureKey = null) }

    /**
     * Type the invitee's phone.
     *
     * @param text Their number
     */
    fun invitePhone(text: String) = _state.update { it.copy(invitePhone = text, failureKey = null) }

    /**
     * Choose the invitee's role.
     *
     * @param role Manager or teacher
     */
    fun inviteRole(role: MemberRole) = _state.update { it.copy(inviteRole = role, failureKey = null) }

    /** Send the invitation, then read the list as the server now has it. */
    fun invite() {
        val form = _state.value
        if (!form.canInvite) return
        _state.update { it.copy(inviting = true, failureKey = null, invited = null) }
        viewModelScope.launch {
            val result = repository.invite(form.inviteName.trim(), form.invitePhone.trim(), form.inviteRole.wire)
            when (result) {
                is AuthResult.Ok -> {
                    val body = read()
                    _state.update {
                        MembersUiState(body = body, invited = result.value.displayName)
                    }
                }
                is AuthResult.Refused ->
                    _state.update { it.copy(inviting = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(inviting = false, failureKey = OFFLINE_KEY) }
            }
        }
    }

    /**
     * Remove a member, then read the list again.
     *
     * @param memberId The membership
     */
    fun revoke(memberId: String) {
        viewModelScope.launch {
            when (val result = repository.revoke(memberId)) {
                is AuthResult.Ok -> {
                    val body = read()
                    _state.update { it.copy(body = body, failureKey = null) }
                }
                is AuthResult.Refused -> _state.update { it.copy(failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(failureKey = OFFLINE_KEY) }
            }
        }
    }

    private suspend fun read(): MembersBody =
        when (val result = repository.members()) {
            is AuthResult.Ok -> MembersBody.Loaded(result.value)
            is AuthResult.Refused ->
                MembersBody.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> MembersBody.Failed(OFFLINE_KEY, retryable = true)
        }
}

/**
 * The centres' offers to the signed-in account.
 *
 * @property offers The pending offers; declined ones are not shown
 * @property busy The offer being answered, or null
 * @property accepted Set when an offer was accepted, so the caller can
 *   re-read the account's workspaces and lenses
 * @property failureKey Message key for the last refusal, or null
 */
data class OffersUiState(
    val offers: List<MembershipDto> = emptyList(),
    val busy: String? = null,
    val accepted: Int = 0,
    val failureKey: String? = null,
)

/**
 * Holds the centres' offers: reading, accepting and declining.
 *
 * A failed read leaves the list empty rather than failing the screen it
 * sits on: the offers are a section of Invitations, not the screen.
 *
 * @property repository The network
 */
class CentreOffersViewModel(
    private val repository: CentresRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(OffersUiState())

    /** What the section renders. */
    val state: StateFlow<OffersUiState> = _state.asStateFlow()

    /** Read the pending offers. */
    fun load() {
        viewModelScope.launch {
            val offers = (repository.offers() as? AuthResult.Ok)?.value.orEmpty().filter { it.decision == "pending" }
            _state.update { it.copy(offers = offers) }
        }
    }

    /**
     * Accept an offer.
     *
     * @param memberId The membership
     */
    fun accept(memberId: String) = decide(memberId, accept = true)

    /**
     * Decline an offer.
     *
     * @param memberId The membership
     */
    fun decline(memberId: String) = decide(memberId, accept = false)

    private fun decide(memberId: String, accept: Boolean) {
        if (_state.value.busy != null || _state.value.offers.none { it.memberId == memberId }) return
        _state.update { it.copy(busy = memberId, failureKey = null) }
        viewModelScope.launch {
            val result = if (accept) repository.accept(memberId) else repository.decline(memberId)
            when (result) {
                is AuthResult.Ok ->
                    _state.update { current ->
                        current.copy(
                            offers = current.offers.filterNot { it.memberId == memberId },
                            busy = null,
                            accepted = current.accepted + if (accept) 1 else 0,
                        )
                    }
                is AuthResult.Refused ->
                    _state.update { it.copy(busy = null, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(busy = null, failureKey = OFFLINE_KEY) }
            }
        }
    }
}
