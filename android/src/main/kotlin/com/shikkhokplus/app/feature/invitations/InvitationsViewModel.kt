package com.shikkhokplus.app.feature.invitations

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.DecisionDto
import com.shikkhokplus.app.core.network.InvitationDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the invitations screen needs from the network.
 *
 * Declared here rather than in `core.network` for the same reason
 * [com.shikkhokplus.app.feature.auth.AuthRepository] is: the feature
 * states what it needs and the network layer supplies it.
 */
interface InvitationsRepository {
    /**
     * List the seats awaiting this person's decision.
     *
     * @return The seats, a refusal, or a transport failure
     */
    suspend fun list(): AuthResult<List<InvitationDto>>

    /**
     * Read one seat.
     *
     * @param enrollmentId The seat to read
     * @return The seat, a refusal, or a transport failure
     */
    suspend fun detail(enrollmentId: String): AuthResult<InvitationDto>

    /**
     * Accept a seat, granting the lens it carries.
     *
     * @param enrollmentId The seat being accepted
     * @return The decided seat, or why the server refused
     */
    suspend fun accept(enrollmentId: String): AuthResult<DecisionDto>

    /**
     * Decline a seat.
     *
     * @param enrollmentId The seat being declined
     * @return The decided seat, or why the server refused
     */
    suspend fun decline(enrollmentId: String): AuthResult<DecisionDto>
}

/**
 * Holds the invitations screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [InvitationsStateMapper], including
 * **which decline sheet a holder reads** — the one rule here that is
 * genuinely role-dependent [BR5.2].
 *
 * **This is the acceptance model's client half.** Before D1, a teacher
 * typing a phone number granted a stranger a guardian lens over a
 * child's records; a seat now grants nothing until its holder accepts.
 * These are the calls that let them.
 */
class InvitationsViewModel(
    private val repository: InvitationsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<InvitationsUiState>(InvitationsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<InvitationsUiState> = _state.asStateFlow()

    private var lastAction: (() -> Unit)? = null

    /** Load the seats awaiting a decision. */
    fun load() {
        lastAction = { load() }
        _state.value = InvitationsUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.list()) {
                    is AuthResult.Ok -> InvitationsStateMapper.afterLoad(result.value)
                    is AuthResult.Refused ->
                        InvitationsStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        InvitationsStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Open one seat.
     *
     * @param enrollmentId The seat to open
     */
    fun open(enrollmentId: String) {
        lastAction = { open(enrollmentId) }
        _state.value = InvitationsUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.detail(enrollmentId)) {
                    is AuthResult.Ok -> InvitationsStateMapper.afterDetail(result.value)
                    is AuthResult.Refused ->
                        InvitationsStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        InvitationsStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Accept a seat.
     *
     * @param enrollmentId The seat being accepted
     */
    fun accept(enrollmentId: String) {
        lastAction = { accept(enrollmentId) }
        decide { repository.accept(enrollmentId) }
    }

    /**
     * Ask for the decline confirmation.
     *
     * **No network call, and the sheet is chosen here from what the
     * server said** [BR5.2]. A guardian's decline leaves the student's
     * obligation standing, so a guardian must not read a sheet saying
     * the fee stops — which one confirmation shown to both roles once
     * did.
     *
     * @param enrollmentId The seat being declined
     */
    fun confirmDecline(enrollmentId: String) {
        val row = rowFor(enrollmentId) ?: return
        _state.value =
            InvitationsStateMapper.beforeDecline(row, heldAsGuardian = row.heldAsGuardian)
    }

    /**
     * Decline, once the person has read the confirmation.
     *
     * @param enrollmentId The seat being declined
     */
    fun decline(enrollmentId: String) {
        lastAction = { decline(enrollmentId) }
        decide { repository.decline(enrollmentId) }
    }

    /** Close the confirmation without deciding. */
    fun dismissSheet() {
        val current = _state.value
        if (current is InvitationsUiState.ConfirmingDecline) {
            _state.value = InvitationsUiState.Detail(current.row)
        }
    }

    /**
     * Retry, when the person asks.
     *
     * Never automatic: V1 has no local queue [TC-8, D-9].
     */
    fun retry() {
        lastAction?.invoke()
    }

    /**
     * Find the row a confirmation is about.
     *
     * @param enrollmentId The seat
     * @return The row, or null when the state holds no such seat
     */
    private fun rowFor(enrollmentId: String): InvitationRow? =
        when (val current = _state.value) {
            is InvitationsUiState.Loaded ->
                current.rows.firstOrNull { it.enrollmentId == enrollmentId }

            is InvitationsUiState.Detail ->
                current.row.takeIf { it.enrollmentId == enrollmentId }

            else -> null
        }

    /**
     * Run a decision call and map its outcome.
     *
     * @param call The accept or decline request
     */
    private fun decide(call: suspend () -> AuthResult<DecisionDto>) {
        _state.value = InvitationsUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = call()) {
                    is AuthResult.Ok -> InvitationsStateMapper.afterDecision(result.value)
                    is AuthResult.Refused ->
                        InvitationsStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        InvitationsStateMapper.afterTransportFailure()
                }
        }
    }
}
