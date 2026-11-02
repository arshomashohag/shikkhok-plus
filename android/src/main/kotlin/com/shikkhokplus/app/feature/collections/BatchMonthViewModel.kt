package com.shikkhokplus.app.feature.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.network.BatchFeesDto
import com.shikkhokplus.app.core.network.toHistoryLine
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds one batch's month screen. Holds no business logic [TC-9, D-31].
 *
 * The month switcher asks the server for the month it names; the
 * filter counts are the server's own. The phone only chooses which
 * already-decided rows to show under the open filter.
 */
class BatchMonthViewModel(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<BatchMonthUiState>(BatchMonthUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<BatchMonthUiState> = _state.asStateFlow()

    private var batchId: String = ""

    private var requested: String? = null

    private var currentPeriod: String? = null

    private var filter: MonthFilter = MonthFilter.ALL

    private var allSeats: List<MonthSeat> = emptyList()

    /**
     * Load a batch, in a month or in the server's current one.
     *
     * @param batchId The batch
     * @param period `YYYY-MM`, or null for the current month
     */
    fun load(
        batchId: String,
        period: String? = null,
    ) {
        this.batchId = batchId
        this.requested = period
        this.currentPeriod = null
        fetch()
    }

    /** Retry, when the person asks. Never automatic [TC-8, D-9]. */
    fun retry() {
        fetch()
    }

    /** Show the month before the one in view. */
    fun previous() {
        shift(-1)
    }

    /** Show the month after the one in view, if one exists. */
    fun next() {
        val loaded = _state.value as? BatchMonthUiState.Loaded ?: return
        if (loaded.canGoNext) shift(1)
    }

    /**
     * Narrow the seats to one filter.
     *
     * @param filter The filter
     */
    fun filter(filter: MonthFilter) {
        this.filter = filter
        val loaded = _state.value as? BatchMonthUiState.Loaded ?: return
        _state.value = loaded.copy(filter = filter, seats = visible(filter))
    }

    private fun shift(by: Long) {
        val loaded = _state.value as? BatchMonthUiState.Loaded ?: return
        val moved = YearMonth.parseOrNull(loaded.period)?.plusMonths(by) ?: return
        requested = moved.toString()
        fetch()
    }

    private fun fetch() {
        _state.value = BatchMonthUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.batchMonth(batchId, requested)) {
                    is AuthResult.Ok -> loaded(result.value)
                    is AuthResult.Refused ->
                        BatchMonthUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                    AuthResult.TransportFailure -> BatchMonthUiState.Failed(OFFLINE_KEY, retryable = true)
                }
        }
    }

    private fun loaded(dto: BatchFeesDto): BatchMonthUiState.Loaded {
        if (requested == null) currentPeriod = dto.period
        allSeats = dto.seats.map(::seat)
        return BatchMonthUiState.Loaded(
            period = dto.period,
            collected = dto.collected,
            charged = dto.charged,
            counts = SeatCounts(dto.counts.paid, dto.counts.checking, dto.counts.owed),
            filter = filter,
            seats = visible(filter),
            canGoNext = dto.period < (currentPeriod ?: dhakaTodayIso().take(PERIOD_LENGTH)),
        )
    }

    private fun visible(filter: MonthFilter): List<MonthSeat> =
        allSeats.filter { filter == MonthFilter.ALL || filterOf(it.kind) == filter }

    private fun filterOf(kind: SeatKind): MonthFilter? =
        when (kind) {
            SeatKind.PAID, SeatKind.WAIVED -> MonthFilter.PAID
            SeatKind.CHECKING -> MonthFilter.CHECKING
            SeatKind.PARTIAL, SeatKind.DUE, SeatKind.OVERDUE -> MonthFilter.OWED
            SeatKind.NONE -> null
        }

    private fun seat(row: RosterFeeRowDto): MonthSeat =
        MonthSeat(
            enrollmentId = row.enrollmentId,
            displayName = row.displayName,
            kind = kindOf(row),
            outstanding = row.outstanding,
            daysOverdue = row.daysOverdue,
            verifying = row.verifying,
            historyLine = row.historyLine?.toHistoryLine(),
        )

    private fun kindOf(row: RosterFeeRowDto): SeatKind =
        when (row.state) {
            "paid" -> SeatKind.PAID
            "waived" -> SeatKind.WAIVED
            "partly_paid" -> SeatKind.PARTIAL
            "checking" -> SeatKind.CHECKING
            "unpaid" -> if (row.daysOverdue != null) SeatKind.OVERDUE else SeatKind.DUE
            else -> SeatKind.NONE
        }

    private companion object {
        const val OFFLINE_KEY: String = "error.network.unreachable"
        const val PERIOD_LENGTH: Int = 7
    }
}
