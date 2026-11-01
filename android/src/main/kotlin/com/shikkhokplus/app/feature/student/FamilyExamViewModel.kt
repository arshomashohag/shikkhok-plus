package com.shikkhokplus.app.feature.student

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds one exam's detail: its topics, read from the server.
 *
 * @property repository The family's reads
 */
class FamilyExamViewModel(
    private val repository: StudentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<FamilyExamUiState>(FamilyExamUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<FamilyExamUiState> = _state.asStateFlow()

    private var last: Pair<String, String>? = null

    /**
     * Load one exam.
     *
     * @param enrollmentId The seat
     * @param examId The exam
     */
    fun load(enrollmentId: String, examId: String) {
        last = enrollmentId to examId
        _state.value = FamilyExamUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.exam(enrollmentId, examId)) {
                    is AuthResult.Ok -> StudentStateMapper.afterExam(result.value)
                    is AuthResult.Refused -> {
                        val (key, retryable) = StudentStateMapper.failure(result.envelope)
                        FamilyExamUiState.Failed(key, retryable)
                    }
                    AuthResult.TransportFailure ->
                        FamilyExamUiState.Failed(StudentStateMapper.OFFLINE_KEY, retryable = true)
                }
        }
    }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() {
        last?.let { (seat, exam) -> load(seat, exam) }
    }
}
