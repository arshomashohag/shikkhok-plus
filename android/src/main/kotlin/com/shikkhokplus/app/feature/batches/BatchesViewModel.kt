package com.shikkhokplus.app.feature.batches

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
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
}

/**
 * Maps responses to a [BatchesUiState]. The unit the tests target.
 */
object BatchesStateMapper {
    /** Shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map a loaded list.
     *
     * @param rows The batches the server returned
     * @return The state the screen renders
     */
    fun afterLoad(rows: List<BatchDto>): BatchesUiState =
        if (rows.isEmpty()) {
            BatchesUiState.Empty
        } else {
            BatchesUiState.Loaded(
                rows.map { dto ->
                    BatchRow(
                        id = dto.id,
                        name = dto.name,
                        subjects = dto.subjects,
                        defaultFee = dto.defaultFee,
                        // Counted SERVER-side. A client counting a
                        // roster it has not fetched would be guessing,
                        // and one that fetched every roster to count
                        // would be the N+1 shape on the client.
                        enrollmentCount = dto.enrollmentCount,
                        active = dto.active,
                    )
                },
            )
        }

    /**
     * Map a server refusal.
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): BatchesUiState =
        BatchesUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope arrived.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): BatchesUiState =
        BatchesUiState.Failed(OFFLINE_KEY, retryable = true)
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
}
