package com.shikkhokplus.app.feature.student

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds S1's state. Decisions are [StudentStateMapper]'s.
 *
 * @property repository The student's reads
 */
class MyBatchesViewModel(
    private val repository: StudentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<MyBatchesUiState>(MyBatchesUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<MyBatchesUiState> = _state.asStateFlow()

    /**
     * Load the student's batches.
     *
     * The account is read only when there are none, for the number the
     * empty state asks the student to give their teacher.
     */
    fun load() {
        _state.value = MyBatchesUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.batches()) {
                    is AuthResult.Ok -> {
                        val phone =
                            if (result.value.isEmpty()) {
                                (repository.phone() as? AuthResult.Ok)?.value?.phone
                            } else {
                                null
                            }
                        StudentStateMapper.afterBatches(result.value, phone)
                    }
                    is AuthResult.Refused -> {
                        val (key, retryable) = StudentStateMapper.failure(result.envelope)
                        MyBatchesUiState.Failed(key, retryable)
                    }
                    AuthResult.TransportFailure ->
                        MyBatchesUiState.Failed(StudentStateMapper.OFFLINE_KEY, retryable = true)
                }
        }
    }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() = load()
}
