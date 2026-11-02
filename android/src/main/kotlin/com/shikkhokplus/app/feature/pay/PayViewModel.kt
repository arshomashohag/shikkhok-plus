package com.shikkhokplus.app.feature.pay

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.network.FamilyPaymentMethodsDto
import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.PaymentSubmitDto
import com.shikkhokplus.app.core.network.PaymentSubmittedDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/** What sending money needs from the network. */
interface PayRepository {
    /**
     * Read the accepted seats the payer may pay for.
     *
     * @return One row per accepted seat
     */
    suspend fun seats(): AuthResult<List<StudentBatchDto>>

    /**
     * Read the methods the seat's teacher accepts.
     *
     * @param enrollmentId Any seat in the batch
     * @return The methods and suggestions
     */
    suspend fun methods(enrollmentId: String): AuthResult<FamilyPaymentMethodsDto>

    /**
     * Read what the chosen children owe together.
     *
     * @param enrollmentIds The chosen seats
     * @return The server's owed figures
     */
    suspend fun owed(enrollmentIds: List<String>): AuthResult<OwedTogetherDto>

    /**
     * Record a payment for the teacher to check.
     *
     * @param payment What was paid
     * @return The recorded payment
     */
    suspend fun submit(payment: PaymentSubmitDto): AuthResult<PaymentSubmittedDto>
}

/**
 * Holds the "Send money" flow: choose how, fill in, send, sent.
 *
 * **Never queued.** A payment write needs a connection [TC-8, D-9]; a
 * failed send keeps what was typed and asks the payer to send again.
 * Money figures are the server's: the owed line and the suggested
 * amount are read, never summed here [TC-9].
 *
 * @property repository The network
 * @property today Bangladesh's current date, `yyyy-MM-dd`
 * @property newMutationId Generates a payment's replay key; injectable
 *   so a test can assert which key a send carried
 */
