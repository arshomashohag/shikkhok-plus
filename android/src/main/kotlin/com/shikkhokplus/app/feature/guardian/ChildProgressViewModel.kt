package com.shikkhokplus.app.feature.guardian

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.ProgressSummaryDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** What G2 needs from the network. */
interface ChildProgressRepository {
    /**
     * Read the guardian's children, to find the child's batches.
     *
     * @return The children, or a failure
     */
    suspend fun home(): AuthResult<GuardianHomeDto>

    /**
     * Read one seat's results, oldest first.
     *
     * @param seat The seat
     * @return The results, or a failure
     */
    suspend fun progress(seat: String): AuthResult<List<ProgressEntryDto>>

    /**
     * Read the server's reading of the seat's latest run.
     *
     * @param seat The seat
     * @return The run, null with fewer than two results, or a failure
     */
    suspend fun progressSummary(seat: String): AuthResult<ProgressSummaryDto?>
}

/**
 * One test on G2.
 *
 * @property title The exam
 * @property date `yyyy-MM-dd`
 * @property marks The mark
 * @property totalMarks Out of how many
 * @property rank The rank, where published
 * @property rankedOutOf How many it is among, where published
 * @property average The batch average, where published
 */
data class ProgressPoint(
    val title: String,
    val date: String,
    val marks: Int,
    val totalMarks: Int,
    val rank: Int?,
    val rankedOutOf: Int?,
    val average: Double?,
)

/**
 * The server's one-line reading.
 *
 * @property direction `up`, `down` or `same`
 * @property run How many tests
 * @property firstMarks From
 * @property lastMarks To
 * @property totalMarks Out of
 * @property aboveAverage Against the batch average, or null
 */
data class ProgressReading(
    val direction: String,
    val run: Int,
    val firstMarks: Int,
    val lastMarks: Int,
    val totalMarks: Int,
    val aboveAverage: Boolean?,
)

/**
 * A batch the chips switch between.
 *
 * @property seat The child's seat in it
 * @property name The batch
 */
data class ProgressBatch(val seat: String, val name: String)

/** Everything G2 renders. */
sealed interface ChildProgressUiState {
    /** Reading. */
    data object Loading : ChildProgressUiState

    /**
     * Loaded.
     *
     * @property childName The child
     * @property batches The child's batches
     * @property selected The shown batch's seat
     * @property points Marked tests, oldest first; absences are left out
     * @property reading The server's reading, or null
     */
    data class Loaded(
        val childName: String,
        val batches: List<ProgressBatch>,
        val selected: String,
        val points: List<ProgressPoint>,
        val reading: ProgressReading?,
    ) : ChildProgressUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ChildProgressUiState
}

/**
 * Holds G2: one child's results, a batch at a time.
 *
 * @property repository The network
 */
class ChildProgressViewModel(
    private val repository: ChildProgressRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ChildProgressUiState>(ChildProgressUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ChildProgressUiState> = _state.asStateFlow()

    private var lastSeat: String? = null

    /**
     * Read the child holding this seat and that batch's results.
     *
     * @param seat The seat whose batch to show first
     */
    fun load(seat: String) {
        lastSeat = seat
        _state.value = ChildProgressUiState.Loading
        viewModelScope.launch {
            val home = repository.home()
            if (home !is AuthResult.Ok) {
                _state.value = failure(home)
                return@launch
            }
            val child = home.value.children.firstOrNull { c -> c.batches.any { it.enrollmentId == seat } }
            if (child == null) {
                _state.value = ChildProgressUiState.Failed("error.not_available", false)
                return@launch
            }
            val batches = child.batches.map { ProgressBatch(it.enrollmentId, it.batchName) }
            _state.value = read(child.displayName, batches, seat)
        }
    }

    /**
     * Show another of the child's batches.
     *
     * @param seat The child's seat in that batch
     */
    fun select(seat: String) {
        val current = _state.value as? ChildProgressUiState.Loaded ?: return
        if (current.selected == seat) return
        lastSeat = seat
        _state.update { current.copy(selected = seat, points = emptyList(), reading = null) }
        viewModelScope.launch { _state.value = read(current.childName, current.batches, seat) }
    }

    /** Read again, after a failure. */
    fun retry() {
        lastSeat?.let(::load)
    }

    /**
     * Read one batch's results and reading.
     *
     * @param name The child
     * @param batches The child's batches
     * @param seat The batch's seat
     * @return The state to show
     */
    private suspend fun read(name: String, batches: List<ProgressBatch>, seat: String): ChildProgressUiState {
        val entries = repository.progress(seat)
        if (entries !is AuthResult.Ok) return failure(entries)
        val reading = (repository.progressSummary(seat) as? AuthResult.Ok)?.value
        return ChildProgressUiState.Loaded(
            childName = name,
            batches = batches,
            selected = seat,
            points =
                entries.value.mapNotNull { entry ->
                    entry.marks?.let {
                        ProgressPoint(
                            entry.title,
                            entry.date,
                            it,
                            entry.totalMarks,
                            entry.rank,
                            entry.rankedOutOf,
                            entry.batchAverage,
                        )
                    }
                },
            reading =
                reading?.let {
                    ProgressReading(it.direction, it.run, it.firstMarks, it.lastMarks, it.totalMarks, it.aboveAverage)
                },
        )
    }

    /**
     * Name a failed read.
     *
     * @param result A refusal or a transport failure
     * @return The failure
     */
    private fun failure(result: AuthResult<*>): ChildProgressUiState =
        when (result) {
            is AuthResult.Refused -> ChildProgressUiState.Failed(
                result.envelope.error.messageKey,
                result.envelope.error.retryable,
            )
            else -> ChildProgressUiState.Failed(GuardianStateMapper.OFFLINE_KEY, true)
        }
}
