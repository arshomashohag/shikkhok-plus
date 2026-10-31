package com.shikkhokplus.app.feature.student

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds S2's state: one batch from the student's or a guardian's side.
 *
 * Three reads, in order, and the first failure is the result: a half-
 * loaded batch would show a fee with no classes, or classes with no
 * fee, and either reads as the whole truth.
 *
 * @property repository The student's reads
 */
class StudentBatchViewModel(
    private val repository: StudentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<StudentBatchUiState>(StudentBatchUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<StudentBatchUiState> = _state.asStateFlow()

    private val _tab = MutableStateFlow(FamilyTab.CLASSES)

    /** The open tab, which survives the screen being rebuilt. */
    val tab: StateFlow<FamilyTab> = _tab.asStateFlow()

    private var lastSeat: String? = null

    /**
     * Load one batch.
     *
     * @param enrollmentId The student's own seat
     */
    fun load(enrollmentId: String) {
        lastSeat = enrollmentId
        _state.value = StudentBatchUiState.Loading
        viewModelScope.launch { _state.value = read(enrollmentId) }
    }

    /**
     * Open a tab.
     *
     * @param tab The tab to show
     */
    fun select(tab: FamilyTab) {
        _tab.value = tab
    }

    /**
     * Load a seat only if this model has not already, for a detail
     * screen that may be the first to build it.
     *
     * @param enrollmentId The seat
     */
    fun ensureLoaded(enrollmentId: String) {
        if (lastSeat != enrollmentId) load(enrollmentId)
    }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() {
        lastSeat?.let(::load)
    }

    /**
     * Make the three reads and combine them.
     *
     * @param seat The student's own seat
     * @return The state to show
     */
    private suspend fun read(seat: String): StudentBatchUiState {
        val batches =
            when (val result = repository.batches()) {
                is AuthResult.Ok -> result.value
                else -> return failed(result)
            }
        val batch = batches.firstOrNull { it.enrollmentId == seat } ?: return StudentStateMapper.notFound()
        return readSeat(withFee(batch))
    }

    /**
     * Add the seat's latest fee when the list did not carry one. A
     * failed fee read leaves the header with the fee-history link
     * rather than failing the whole page.
     *
     * @param batch The seat's row
     * @return The row, with a fee line where one was read
     */
    private suspend fun withFee(batch: StudentBatchDto): StudentBatchDto {
        if (batch.currentFee != null) return batch
        val fee = (repository.seatFee(batch.enrollmentId) as? AuthResult.Ok)?.value
        return if (fee == null) batch else batch.copy(currentFee = fee)
    }

    /**
     * Read one seat's classes and results, after its row was found.
     *
     * @param batch The seat's row from the student's own list
     * @return The state to show
     */
    private suspend fun readSeat(batch: StudentBatchDto): StudentBatchUiState {
        val view =
            when (val result = repository.batchView(batch.enrollmentId)) {
                is AuthResult.Ok -> result.value
                else -> return failed(result)
            }
        // A refusal here is the teacher hiding marksheets from families:
        // the page still shows, with no results, rather than failing whole.
        return when (val result = repository.progress(batch.enrollmentId)) {
            is AuthResult.Ok -> StudentStateMapper.afterBatch(batch, view, result.value)
            is AuthResult.Refused -> StudentStateMapper.afterBatch(batch, view, emptyList())
            AuthResult.TransportFailure -> failed(result)
        }
    }

    /**
     * Name a failed read.
     *
     * @param result A refusal or a transport failure
     * @return The failure to show
     */
    private fun failed(result: AuthResult<*>): StudentBatchUiState =
        when (result) {
            is AuthResult.Refused -> {
                val (key, retryable) = StudentStateMapper.failure(result.envelope)
                StudentBatchUiState.Failed(key, retryable)
            }
            else -> StudentBatchUiState.Failed(StudentStateMapper.OFFLINE_KEY, retryable = true)
        }
}
