package com.shikkhokplus.app.feature.students

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.StudentSeatBody
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The Students tab, the add-student form and the roster's picker [0018].
 *
 * Holds no business logic [TC-9]: the filter and the search are sent to
 * the server, which answers with the matching students. A new load
 * cancels the one in flight, so a quick change of filter cannot be
 * overwritten by the slower answer to the previous one.
 *
 * @property repository Where the students come from
 */
class StudentsViewModel(
    private val repository: StudentsRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<StudentsUiState>(StudentsUiState.Loading)

    /** What the list renders. */
    val state: StateFlow<StudentsUiState> = _state.asStateFlow()

    private val _batches = MutableStateFlow<List<BatchOption>>(emptyList())

    /** The teacher's batches, for the chips and the batch picker. */
    val batches: StateFlow<List<BatchOption>> = _batches.asStateFlow()

    private val _filter = MutableStateFlow<StudentFilter>(StudentFilter.All)

    /** The filter in force. */
    val filter: StateFlow<StudentFilter> = _filter.asStateFlow()

    private val _query = MutableStateFlow("")

    /** The search text in force. */
    val query: StateFlow<String> = _query.asStateFlow()

    private val _writeState = MutableStateFlow<WriteState>(WriteState.Idle)

    /** Where the add form's or the picker's write stands. */
    val writeState: StateFlow<WriteState> = _writeState.asStateFlow()

    private val _picked = MutableStateFlow<Set<String>>(emptySet())

    /** The picker's chosen students. */
    val picked: StateFlow<Set<String>> = _picked.asStateFlow()

    private var loading: Job? = null

    /**
     * Load the list with a filter, and the batches beside it.
     *
     * @param filter Which students
     */
    fun load(filter: StudentFilter = _filter.value) {
        _filter.value = filter
        loading?.cancel()
        _state.value = StudentsUiState.Loading
        loading =
            viewModelScope.launch {
                val narrowed = filter != StudentFilter.All || _query.value.isNotBlank()
                _state.value =
                    when (val result = repository.students(filter, _query.value)) {
                        is AuthResult.Ok -> StudentsStateMapper.afterLoad(result.value, narrowed)
                        is AuthResult.Refused -> StudentsStateMapper.afterError(result.envelope)
                        AuthResult.TransportFailure ->
                            StudentsUiState.Failed(StudentsStateMapper.OFFLINE_KEY, retryable = true)
                    }
            }
        loadBatches()
    }

    /** Load the teacher's batches, for the chips and the batch picker. */
    fun loadBatches() {
        viewModelScope.launch {
            val result = repository.batches()
            if (result is AuthResult.Ok) _batches.value = StudentsStateMapper.options(result.value)
        }
    }

    /**
     * Search by name or number, on the server.
     *
     * @param text What the teacher typed
     */
    fun search(text: String) {
        _query.value = text
        load()
    }

    /** Repeat the load, only when the teacher asks [TC-8, D-9]. */
    fun retry() = load()

    /**
     * Add a student, optionally to batches. Closes the form on success.
     *
     * A second tap while one is in flight is ignored.
     *
     * @param name The typed name
     * @param studentPhone The typed student number, or null
     * @param guardianPhone The typed guardian number, or null
     * @param seats The batches chosen, each with its fee or null
     */
    fun create(
        name: String,
        studentPhone: String?,
        guardianPhone: String?,
        seats: List<StudentSeatBody>,
    ) {
        if (_writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            val result = repository.create(name, studentPhone, guardianPhone, seats)
            _writeState.value = StudentsStateMapper.written(result)
            if (result is AuthResult.Ok) load()
        }
    }

    /**
     * Choose or unchoose a student in the roster's picker.
     *
     * @param studentId The student
     */
    fun togglePick(studentId: String) {
        _picked.value = if (studentId in _picked.value) _picked.value - studentId else _picked.value + studentId
    }

    /**
     * Seat the chosen students in one batch.
     *
     * @param batchId The batch
     */
    fun addPicked(batchId: String) {
        val chosen = _picked.value.toList()
        if (chosen.isEmpty() || _writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            val result = repository.addToBatch(batchId, chosen)
            _writeState.value = StudentsStateMapper.written(result)
            if (result is AuthResult.Ok) _picked.value = emptySet()
        }
    }

    /** Mark a finished write as seen, so a form does not close twice. */
    fun acknowledgeWrite() {
        if (_writeState.value != WriteState.Saving) _writeState.value = WriteState.Idle
    }
}
