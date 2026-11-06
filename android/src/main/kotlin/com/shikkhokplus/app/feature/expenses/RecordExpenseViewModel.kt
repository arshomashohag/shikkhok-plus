package com.shikkhokplus.app.feature.expenses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Holds the record-an-expense form.
 *
 * **One retry key per opened form.** A save that timed out may have been
 * stored; sending again under the same key is a replay the server
 * answers with the stored expense, never a second one.
 *
 * Validation here is format only: a description and an amount that
 * parses. Whether the amount is above zero or the date is not in the
 * future is the server's to refuse, in the person's language.
 *
 * @property repository The network
 * @param today The default date, overridden by tests
 * @param mutationId The retry key, overridden by tests
 */
class RecordExpenseViewModel(
    private val repository: ExpensesRepository,
    today: String = dhakaTodayIso(),
    private val mutationId: String = UUID.randomUUID().toString(),
) : ViewModel() {

    private val _state = MutableStateFlow(RecordExpenseUiState(spentOn = today))

    /** What the form renders. */
    val state: StateFlow<RecordExpenseUiState> = _state.asStateFlow()

    /**
     * Choose what it was spent on.
     *
     * @param category The category
     */
    fun category(category: ExpenseCategory) = _state.update { it.copy(category = category, failureKey = null) }

    /**
     * Say what it was.
     *
     * @param text The description
     */
    fun what(text: String) = _state.update { it.copy(what = text.take(EXPENSE_WHAT_MAX), failureKey = null) }

    /**
     * Type the amount.
     *
     * @param text The amount as typed
     */
    fun amount(text: String) = _state.update { it.copy(typedAmount = text, failureKey = null) }

    /**
     * Pick the day it was paid.
     *
     * @param isoDate `yyyy-MM-dd`
     */
    fun spentOn(isoDate: String) = _state.update { it.copy(spentOn = isoDate, failureKey = null) }

    /**
     * Say who was paid.
     *
     * @param text The payee
     */
    fun payee(text: String) = _state.update { it.copy(payee = text.take(EXPENSE_PAYEE_MAX), failureKey = null) }

    /**
     * Add a note or receipt number.
     *
     * @param text The note
     */
    fun note(text: String) = _state.update { it.copy(note = text.take(EXPENSE_NOTE_MAX), failureKey = null) }

    /** Send the form, when it can be sent. */
    fun save() {
        val form = _state.value
        if (!form.canSave) return
        val amount = Money.fromTyped(form.typedAmount) ?: return
        val draft =
            ExpenseDraft(
                category = form.category,
                what = form.what.trim(),
                amount = amount,
                spentOn = form.spentOn,
                payee = form.payee.trim().ifBlank { null },
                note = form.note.trim().ifBlank { null },
                clientMutationId = mutationId,
            )
        _state.update { it.copy(saving = true, failureKey = null) }
        viewModelScope.launch {
            when (val result = repository.record(draft)) {
                is AuthResult.Ok -> _state.update { it.copy(saving = false, saved = true) }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }
}
