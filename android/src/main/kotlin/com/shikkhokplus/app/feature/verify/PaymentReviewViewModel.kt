package com.shikkhokplus.app.feature.verify

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.PaymentApprovalBodyDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** The most characters a note to the family may hold. */
const val REVIEW_NOTE_MAX: Int = 500


/**
 * Holds R2 to R4: one payment, its decision, and the approval sheet.
 *
 * **Money is the server's.** A payment that matches is approved at the
 * amount the payer reported; any other is approved through the sheet,
 * which asks only for the inputs the server will require. A write that
 * fails keeps the sheet open for an explicit retry, and a conflict
 * reloads the payment so the teacher sees what was decided [TC-8, D-9].
 *
 * @property repository The payment reads and writes
 */
class PaymentReviewViewModel(
    private val repository: PaymentReviewRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ReviewUiState>(ReviewUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ReviewUiState> = _state.asStateFlow()

    private val _sheet = MutableStateFlow<ApprovalSheet?>(null)

    /** The approval sheet, while it is open. */
    val sheet: StateFlow<ApprovalSheet?> = _sheet.asStateFlow()

    private var submissionId: String = ""

    /**
     * Load a payment.
     *
     * @param id The payment
     */
    fun load(id: String) {
        submissionId = id
        _state.value = ReviewUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /** Repeat the load, only when asked. */
    fun retry() = load(submissionId)

    /**
     * Approve as reported when it matches, else open the sheet.
     *
     * @param note A note to the family, if the teacher typed one
     */
    fun approve(note: String = "") {
        val loaded = decidable() ?: return
        if (loaded.card.comparison == Comparison.MATCHES) {
            send(
                PaymentApprovalBodyDto(
                    receivedAmount = loaded.card.totalAmount,
                    note = note.trim().takeIf { it.isNotEmpty() },
                    correcting = loaded.correcting,
                ),
            )
        } else {
            openSheet(note)
        }
    }

    /**
     * Open the sheet, starting from what the payer reported.
     *
     * @param note A note already typed on the detail
     */
    fun openSheet(note: String = "") {
        val loaded = decidable() ?: return
        _sheet.value =
            ApprovalSheet(
                card = loaded.card,
                typed = loaded.card.totalAmount.amount.toPlainString(),
                note = note.take(REVIEW_NOTE_MAX),
            )
    }

    /** Close the sheet without deciding. */
    fun closeSheet() {
        _sheet.value = null
    }

    /**
     * The teacher typed a different amount received.
     *
     * Choices that no longer apply to the new amount are dropped.
     *
     * @param typed The amount as typed
     */
    fun typeAmount(typed: String) {
        val current = _sheet.value ?: return
        val next = current.copy(typed = typed)
        _sheet.value =
            if (next.side == current.side) {
                next
            } else {
                next.copy(disposition = null, childId = null)
            }
    }

    /**
     * Choose what happens to a shortfall.
     *
     * @param disposition `carried` or `waived`
     */
    fun chooseDisposition(disposition: String) {
        _sheet.value = _sheet.value?.copy(disposition = disposition)
    }

    /**
     * Choose the child who carries a shortfall or gets a credit.
     *
     * @param enrollmentId The child's seat
     */
    fun chooseChild(enrollmentId: String) {
        _sheet.value = _sheet.value?.copy(childId = enrollmentId)
    }

    /**
     * Type the note shown to the family with the decision.
     *
     * @param note The note
     */
    fun typeNote(note: String) {
        _sheet.value = _sheet.value?.copy(note = note.take(REVIEW_NOTE_MAX))
    }

    /** Send the sheet's approval, once everything it needs is supplied. */
    fun confirmApproval() {
        val sheet = _sheet.value ?: return
        val loaded = decidable() ?: return
        val received = sheet.received ?: return
        if (!sheet.canConfirm) return
        val bearer = sheet.childId.takeIf { sheet.needsChild }
        send(
            PaymentApprovalBodyDto(
                receivedAmount = received,
                shortfallDisposition = sheet.disposition.takeIf { sheet.needsDisposition },
                carriedByEnrollmentId = bearer.takeIf { sheet.side == AmountSide.SHORT },
                creditToEnrollmentId = bearer.takeIf { sheet.side == AmountSide.OVER },
                note = sheet.note.trim().takeIf { it.isNotEmpty() },
                correcting = loaded.correcting,
            ),
        )
    }

    /**
     * Reject the payment, once the teacher has confirmed.
     *
     * @param note Why; blank is sent as no note
     */
    fun reject(note: String) {
        val loaded = decidable() ?: return
        write(loaded) { repository.reject(submissionId, note.trim().takeIf { it.isNotEmpty() }, loaded.correcting) }
    }

    /** Offer Approve and Reject again on a decided payment. */
    fun changeDecision() {
        val loaded = _state.value as? ReviewUiState.Loaded ?: return
        _state.value = loaded.copy(correcting = true, errorKey = null)
    }

    /**
     * The loaded payment, when a decision may be sent for it now.
     *
     * @return The state, or null while busy, undecidable or not loaded
     */
    private fun decidable(): ReviewUiState.Loaded? =
        (_state.value as? ReviewUiState.Loaded)?.takeIf { it.canDecide && !it.busy }

    /**
     * Send an approval.
     *
     * @param body The approval
     */
    private fun send(body: PaymentApprovalBodyDto) {
        val loaded = decidable() ?: return
        write(loaded) { repository.approve(submissionId, body) }
    }

    /**
     * Send a decision, then show the payment as the server now has it.
     *
     * @param loaded The state the decision is made from
     * @param call The decision
     */
    private fun write(loaded: ReviewUiState.Loaded, call: suspend () -> AuthResult<PaymentReviewDto>) {
        _state.value = loaded.copy(busy = true, errorKey = null)
        viewModelScope.launch {
            when (val result = call()) {
                is AuthResult.Ok -> {
                    _sheet.value = null
                    _state.value = VerifyStateMapper.afterDetail(result.value)
                }
                is AuthResult.Refused -> refused(loaded, result)
                AuthResult.TransportFailure ->
                    _state.value = loaded.copy(busy = false, errorKey = VerifyStateMapper.OFFLINE_KEY)
            }
        }
    }

    /**
     * Handle a refused decision: a conflict reloads, any other keeps the sheet.
     *
     * @param loaded The state the decision was made from
     * @param result The refusal
     */
    private suspend fun refused(loaded: ReviewUiState.Loaded, result: AuthResult.Refused) {
        val error = result.envelope.error
        if (error.code != VerifyStateMapper.ALREADY_DECIDED_CODE) {
            _state.value = loaded.copy(busy = false, errorKey = error.messageKey)
            return
        }
        _sheet.value = null
        val reloaded = read()
        _state.value =
            if (reloaded is ReviewUiState.Loaded) {
                reloaded.copy(errorKey = error.messageKey)
            } else {
                loaded.copy(busy = false, errorKey = error.messageKey)
            }
    }

    /**
     * Read the payment into a state.
     *
     * @return The state to show
     */
    private suspend fun read(): ReviewUiState =
        when (val result = repository.detail(submissionId)) {
            is AuthResult.Ok -> VerifyStateMapper.afterDetail(result.value)
            is AuthResult.Refused -> VerifyStateMapper.detailError(result.envelope)
            AuthResult.TransportFailure -> VerifyStateMapper.detailOffline()
        }
}
