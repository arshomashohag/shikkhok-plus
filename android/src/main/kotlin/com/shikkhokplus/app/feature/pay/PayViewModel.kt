package com.shikkhokplus.app.feature.pay

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.ClaimSubmitDto
import com.shikkhokplus.app.core.network.PayablesDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What paying a fee needs from the network. */
interface PayRepository {
    /**
     * Read what this student can pay for.
     *
     * @return The payable months and waiting batches
     */
    suspend fun payables(): AuthResult<PayablesDto>

    /**
     * Read where to send money for one seat.
     *
     * @param enrollmentId The seat
     * @return The destination, or null when the teacher set no number
     */
    suspend fun destination(enrollmentId: String): AuthResult<PaymentDestinationDto?>

    /**
     * Record a payment for the teacher to check.
     *
     * @param enrollmentId The seat
     * @param claim What was paid
     * @return The pending claim
     */
    suspend fun submit(enrollmentId: String, claim: ClaimSubmitDto): AuthResult<ClaimDto>
}

/**
 * Holds the S3 "Pay a fee" flow: choose, fill in, send, sent.
 *
 * **Never queued.** A payment write needs a connection [TC-8, D-9]; a
 * failed send keeps what was typed and asks the student to send again.
 *
 * @property repository The network
 */
class PayViewModel(
    private val repository: PayRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<PayUiState>(PayUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<PayUiState> = _state.asStateFlow()

    private var choosing: PayUiState.Choosing? = null

    /**
     * Read what can be paid; open the one fee directly if it is the only
     * thing to show.
     *
     * @param preselect A seat to open straight away, as from a batch page
     */
    fun load(preselect: String? = null) {
        _state.value = PayUiState.Loading
        viewModelScope.launch {
            when (val result = repository.payables()) {
                is AuthResult.Ok -> {
                    val (options, waiting) = PayMapper.options(result.value)
                    val list = PayUiState.Choosing(options, waiting)
                    choosing = list
                    val direct =
                        options.firstOrNull { it.enrollmentId == preselect }
                            ?: options.singleOrNull()?.takeIf { waiting.isEmpty() }
                    if (direct == null) _state.value = list else open(direct)
                }
                is AuthResult.Refused ->
                    _state.value =
                        PayUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                AuthResult.TransportFailure -> _state.value = PayUiState.Failed(PayMapper.OFFLINE_KEY, true)
            }
        }
    }

    /**
     * Open the form for one fee.
     *
     * @param option The fee
     */
    fun choose(option: PayOption) {
        viewModelScope.launch { open(option) }
    }

    /** Go back to the list of fees, from the form. */
    fun change() {
        choosing?.let { _state.value = it }
    }

    /**
     * Change what has been typed.
     *
     * @param form The form as it now reads
     */
    fun type(form: PayForm) {
        _state.update { current ->
            (current as? PayUiState.Filling)?.copy(form = form, problem = PayMapper.claimOf(form).second)
                ?: current
        }
    }

    /** Send the payment for checking, if the form has the shape of one. */
    fun send() {
        val filling = _state.value as? PayUiState.Filling ?: return
        if (filling.sending) return
        val claim = PayMapper.claimOf(filling.form).first ?: return
        _state.value = filling.copy(sending = true, failedKey = null)
        viewModelScope.launch {
            _state.value =
                when (val result = repository.submit(filling.option.enrollmentId, claim)) {
                    is AuthResult.Ok ->
                        PayUiState.Sent(
                            filling.option,
                            PayMapper.sent(result.value, claim.transactionId.orEmpty()),
                            filling.destination?.teacherName,
                        )
                    is AuthResult.Refused -> filling.copy(failedKey = result.envelope.error.messageKey)
                    AuthResult.TransportFailure -> filling.copy(failedKey = PayMapper.OFFLINE_KEY)
                }
        }
    }

    /**
     * Read the destination and show the form.
     *
     * @param option The fee
     */
    private suspend fun open(option: PayOption) {
        val canChange = (choosing?.options?.size ?: 0) > 1 || choosing?.waiting?.isNotEmpty() == true
        _state.value =
            when (val result = repository.destination(option.enrollmentId)) {
                is AuthResult.Ok -> PayMapper.filling(option, result.value, canChange)
                is AuthResult.Refused ->
                    PayUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                AuthResult.TransportFailure -> PayUiState.Failed(PayMapper.OFFLINE_KEY, true)
            }
    }
}
