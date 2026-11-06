package com.shikkhokplus.app.feature.payroll

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.AdjustmentBodyDto
import com.shikkhokplus.app.core.network.SalaryLineDto
import com.shikkhokplus.app.core.network.SalaryPaymentBodyDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.expenses.currentMonth
import com.shikkhokplus.app.feature.expenses.shiftMonth
import com.shikkhokplus.app.feature.myexams.Loadable
import com.shikkhokplus.app.feature.timetable.OFFLINE_KEY
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/** The kind of an adjustment that adds to the salary. */
const val ADDITION: String = "addition"

/** The kind of an adjustment that takes from the salary. */
const val DEDUCTION: String = "deduction"

/** The longest adjustment label the server accepts. */
private const val LABEL_MAX: Int = 80

/** The longest payment note the server accepts. */
private const val NOTE_MAX: Int = 200

/** The sheet open over the payroll. */
sealed interface PayrollSheet {
    /** The line it is about. */
    val lineId: String

    /**
     * Adding a bonus or deduction.
     *
     * @property lineId The line
     * @property kind [ADDITION] or [DEDUCTION]
     * @property label What it is for, as typed
     * @property amount How much, as typed
     */
    data class Adjust(
        override val lineId: String,
        val kind: String = ADDITION,
        val label: String = "",
        val amount: String = "",
    ) : PayrollSheet {
        /** The body to send, or null while it cannot be sent. */
        val body: AdjustmentBodyDto?
            get() {
                val money = Money.fromTyped(amount)?.takeIf { it.amount.signum() > 0 } ?: return null
                val trimmed = label.trim().takeIf { it.isNotEmpty() } ?: return null
                return AdjustmentBodyDto(kind, trimmed.take(LABEL_MAX), money)
            }
    }

    /**
     * Recording a payment.
     *
     * @property lineId The line
     * @property amount How much, as typed; starts at what is left
     * @property paidOn When, `yyyy-MM-dd`, or blank for today
     * @property note A short note, as typed
     * @property mutationId The replay key, kept across a failed send
     */
    data class Pay(
        override val lineId: String,
        val amount: String,
        val paidOn: String = "",
        val note: String = "",
        val mutationId: String,
    ) : PayrollSheet {
        /** The body to send, or null while it cannot be sent. */
        val body: SalaryPaymentBodyDto?
            get() {
                val money = Money.fromTyped(amount)?.takeIf { it.amount.signum() > 0 } ?: return null
                return SalaryPaymentBodyDto(
                    amount = money,
                    clientMutationId = mutationId,
                    paidOn = paidOn.trim().ifEmpty { null },
                    note = note.trim().ifEmpty { null },
                )
            }
    }
}

/**
 * A centre's payroll for one month.
 *
 * @property month The month, `yyyy-MM`
 * @property lines The month's lines
 * @property sheet The sheet open, or null
 * @property saving Whether a write is in flight
 * @property failureKey Message key for the last refusal, or null
 * @property saved Whether the last write was saved
 */
data class PayrollUiState(
    val month: String,
    val lines: Loadable<List<SalaryLineDto>> = Loadable.Loading,
    val sheet: PayrollSheet? = null,
    val saving: Boolean = false,
    val failureKey: String? = null,
    val saved: Boolean = false,
) {
    /** False on the current month: there is no payroll ahead of it. */
    val canGoForward: Boolean get() = month < currentMonth()

    /** The line the open sheet is about, or null. */
    val sheetLine: SalaryLineDto?
        get() = sheet?.let { s -> (lines as? Loadable.Loaded)?.value?.firstOrNull { it.lineId == s.lineId } }
}

/**
 * Holds a centre's payroll a month at a time: draw the lines from the
 * staff records, add bonuses and deductions to drafts, approve, and
 * record payments. Every figure and every refusal is the server's.
 *
 * @property repository The network
 * @property newMutationId Makes a replay key, overridden by tests
 * @param month The first month shown, overridden by tests
 */
