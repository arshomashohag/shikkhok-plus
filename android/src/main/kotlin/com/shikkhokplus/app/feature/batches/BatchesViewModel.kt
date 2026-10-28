package com.shikkhokplus.app.feature.batches

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.ui.WriteState
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

    private val _writeState = MutableStateFlow<WriteState>(WriteState.Idle)

    /**
     * Where the create form's write stands, apart from the list.
     *
     * The form watches this and closes only on [WriteState.Saved]. See
     * [WriteState] for the race this replaces.
     */
    val writeState: StateFlow<WriteState> = _writeState.asStateFlow()

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
     * **The outcome goes to [writeState], and the list is left alone.**
     * This used to set the list to `Loading` and then to the refusal,
     * while the screen that had just been navigated back to reloaded
     * the same list concurrently. Whichever response landed last won,
     * so a refused create could be overwritten by the old list -- no
     * class, and no error. A refusal now belongs to the form that
     * caused it, which stays open to show it.
     *
     * A second tap while one is in flight is ignored, so a slow network
     * cannot create the same class twice.
     *
     * @param name The teacher's name for the class
     * @param subjects One or more subjects taught
     * @param defaultFee The inherited fee in canonical form, or null
     * @param feeDueDay Day of month 1-31, or null
     */
    fun create(
        name: String,
        subjects: List<String>,
        defaultFee: String?,
        feeDueDay: Int?,
    ) {
        if (_writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            _writeState.value =
                when (val result = repository.createBatch(name, subjects, defaultFee, feeDueDay)) {
                    is AuthResult.Ok -> {
                        load()
                        WriteState.Saved
                    }
                    is AuthResult.Refused ->
                        WriteState.Failed(
                            messageKey = result.envelope.error.messageKey,
                            retryable = result.envelope.error.retryable,
                        )
                    AuthResult.TransportFailure ->
                        WriteState.Failed(
                            messageKey = BatchesStateMapper.OFFLINE_KEY,
                            retryable = true,
                        )
                }
        }
    }

    /**
     * Mark a finished write as seen, so the form does not close twice.
     *
     * Called by the route once it has acted on [WriteState.Saved], and
     * when the form is abandoned, so the next form opens clean rather
     * than showing the last one's error.
     */
    fun acknowledgeWrite() {
        if (_writeState.value != WriteState.Saving) _writeState.value = WriteState.Idle
    }
}
