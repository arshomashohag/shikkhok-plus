package com.shikkhokplus.app.feature.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.DashboardDto
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.fees.StripKind
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds the progress dashboard for all three readers.
 *
 * Holds no business logic [TC-9, D-31]: every figure, percent, state
 * and direction is the server's, and switching a range, child or batch
 * asks the server again.
 */
class DashboardViewModel(
    private val repository: DashboardRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<DashboardUiState>(DashboardUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<DashboardUiState> = _state.asStateFlow()

    private var reader: DashboardReader = DashboardReader.STUDENT

    private var seat: String = ""

    private var heading: String = ""

    private var subheading: String = ""

    private var range: DashboardRange = DashboardRange.SIX_MONTHS

    private var children: List<DashboardChild> = emptyList()

    private var reading: Job? = null

    /**
     * Read a seat's dashboard.
     *
     * @param reader Who is reading
     * @param seat The seat
     * @param heading Whose progress, for a reader who is not a guardian
     * @param subheading Which batch, for a reader who is not a guardian
     */
    fun load(
        reader: DashboardReader,
        seat: String,
        heading: String = "",
        subheading: String = "",
    ) {
        this.reader = reader
        this.seat = seat
        this.heading = heading
        this.subheading = subheading
        this.range = DashboardRange.SIX_MONTHS
        this.children = emptyList()
        _state.value = DashboardUiState.Loading
        reading?.cancel()
        reading = viewModelScope.launch {
            if (reader == DashboardReader.GUARDIAN && !readChildren()) return@launch
            fetch()
        }
    }

    /**
     * Show another range.
     *
     * @param range The range chip tapped
     */
    fun selectRange(range: DashboardRange) {
        if (range == this.range) return
        this.range = range
        refetch()
    }

    /**
     * Show another of the guardian's children, on their first batch.
     *
     * @param key The child's key
     */
    fun selectChild(key: String) {
        val child = children.firstOrNull { it.key == key } ?: return
        val first = child.batches.firstOrNull() ?: return
        if (first.seat == seat) return
        seat = first.seat
        refetch()
    }

    /**
     * Show another batch of the same child.
     *
     * @param seat The seat in that batch
     */
    fun selectBatch(seat: String) {
        if (seat == this.seat) return
        this.seat = seat
        refetch()
    }

    /** Read again, when the person asks. Never automatic [TC-8, D-9]. */
    fun retry() {
        _state.value = DashboardUiState.Loading
        reading?.cancel()
        reading = viewModelScope.launch { fetch() }
    }

    private fun refetch() {
        (_state.value as? DashboardUiState.Loaded)?.let { _state.value = it.copy(refreshing = true) }
        reading?.cancel()
        reading = viewModelScope.launch { fetch() }
    }

    private suspend fun readChildren(): Boolean {
        when (val home = repository.children()) {
            is AuthResult.Ok -> children = childrenOf(home.value)
            else -> {
                _state.value = failure(home)
                return false
            }
        }
        if (children.none { child -> child.batches.any { it.seat == seat } }) {
            _state.value = DashboardUiState.Failed(NOT_AVAILABLE_KEY, retryable = false)
            return false
        }
        return true
    }

    private fun childrenOf(home: GuardianHomeDto): List<DashboardChild> =
        home.children.map { child ->
            val batches = child.batches.map { DashboardBatch(it.enrollmentId, it.batchName) }
            DashboardChild(child.key, child.displayName, batches)
        }

    private suspend fun fetch() {
        _state.value =
            when (val result = repository.dashboard(reader, seat, range)) {
                is AuthResult.Ok -> loaded(result.value)
                else -> failure(result)
            }
    }

    private fun loaded(dto: DashboardDto): DashboardUiState.Loaded {
        val child = children.firstOrNull { c -> c.batches.any { it.seat == seat } }
        return DashboardUiState.Loaded(
            reader = reader,
            heading = child?.name ?: heading,
            subheading = child?.batches?.firstOrNull { it.seat == seat }?.name ?: subheading,
            range = range,
            children = children,
            selectedChild = child?.key,
            batches = child?.batches.orEmpty(),
            seat = seat,
            attendancePercent = dto.tiles.attendancePercent,
            present = dto.tiles.present,
            held = dto.tiles.held,
            examAveragePercent = dto.tiles.examAveragePercent,
            direction = directionOf(dto.tiles.direction),
            owed = dto.tiles.owed,
            attendance = dto.attendanceByMonth,
            exams = dto.exams,
            feeMonths =
                dto.feeMonths.mapNotNull { month ->
                    kindOf(month.state)?.let { DashboardFeeMonth(month.period, it) }
                },
        )
    }

    private fun directionOf(wire: String?): DashboardDirection? =
        when (wire) {
            "up" -> DashboardDirection.UP
            "down" -> DashboardDirection.DOWN
            "same" -> DashboardDirection.SAME
            else -> null
        }

    private fun kindOf(state: String): StripKind? =
        when (state) {
            "paid" -> StripKind.PAID
            "partly_paid" -> StripKind.PARTIAL
            "unpaid" -> StripKind.UNPAID
            "waived" -> StripKind.WAIVED
            "checking" -> StripKind.CHECKING
            else -> null
        }

    private fun failure(result: AuthResult<*>): DashboardUiState =
        when (result) {
            is AuthResult.Refused ->
                DashboardUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            else -> DashboardUiState.Failed(OFFLINE_KEY, retryable = true)
        }

    private companion object {
        const val OFFLINE_KEY = "error.network.unreachable"
        const val NOT_AVAILABLE_KEY = "error.not_available"
    }
}