class PayViewModel(
    private val repository: PayRepository,
    private val today: () -> String = ::dhakaTodayIso,
    private val newMutationId: () -> String = { UUID.randomUUID().toString() },
) : ViewModel() {

    private val _state = MutableStateFlow<PayUiState>(PayUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<PayUiState> = _state.asStateFlow()

    private var batches: List<PayBatch> = emptyList()

    /**
     * Read the seats and open on the batch holding [preselect].
     *
     * @param preselect A seat to start on, or null
     */
    fun load(preselect: String? = null) {
        _state.value = PayUiState.Loading
        viewModelScope.launch {
            when (val result = repository.seats()) {
                is AuthResult.Ok -> {
                    batches = PayMapper.batches(result.value)
                    val first =
                        batches.firstOrNull { batch -> batch.seats.any { it.enrollmentId == preselect } }
                            ?: batches.firstOrNull()
                    if (first == null) {
                        _state.value = PayUiState.NoSeats
                    } else {
                        openMethods(first, PayMapper.initialSelection(first, preselect))
                    }
                }
                is AuthResult.Refused -> _state.value = failed(result)
                AuthResult.TransportFailure -> _state.value = PayUiState.Failed(PayMapper.OFFLINE_KEY, true)
            }
        }
    }

    /**
     * Pick another batch. Keeps the way of paying when the new batch's
     * teacher offers the same method; otherwise asks again.
     *
     * @param key The batch
     */
    fun chooseBatch(key: String) {
        val batch = batches.firstOrNull { it.key == key } ?: return
        val current = _state.value
        val previous = (current as? PayUiState.Filling)
        if (current is PayUiState.Methods && current.scope.batch.key == key) return
        if (previous != null && previous.scope.batch.key == key) return
        viewModelScope.launch {
            val selected = PayMapper.initialSelection(batch, null)
            val scope = scopeFor(batch, selected) ?: return@launch
            val choice = (previous?.choice as? PayChoice.Method)?.method
            val same = scope.methods.firstOrNull { it.methodId == choice?.methodId }
            when {
                previous != null && same != null -> {
                    _state.value = previous.copy(scope = scope, choice = PayChoice.Method(same), owed = null)
                    refreshOwed()
                }
                previous != null && previous.choice is PayChoice.Cash -> {
                    _state.value = previous.copy(scope = scope, owed = null)
                    refreshOwed()
                }
                else -> _state.value = PayUiState.Methods(scope)
            }
        }
    }

    /**
     * Choose where the money went and open its form.
     *
     * @param choice A listed method, or cash
     */
    fun choose(choice: PayChoice) {
        val methods = _state.value as? PayUiState.Methods ?: return
        _state.value = PayUiState.Filling(methods.scope, choice, null, PayForm(paidOn = today()))
        viewModelScope.launch { refreshOwed() }
    }

    /** Go back to the list of methods, from a form. */
    fun back() {
        (_state.value as? PayUiState.Filling)?.let { _state.value = PayUiState.Methods(it.scope) }
    }

    /**
     * Add or drop a child from the payment. At least one child stays.
     *
     * @param enrollmentId The child's seat
     */
    fun toggleChild(enrollmentId: String) {
        val filling = _state.value as? PayUiState.Filling ?: return
        val selected = filling.scope.selected
        val inBatch = filling.scope.batch.seats.map { it.enrollmentId }
        val next =
            if (enrollmentId in selected) {
                selected - enrollmentId
            } else {
                inBatch.filter { it in selected || it == enrollmentId }
            }
        if (next.isEmpty()) return
        _state.value = filling.copy(scope = filling.scope.copy(selected = next), owed = null)
        viewModelScope.launch { refreshOwed() }
    }

    /**
     * Change what has been typed.
     *
     * @param form The form as it now reads
     */
    fun type(form: PayForm) {
        _state.update { current ->
            if (current !is PayUiState.Filling) return@update current
            val next = current.copy(form = form)
            next.copy(problem = PayMapper.requestOf(next).second)
        }
    }

    /**
     * Send the payment for checking, if the form has the shape of one.
     *
     * The payment carries its attempt's replay key, and the attempt is
     * kept in the state through a failure: tapping Send again on the
     * same payment re-sends the same key, which is what lets the server
     * recognise a send that timed out after it was recorded. A replayed
     * send is answered with the original submission, as a success.
     */
    fun send() {
        val filling = _state.value as? PayUiState.Filling ?: return
        if (filling.sending) return
        val payment = PayMapper.requestOf(filling).first ?: return
        val attempt = PayMapper.attemptFor(filling.attempt, payment, newMutationId)
        val sending = filling.copy(sending = true, failedKey = null, attempt = attempt)
        _state.value = sending
        viewModelScope.launch {
            _state.value =
                when (val result = repository.submit(attempt.request)) {
                    is AuthResult.Ok ->
                        PayUiState.Sent(
                            filling.scope.batch.name,
                            filling.scope.teacherName,
                            filling.choice,
                            result.value,
                            payment.transactionId ?: payment.fromAccount,
                        )
                    is AuthResult.Refused ->
                        sending.copy(sending = false, failedKey = result.envelope.error.messageKey)
                    AuthResult.TransportFailure -> sending.copy(sending = false, failedKey = PayMapper.OFFLINE_KEY)
                }
        }
    }

    private suspend fun openMethods(batch: PayBatch, selected: List<String>) {
        _state.value = scopeFor(batch, selected)?.let { PayUiState.Methods(it) } ?: _state.value
    }

    private suspend fun scopeFor(batch: PayBatch, selected: List<String>): PayScope? =
        when (val result = repository.methods(batch.seats.first().enrollmentId)) {
            is AuthResult.Ok ->
                PayScope(batches, batch, selected, result.value.methods, result.value.teacherDisplayName)
            is AuthResult.Refused -> {
                _state.value = failed(result)
                null
            }
            AuthResult.TransportFailure -> {
                _state.value = PayUiState.Failed(PayMapper.OFFLINE_KEY, true)
                null
            }
        }

    private suspend fun refreshOwed() {
        val asked = (_state.value as? PayUiState.Filling)?.scope?.selected ?: return
        val owed = (repository.owed(asked) as? AuthResult.Ok)?.value ?: return
        _state.update { current ->
            if (current !is PayUiState.Filling || current.scope.selected != asked) return@update current
            val previous = current.owed?.owedTogether?.toString()
            val replace = current.form.amount.isBlank() || current.form.amount == previous
            val suggested = owed.owedTogether.takeIf { it.amount.signum() > 0 }?.toString().orEmpty()
            current.copy(
                owed = owed,
                form = if (replace) current.form.copy(amount = suggested) else current.form,
            )
        }
    }

    private fun failed(refused: AuthResult.Refused): PayUiState.Failed =
        PayUiState.Failed(refused.envelope.error.messageKey, refused.envelope.error.retryable)
}
