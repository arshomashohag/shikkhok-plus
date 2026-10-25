package com.shikkhokplus.app.feature.batches

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the batches repository must provide. */
interface BatchesRepository {
    /**
     * List this teacher's batches.
     *
     * @return The batches, an error envelope, or a transport failure
     */
    suspend fun batches(): AuthResult<List<BatchDto>>

    /**
     * Create a batch.
     *
     * @param name The teacher's name for the class
     * @param subjects One or more subjects taught
     * @param defaultFee The inherited fee as a canonical string, or null
     * @param feeDueDay Day of month 1-31, or null
     * @return The created batch, an envelope, or a transport failure
     */
    suspend fun createBatch(
        name: String,
        subjects: List<String>,
        defaultFee: String?,
        feeDueDay: Int?,
    ): AuthResult<BatchDto>
}

/**
 * Holds the batch list's state. Holds no business logic [TC-9, D-31].
 *
 * @property repository Where the batches come from
 */
class BatchesViewModel(
    private val repository: BatchesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<BatchesUiState>(BatchesUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<BatchesUiState> = _state.asStateFlow()

    /** Load the teacher's batches. */
    fun load() {
        _state.value = BatchesUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.batches()) {
                    is AuthResult.Ok -> BatchesStateMapper.afterLoad(result.value)
                    is AuthResult.Refused -> BatchesStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        BatchesStateMapper.afterTransportFailure()
                }
        }
    }

    /** Repeat the load, and only when the user asks [TC-8, D-9]. */
    fun retry() = load()

    /**
     * Create a batch, then reload the list.
     *
     * **No optimistic insert.** V1 accepts no write without
     * connectivity [TC-8, D-9]: a row added locally before the server
     * confirmed would be a local write queue, which this product
     * deliberately does not have. The list reloads from the server so
     * what the teacher sees is what exists.
     *
     * @param name The teacher's name for the class
     * @param subjects One or more subjects taught
     * @param defaultFee The inherited fee as a canonical string, or null
     * @param feeDueDay Day of month 1-31, or null
     */
    fun create(
        name: String,
        subjects: List<String>,
        defaultFee: String?,
        feeDueDay: Int?,
    ) {
        _state.value = BatchesUiState.Loading
        viewModelScope.launch {
            when (val result = repository.createBatch(name, subjects, defaultFee, feeDueDay)) {
                is AuthResult.Ok -> load()
                is AuthResult.Refused ->
                    _state.value = BatchesStateMapper.afterError(result.envelope)
                AuthResult.TransportFailure ->
                    _state.value = BatchesStateMapper.afterTransportFailure()
            }
        }
    }
}
