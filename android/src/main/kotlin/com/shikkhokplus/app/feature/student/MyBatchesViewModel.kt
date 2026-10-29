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
     * The account is read too: its name and number head the list, and
     * the empty state asks the student to give their teacher the number.
     */
    fun load() {
        _state.value = MyBatchesUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.batches()) {
                    is AuthResult.Ok -> {
                        // The account, for S1's subtitle and the empty
                        // state's number. Its failure costs only those.
                        val me = (repository.phone() as? AuthResult.Ok)?.value
                        StudentStateMapper.afterBatches(result.value, me?.phone, me?.selfName)
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
