package com.shikkhokplus.app.feature.expenses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** How many characters of an ISO date make its month. */
private const val MONTH_LENGTH: Int = 7

/**
 * The current month in Dhaka, `YYYY-MM`.
 *
 * @return The month
 */
internal fun currentMonth(): String = dhakaTodayIso().take(MONTH_LENGTH)

/**
 * Holds the expense list: one month at a time, voiding an expense. Every
 * total is the server's; nothing here adds money [TC-9, D-31].
 *
 * @property repository The network
 * @property thisMonth Supplies the current month, overridden by tests
 */
class ExpensesViewModel(
    private val repository: ExpensesRepository,
    private val thisMonth: () -> String = ::currentMonth,
) : ViewModel() {

    private val _state = MutableStateFlow(ExpensesUiState(month = thisMonth(), canGoForward = false))

    /** What the screen renders. */
    val state: StateFlow<ExpensesUiState> = _state.asStateFlow()

    private var reading: Job? = null

    /** Read the month shown, again. */
    fun load() = show(_state.value.month)

    /** Read again after a failure, when the person asks. */
    fun retry() = load()

    /**
     * Move the month shown; never past the current month.
     *
     * @param by How many months, negative for earlier
     */
    fun shift(by: Long) {
        val target = shiftMonth(_state.value.month, by)
        if (target > thisMonth()) return
        show(target)
    }

    /**
     * Void an expense, then show the month as the server now has it.
     *
     * @param expenseId The expense
     * @param reason Why, or blank for none
     */
    fun void(expenseId: String, reason: String) {
        viewModelScope.launch {
            val why = reason.trim().take(EXPENSE_NOTE_MAX).ifBlank { null }
            when (val result = repository.void(expenseId, why)) {
                is AuthResult.Ok -> load()
                is AuthResult.Refused ->
                    _state.value = _state.value.copy(voidFailedKey = result.envelope.error.messageKey)
                AuthResult.TransportFailure -> _state.value = _state.value.copy(voidFailedKey = OFFLINE_KEY)
            }
        }
    }

    private fun show(month: String) {
        reading?.cancel()
        _state.value =
            ExpensesUiState(
                month = month,
                canGoForward = month < thisMonth(),
                body = ExpensesBody.Loading,
            )
        reading =
            viewModelScope.launch {
                val body =
                    when (val result = repository.month(month)) {
                        is AuthResult.Ok -> expensesBodyOf(result.value)
                        is AuthResult.Refused ->
                            ExpensesBody.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                        AuthResult.TransportFailure -> ExpensesBody.Failed(OFFLINE_KEY, retryable = true)
                    }
                _state.value = _state.value.copy(body = body)
            }
    }
}

/**
 * Holds the monthly summary. Every figure and the verdict are the
 * server's [TC-9, D-31].
 *
 * @property repository The network
 * @property thisMonth Supplies the current month, overridden by tests
 */
class SummaryViewModel(
    private val repository: ExpensesRepository,
    private val thisMonth: () -> String = ::currentMonth,
) : ViewModel() {

    private val _state = MutableStateFlow(SummaryUiState(month = thisMonth(), canGoForward = false))

    /** What the screen renders. */
    val state: StateFlow<SummaryUiState> = _state.asStateFlow()

    private var reading: Job? = null

    /** Read the month shown, again. */
    fun load() = show(_state.value.month)

    /** Read again after a failure, when the person asks. */
    fun retry() = load()

    /**
     * Move the month shown; never past the current month.
     *
     * @param by How many months, negative for earlier
     */
    fun shift(by: Long) {
        val target = shiftMonth(_state.value.month, by)
        if (target > thisMonth()) return
        show(target)
    }

    private fun show(month: String) {
        reading?.cancel()
        _state.value = SummaryUiState(month = month, canGoForward = month < thisMonth(), body = SummaryBody.Loading)
        reading =
            viewModelScope.launch {
                val body =
                    when (val result = repository.summary(month)) {
                        is AuthResult.Ok -> SummaryBody.Loaded(summaryOf(result.value))
                        is AuthResult.Refused ->
                            SummaryBody.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                        AuthResult.TransportFailure -> SummaryBody.Failed(OFFLINE_KEY, retryable = true)
                    }
                _state.value = _state.value.copy(body = body)
            }
    }
}