class PayrollViewModel(
    private val repository: PayrollRepository,
    month: String = currentMonth(),
    private val newMutationId: () -> String = { UUID.randomUUID().toString() },
) : ViewModel() {

    private val _state = MutableStateFlow(PayrollUiState(month = month))

    /** What the screen renders. */
    val state: StateFlow<PayrollUiState> = _state.asStateFlow()

    /** Read the month. */
    fun load() {
        val month = _state.value.month
        viewModelScope.launch {
            val lines = Loadable.of(repository.month(month))
            _state.update { if (it.month == month) it.copy(lines = lines) else it }
        }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.update { it.copy(lines = Loadable.Loading) }
        load()
    }

    /**
     * Move a month; never past the current one.
     *
     * @param by How many months, negative for earlier
     */
    fun shift(by: Long) {
        val next = shiftMonth(_state.value.month, by)
        if (next > currentMonth()) return
        _state.update { PayrollUiState(month = next) }
        load()
    }

    /** Draw the month's lines from the staff records. */
    fun draw() = writeMonth { repository.draw(it) }

    /**
     * Approve a draft line.
     *
     * @param lineId The line
     */
    fun approve(lineId: String) = writeLine { repository.approve(lineId) }

    /**
     * Remove a bonus or deduction from a draft line.
     *
     * @param lineId The line
     * @param adjustmentId The adjustment
     */
    fun removeAdjustment(lineId: String, adjustmentId: String) =
        writeLine { repository.removeAdjustment(lineId, adjustmentId) }

    /**
     * Open the adjustment sheet for a draft line.
     *
     * @param lineId The line
     */
    fun openAdjust(lineId: String) = open(PayrollSheet.Adjust(lineId))

    /**
     * Open the payment sheet for an approved line, starting at what is left.
     *
     * @param lineId The line
     */
    fun openPay(lineId: String) {
        val line = (_state.value.lines as? Loadable.Loaded)?.value?.firstOrNull { it.lineId == lineId } ?: return
        open(PayrollSheet.Pay(lineId, amount = line.remaining.toString(), mutationId = newMutationId()))
    }

    /** Close the sheet. */
    fun close() = _state.update { it.copy(sheet = null, failureKey = null) }

    private fun edit(change: (PayrollSheet) -> PayrollSheet) =
        _state.update { it.copy(sheet = it.sheet?.let(change), failureKey = null) }

    /**
     * Type into the adjustment sheet.
     *
     * @param kind [ADDITION] or [DEDUCTION], or null to keep it
     * @param label The label, or null to keep it
     * @param amount The amount, or null to keep it
     */
    fun adjustment(kind: String? = null, label: String? = null, amount: String? = null) =
        edit { sheet ->
            (sheet as? PayrollSheet.Adjust)?.let {
                it.copy(
                    kind = kind?.takeIf { k -> k == ADDITION || k == DEDUCTION } ?: it.kind,
                    label = label?.take(LABEL_MAX) ?: it.label,
                    amount = amount ?: it.amount,
                )
            } ?: sheet
        }

    /**
     * Type into the payment sheet.
     *
     * @param amount The amount, or null to keep it
     * @param paidOn The date, or null to keep it
     * @param note The note, or null to keep it
     */
    fun payment(amount: String? = null, paidOn: String? = null, note: String? = null) =
        edit { sheet ->
            (sheet as? PayrollSheet.Pay)?.let {
                it.copy(
                    amount = amount ?: it.amount,
                    paidOn = paidOn ?: it.paidOn,
                    note = note?.take(NOTE_MAX) ?: it.note,
                )
            } ?: sheet
        }

    /** Send the open sheet. */
    fun submit() {
        when (val sheet = _state.value.sheet) {
            is PayrollSheet.Adjust -> sheet.body?.let { body -> writeLine { repository.adjust(sheet.lineId, body) } }
            is PayrollSheet.Pay -> sheet.body?.let { body -> writeLine { repository.pay(sheet.lineId, body) } }
            null -> Unit
        }
    }

    private fun open(sheet: PayrollSheet) = _state.update { it.copy(sheet = sheet, failureKey = null, saved = false) }

    private fun writeLine(send: suspend () -> AuthResult<SalaryLineDto>) =
        write(send) { lines, line -> lines.map { if (it.lineId == line.lineId) line else it } }

    private fun writeMonth(send: suspend (String) -> AuthResult<List<SalaryLineDto>>) {
        val month = _state.value.month
        write({ send(month) }) { _, lines -> lines }
    }

    private fun <T> write(send: suspend () -> AuthResult<T>, merge: (List<SalaryLineDto>, T) -> List<SalaryLineDto>) {
        if (_state.value.saving) return
        _state.update { it.copy(saving = true, failureKey = null, saved = false) }
        viewModelScope.launch {
            when (val result = send()) {
                is AuthResult.Ok ->
                    _state.update {
                        val current = (it.lines as? Loadable.Loaded)?.value.orEmpty()
                        it.copy(
                            lines = Loadable.Loaded(merge(current, result.value)),
                            sheet = null,
                            saving = false,
                            saved = true,
                        )
                    }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }
}

/**
 * Holds my own pay: approved salary lines at every centre, read-only.
 *
 * @property repository The network
 */
class MyPayViewModel(
    private val repository: PayrollRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<Loadable<List<SalaryLineDto>>>(Loadable.Loading)

    /** What the screen renders. */
    val state: StateFlow<Loadable<List<SalaryLineDto>>> = _state.asStateFlow()

    /** Read my pay. */
    fun load() {
        viewModelScope.launch { _state.value = Loadable.of(repository.myPay()) }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.value = Loadable.Loading
        load()
    }
}
