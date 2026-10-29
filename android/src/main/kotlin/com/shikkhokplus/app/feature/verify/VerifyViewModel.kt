package com.shikkhokplus.app.feature.verify

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds T4's state. Decisions about money are the server's [TC-9].
 *
 * **Approving a short claim opens the partial sheet** rather than
 * sending: approving less than the charge requires the teacher to say
 * whether the rest is carried or waived [BR5.4], and the server's own
 * comparison is what says the claim is short.
 *
 * @property repository The payment-check reads and writes
 */
class VerifyViewModel(
    private val repository: VerifyRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<VerifyUiState>(VerifyUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<VerifyUiState> = _state.asStateFlow()

    private val _sheet = MutableStateFlow<PartialSheet?>(null)

    /** The partial-approval sheet, while it is open. */
    val sheet: StateFlow<PartialSheet?> = _sheet.asStateFlow()

    private var previewJob: Job? = null

    /** Load the queue. */
    fun load() {
        _state.value = VerifyUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() = load()

    /**
     * Approve a claim as sent, or open the partial sheet for a short one.
     *
     * @param card The claim
     */
    fun approve(card: ClaimCard) {
        if (card.comparison == Comparison.SHORT) {
            openPartial(card)
            return
        }
        decide(card.claimId) { repository.approve(card.claimId, card.claimedAmount, null) }
    }

    /**
     * Reject a claim, once the teacher has confirmed.
     *
     * @param card The claim
     */
    fun reject(card: ClaimCard) {
        decide(card.claimId) { repository.reject(card.claimId) }
    }

    /**
     * Open the partial sheet, starting from what was claimed.
     *
     * @param card The claim
     */
    fun openPartial(card: ClaimCard) {
        _sheet.value = PartialSheet(card = card, typed = card.claimedAmount.amount.toPlainString())
        refreshPreview()
    }

    /** Close the partial sheet without deciding. */
    fun closePartial() {
        previewJob?.cancel()
        _sheet.value = null
    }

    /**
     * The teacher typed a different amount; ask the server what it leaves.
     *
     * @param typed The amount as typed
     */
    fun typePartial(typed: String) {
        val current = _sheet.value ?: return
        _sheet.value = current.copy(typed = typed, shortfall = null, dispositionRequired = false, disposition = null)
        refreshPreview()
    }

    /**
     * Choose what happens to the shortfall.
     *
     * @param disposition `carried` or `waived`
     */
    fun choose(disposition: String) {
        _sheet.value = _sheet.value?.copy(disposition = disposition)
    }

    /** Approve the partial amount with the chosen disposition. */
    fun confirmPartial() {
        val sheet = _sheet.value ?: return
        val amount = Money.fromTyped(sheet.typed) ?: return
        if (sheet.shortfall == null) return
        if (sheet.dispositionRequired && sheet.disposition == null) return
        val disposition = sheet.disposition.takeIf { sheet.dispositionRequired }
        closePartial()
        decide(sheet.card.claimId) { repository.approve(sheet.card.claimId, amount, disposition) }
    }

    /** Ask the server what the sheet's amount leaves short. */
    private fun refreshPreview() {
        val sheet = _sheet.value ?: return
        val amount = Money.fromTyped(sheet.typed) ?: return
        previewJob?.cancel()
        previewJob =
            viewModelScope.launch {
                val result = repository.preview(sheet.card.claimId, amount)
                val now = _sheet.value
                if (result is AuthResult.Ok && now != null && now.typed == sheet.typed) {
                    _sheet.value =
                        now.copy(
                            shortfall = result.value.shortfall,
                            dispositionRequired = result.value.dispositionRequired,
                        )
                }
            }
    }

    /**
     * Send a decision, keeping the list on screen, then reload it.
     *
     * @param claimId The claim being decided
     * @param write The decision
     */
    private fun decide(claimId: String, write: suspend () -> AuthResult<Unit>) {
        val current = _state.value as? VerifyUiState.Waiting ?: return
        if (current.busyClaimId != null) return
        _state.value = current.copy(busyClaimId = claimId, errorKey = null)
        viewModelScope.launch {
            when (val result = write()) {
                is AuthResult.Ok -> _state.value = read()
                is AuthResult.Refused ->
                    _state.value = current.copy(busyClaimId = null, errorKey = result.envelope.error.messageKey)
                AuthResult.TransportFailure ->
                    _state.value = current.copy(busyClaimId = null, errorKey = VerifyStateMapper.OFFLINE_KEY)
            }
        }
    }

    /**
     * Read the queue into a state.
     *
     * @return The state to show
     */
    private suspend fun read(): VerifyUiState =
        when (val result = repository.queue()) {
            is AuthResult.Ok -> VerifyStateMapper.afterLoad(result.value)
            is AuthResult.Refused -> VerifyStateMapper.afterError(result.envelope)
            AuthResult.TransportFailure -> VerifyStateMapper.afterTransportFailure()
        }
}
