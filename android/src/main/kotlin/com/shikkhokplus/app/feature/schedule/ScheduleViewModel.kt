package com.shikkhokplus.app.feature.schedule

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the schedule screen needs from the server. */
interface ScheduleRepository {
    /**
     * Read a batch's weekly classes.
     *
     * @param batchId The batch
     * @return Its slots, or a refusal
     */
    suspend fun schedule(batchId: String): AuthResult<List<ScheduleSlotDto>>

    /**
     * Replace a batch's weekly classes; sessions follow at once.
     *
     * @param batchId The batch
     * @param slots The complete new schedule
     * @return The schedule as stored, or why the server refused
     */
    suspend fun save(
        batchId: String,
        slots: List<ScheduleSlotDto>,
    ): AuthResult<List<ScheduleSlotDto>>
}

/**
 * Holds one batch's schedule while it is edited. Holds no business logic.
 *
 * **Why this screen exists at all.** Sessions are generated from a
 * batch's schedule, and until now nothing could set one -- so every
 * batch created before this has none, and no session, and attendance
 * cannot be taken for it. This is where an existing batch gets one.
 *
 * @property repository Where the schedule is read and saved
 */
class ScheduleViewModel(
    private val repository: ScheduleRepository,
) : ViewModel() {

    private val _slots = MutableStateFlow<List<ScheduleSlotDto>?>(null)

    /** The stored schedule, or null while it loads. */
    val slots: StateFlow<List<ScheduleSlotDto>?> = _slots.asStateFlow()

    private val _loadFailed = MutableStateFlow<String?>(null)

    /** The message key when the read failed, or null. */
    val loadFailed: StateFlow<String?> = _loadFailed.asStateFlow()

    private val _writeState = MutableStateFlow<WriteState>(WriteState.Idle)

    /** Where the save stands; the screen closes only on Saved. */
    val writeState: StateFlow<WriteState> = _writeState.asStateFlow()

    /**
     * Read the schedule.
     *
     * @param batchId The batch
     */
    fun load(batchId: String) {
        _loadFailed.value = null
        viewModelScope.launch {
            when (val result = repository.schedule(batchId)) {
                is AuthResult.Ok -> _slots.value = result.value
                is AuthResult.Refused -> _loadFailed.value = result.envelope.error.messageKey
                AuthResult.TransportFailure -> _loadFailed.value = OFFLINE_KEY
            }
        }
    }

    /**
     * Save the schedule, replacing the old one.
     *
     * @param batchId The batch
     * @param slots The complete new schedule
     */
    fun save(batchId: String, slots: List<ScheduleSlotDto>) {
        if (_writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            _writeState.value =
                when (val result = repository.save(batchId, slots)) {
                    is AuthResult.Ok -> {
                        _slots.value = result.value
                        WriteState.Saved
                    }
                    is AuthResult.Refused ->
                        WriteState.Failed(
                            result.envelope.error.messageKey,
                            result.envelope.error.retryable,
                        )
                    AuthResult.TransportFailure -> WriteState.Failed(OFFLINE_KEY, true)
                }
        }
    }

    /** Mark a finished save as seen, so the screen does not close twice. */
    fun acknowledgeWrite() {
        if (_writeState.value != WriteState.Saving) _writeState.value = WriteState.Idle
    }

    private companion object {
        /** The key shown when the device cannot reach the server. */
        const val OFFLINE_KEY = "error.network.unreachable"
    }
}
