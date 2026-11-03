package com.shikkhokplus.app.feature.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.BatchFeesDto
import com.shikkhokplus.app.core.network.CollectionsDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** How many months the chart shows. */
const val COLLECTIONS_MONTHS: Int = 6

/**
 * Holds the collections screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Choosing a batch chip asks the server again with the chosen ids; the
 * phone never filters or adds up the figures itself.
 */
class CollectionsViewModel(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<CollectionsUiState>(CollectionsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<CollectionsUiState> = _state.asStateFlow()

    private var batches: List<BatchDto>? = null

    private var selected: List<String> = emptyList()

    private var chosenPeriod: String? = null

    /** Load, or load again after a failure. */
    fun load() {
        _state.value = CollectionsUiState.Loading
        viewModelScope.launch { _state.value = read() }
    }

    /** Retry, when the person asks. Never automatic [TC-8, D-9]. */
    fun retry() {
        load()
    }

    /**
     * Add a batch to, or take it out of, the narrowing, and ask again.
     *
     * @param batchId The batch whose chip was tapped
     */
    fun toggle(batchId: String) {
        selected = if (batchId in selected) selected - batchId else selected + batchId
        (_state.value as? CollectionsUiState.Loaded)?.let { loaded ->
            _state.value = loaded.copy(batches = chips(batches.orEmpty()))
        }
        viewModelScope.launch { _state.value = read() }
    }

    /** Drop the narrowing, so the report covers every batch again. */
    fun showAll() {
        if (selected.isEmpty()) return
        selected = emptyList()
        (_state.value as? CollectionsUiState.Loaded)?.let { loaded ->
            _state.value = loaded.copy(batches = chips(batches.orEmpty()))
        }
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Make a month the one the tiles and batch rows describe.
     *
     * @param period `YYYY-MM`, as the chart's own bar names it
     */
    fun selectMonth(period: String) {
        chosenPeriod = period
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Read one batch's row again, leaving the chart, tiles and other
     * rows as they are.
     *
     * @param batchId The batch whose row failed
     */
    fun retryBatch(batchId: String) {
        val loaded = _state.value as? CollectionsUiState.Loaded ?: return
        val period = loaded.headlinePeriod ?: return
        val batch = batches?.firstOrNull { it.id == batchId } ?: return
        viewModelScope.launch {
            val fresh = rowFor(batch, period)
            (_state.value as? CollectionsUiState.Loaded)?.let { now ->
                _state.value = now.copy(batchRows = now.batchRows.map { if (it.batchId == batchId) fresh else it })
            }
        }
    }

    private suspend fun read(): CollectionsUiState =
        try {
            val all = batches ?: repository.batches().value().also { batches = it }
            val report = repository.collections(selected, COLLECTIONS_MONTHS).value()
            val headline =
                report.months.firstOrNull { it.period == chosenPeriod }
                    ?: report.months.lastOrNull { !it.inProgress }
                    ?: report.months.lastOrNull()
            val inView = all.filter { selected.isEmpty() || it.id in selected }
            val rows =
                headline?.let { month ->
                    coroutineScope { inView.map { batch -> async { rowFor(batch, month.period) } }.awaitAll() }
                }.orEmpty()
            loaded(all, report, headline?.period, rows)
        } catch (stop: Stopped) {
            stop.state
        }

    private suspend fun rowFor(
        batch: BatchDto,
        period: String,
    ): BatchRowItem =
        when (val result = repository.batchMonth(batch.id, period)) {
            is AuthResult.Ok -> row(batch, result.value)
            is AuthResult.Refused ->
                BatchRowFailed(batch.id, batch.name, result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> BatchRowFailed(batch.id, batch.name, OFFLINE_KEY, retryable = true)
        }

    private fun <T> AuthResult<T>.value(): T =
        when (this) {
            is AuthResult.Ok -> value
            is AuthResult.Refused -> throw Stopped(failed(envelope))
            AuthResult.TransportFailure -> throw Stopped(offline())
        }

    private class Stopped(val state: CollectionsUiState) : Exception()

    private fun loaded(
        all: List<BatchDto>,
        report: CollectionsDto,
        headlinePeriod: String?,
        rows: List<BatchRowItem>,
    ): CollectionsUiState.Loaded {
        val headline = report.months.firstOrNull { it.period == headlinePeriod }
        return CollectionsUiState.Loaded(
            batches = chips(all),
            months =
                report.months.map {
                    MonthBar(it.period, it.charged, it.collected, it.chargedBar, it.collectedBar, it.inProgress)
                },
            headlinePeriod = headlinePeriod,
            headlineCollected = headline?.collected,
            headlineCharged = headline?.charged,
            outstanding = report.outstanding,
            owingStudents = report.owingStudents,
            batchRows = rows,
        )
    }

    private fun chips(all: List<BatchDto>): List<BatchChip> =
        all.map { BatchChip(it.id, it.name, it.id in selected) }

    private fun row(
        batch: BatchDto,
        month: BatchFeesDto,
    ): BatchMonthRow =
        BatchMonthRow(
            batchId = batch.id,
            name = batch.name,
            period = month.period,
            collected = month.collected,
            charged = month.charged,
            counts = SeatCounts(month.counts.paid, month.counts.checking, month.counts.owed),
        )

    private fun failed(envelope: ErrorEnvelope): CollectionsUiState =
        CollectionsUiState.Failed(envelope.error.messageKey, envelope.error.retryable)

    private fun offline(): CollectionsUiState = CollectionsUiState.Failed(OFFLINE_KEY, retryable = true)

    private companion object {
        const val OFFLINE_KEY: String = "error.network.unreachable"
    }
}
