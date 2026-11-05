package com.shikkhokplus.app.feature.students

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One student: their numbers, their seats, and the actions on both.
 *
 * Every action reloads the student from the server afterwards, so what
 * the teacher sees is what exists [TC-8, D-9]. Whether a seat may be
 * deleted, and whether the student may be removed, are the server's
 * answers on the loaded student; a refusal is shown, never guessed.
 *
 * @property repository Where the student comes from
 */
class StudentDetailViewModel(
    private val repository: StudentsRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<StudentDetailUiState>(StudentDetailUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<StudentDetailUiState> = _state.asStateFlow()

    private val _writeState = MutableStateFlow<WriteState>(WriteState.Idle)

    /** Where the last action stands; a refusal is shown on the screen. */
    val writeState: StateFlow<WriteState> = _writeState.asStateFlow()

    private var studentId: String = ""

    /**
     * Load one student, with the batches they could still join.
     *
     * @param id The student
     */
    fun load(id: String) {
        studentId = id
        viewModelScope.launch { refresh() }
    }

    /** Repeat the load, only when the teacher asks. */
    fun retry() = load(studentId)

    private suspend fun refresh() {
        val batches =
            when (val listed = repository.batches()) {
                is AuthResult.Ok -> StudentsStateMapper.options(listed.value)
                else -> emptyList()
            }
        _state.value =
            when (val result = repository.student(studentId)) {
                is AuthResult.Ok -> StudentDetailUiState.Loaded(StudentsStateMapper.detail(result.value, batches))
                is AuthResult.Refused ->
                    StudentDetailUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                AuthResult.TransportFailure ->
                    StudentDetailUiState.Failed(StudentsStateMapper.OFFLINE_KEY, retryable = true)
            }
    }

    private fun act(write: suspend () -> AuthResult<*>, after: suspend () -> Unit = { refresh() }) {
        if (_writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            val result = write()
            _writeState.value = StudentsStateMapper.written(result)
            if (result is AuthResult.Ok) after()
        }
    }

    /**
     * Put the student in one more batch, at that batch's fee.
     *
     * @param batchId The batch
     */
    fun enroll(batchId: String) = act({ repository.enroll(studentId, batchId) })

    /**
     * The student leaves one batch from a date; dues stay [D4].
     *
     * @param enrollmentId The seat
     * @param onDate The ISO date
     */
    fun leave(enrollmentId: String, onDate: String) = act({ repository.leaveBatch(enrollmentId, onDate) })

    /**
     * Delete a seat nobody accepted.
     *
     * @param enrollmentId The seat
     */
    fun removeSeat(enrollmentId: String) = act({ repository.removeSeat(enrollmentId) })

    /**
     * Change the name, and either number while it is still changeable.
     *
     * @param name The new name, or null to keep it
     * @param studentPhone The new student number, or null to keep it
     * @param guardianPhone The new guardian number, or null to keep it
     */
    fun edit(name: String?, studentPhone: String?, guardianPhone: String?) =
        act({ repository.rename(studentId, name, studentPhone, guardianPhone) })

    /** Remove the student; the screen closes once the server agrees. */
    fun removeStudent() =
        act({ repository.removeStudent(studentId) }) { _state.value = StudentDetailUiState.Removed }

    /** Mark a finished write as seen. */
    fun acknowledgeWrite() {
        if (_writeState.value != WriteState.Saving) _writeState.value = WriteState.Idle
    }
}
