package com.shikkhokplus.app.feature.paymentmethods

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** How many trailing digits of a bank account number the list shows. */
private const val VISIBLE_ACCOUNT_DIGITS: Int = 4

/**
 * Holds P1, the teacher's list of payment methods. Holds no business
 * logic [TC-9, D-31].
 *
 * @property repository The network
 */
class PaymentMethodsViewModel(
    private val repository: PaymentMethodsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<PaymentMethodsUiState>(PaymentMethodsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<PaymentMethodsUiState> = _state.asStateFlow()

    private var methods: List<PaymentMethodDto> = emptyList()

    /** Read the list. */
    fun load() {
        _state.value = PaymentMethodsUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /** Read the list again after a failure, when the person asks. */
    fun retry() = load()

    /**
     * Retire a method, then show the list as the server now has it.
     *
     * @param methodId The method to retire
     */
    fun retire(methodId: String) {
        viewModelScope.launch {
            when (val result = repository.retire(methodId)) {
                is AuthResult.Ok -> _state.value = read()
                is AuthResult.Refused -> keepWithFailure(result.envelope.error.messageKey)
                AuthResult.TransportFailure -> keepWithFailure(OFFLINE_KEY)
            }
        }
    }

    /**
     * Find a loaded method, for the editor to start from.
     *
     * @param methodId The method
     * @return The method, or null if it is not in the last read
     */
    fun methodFor(methodId: String): PaymentMethodDto? = methods.firstOrNull { it.methodId == methodId }

    private fun keepWithFailure(key: String) {
        val current = _state.value
        if (current is PaymentMethodsUiState.Loaded) {
            _state.value = current.copy(removeFailedKey = key)
        }
    }

    private suspend fun read(): PaymentMethodsUiState =
        when (val result = repository.list()) {
            is AuthResult.Ok -> {
                methods = result.value
                if (methods.isEmpty()) {
                    PaymentMethodsUiState.Empty
                } else {
                    PaymentMethodsUiState.Loaded(methods.map(::rowOf))
                }
            }
            is AuthResult.Refused ->
                PaymentMethodsUiState.Failed(
                    result.envelope.error.messageKey,
                    result.envelope.error.retryable,
                )
            AuthResult.TransportFailure -> PaymentMethodsUiState.Failed(OFFLINE_KEY, retryable = true)
        }

    private fun rowOf(method: PaymentMethodDto): MethodRow {
        val kind = MethodKind.fromWire(method.kind)
        return when (kind) {
            MethodKind.MOBILE ->
                MethodRow(
                    methodId = method.methodId,
                    kind = kind,
                    title = method.provider.orEmpty(),
                    detail = method.mobileNumber.orEmpty(),
                    extra = null,
                    note = method.note?.takeIf { it.isNotBlank() },
                )
            MethodKind.BANK -> {
                val lastDigits = method.accountNumber.orEmpty().takeLast(VISIBLE_ACCOUNT_DIGITS)
                MethodRow(
                    methodId = method.methodId,
                    kind = kind,
                    title = method.provider.orEmpty(),
                    detail = "${method.accountName.orEmpty()} · ••• $lastDigits",
                    extra = method.branchName?.takeIf { it.isNotBlank() },
                    note = method.note?.takeIf { it.isNotBlank() },
                )
            }
        }
    }
}
