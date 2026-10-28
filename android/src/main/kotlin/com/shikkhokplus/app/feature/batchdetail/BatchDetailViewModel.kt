package com.shikkhokplus.app.feature.batchdetail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.BatchEdit
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Holds the batch screen's header, fee chips and notices (T7). The
 * roster, classes and exams keep their own view models.
 *
 * @property repository The batch, its fees and its notices
 */
class BatchDetailViewModel(
    private val repository: BatchDetailRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(BatchDetailState())

    /** What the screen renders. */
    val state: StateFlow<BatchDetailState> = _state.asStateFlow()

    private var batchId: String? = null

    /**
     * Read the batch's header, fee chips and notices.
     *
     * @param batchId The batch
     */
    fun load(batchId: String) {
        this.batchId = batchId
        viewModelScope.launch {
            (repository.batch(batchId) as? AuthResult.Ok)?.let { batch ->
                _state.update { it.copy(header = BatchDetailMapper.header(batch.value)) }
            }
        }
        refreshFees()
        refreshNotices()
    }

    /**
     * Edit the batch's name, subjects, fee or due day.
     *
     * A new fee reaches only cycles generated after it, so the fee chips
     * are read again to show what still stands.
     *
     * @param edit What changes
     */
    fun editBatch(edit: BatchEdit) {
        val id = batchId ?: return
        if (_state.value.batchWrite == WriteState.Saving) return
        _state.update { it.copy(batchWrite = WriteState.Saving) }
        viewModelScope.launch {
            when (val result = repository.editBatch(id, edit)) {
                is AuthResult.Ok -> {
                    _state.update {
                        it.copy(header = BatchDetailMapper.header(result.value), batchWrite = WriteState.Saved)
                    }
                    refreshFees()
                }
                is AuthResult.Refused ->
                    _state.update {
                        it.copy(
                            batchWrite =
                                WriteState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable),
                        )
                    }
                AuthResult.TransportFailure ->
                    _state.update { it.copy(batchWrite = WriteState.Failed(OFFLINE_KEY, retryable = true)) }
            }
        }
    }

    /** Forget a finished or failed batch edit, once shown. */
    fun acknowledgeBatchEdit() {
        _state.update { it.copy(batchWrite = WriteState.Idle) }
    }

    /** Read the fee chips again, as after a failure or a payment. */
    fun refreshFees() {
        val id = batchId ?: return
        _state.update { it.copy(fees = FeeChips.Loading) }
        viewModelScope.launch {
            val chips =
                when (val result = repository.fees(id)) {
                    is AuthResult.Ok -> BatchDetailMapper.chips(result.value)
                    else -> FeeChips.Failed
                }
            _state.update { it.copy(fees = chips) }
        }
    }

    /**
     * Open a tab.
     *
     * @param tab The tab
     */
    fun select(tab: BatchTab) {
        _state.update { it.copy(tab = tab) }
    }

    /**
     * Post a notice.
     *
     * @param body The text
     */
    fun postNotice(body: String) {
        val id = batchId ?: return
        writeNotice { repository.postNotice(id, body.trim()) }
    }

    /**
     * Change a notice's text.
     *
     * @param noticeId The notice
     * @param body The new text
     */
    fun editNotice(noticeId: String, body: String) {
        writeNotice { repository.editNotice(noticeId, body.trim()) }
    }

    /**
     * Take a notice down.
     *
     * @param noticeId The notice
     */
    fun removeNotice(noticeId: String) {
        writeNotice { repository.removeNotice(noticeId) }
    }

    /** Forget a finished or failed notice write, once shown. */
    fun acknowledgeNotice() {
        _state.update { it.copy(noticeWrite = WriteState.Idle) }
    }

    /** Read the notices again. */
    private fun refreshNotices() {
        val id = batchId ?: return
        viewModelScope.launch {
            val notices = (repository.notices(id) as? AuthResult.Ok)?.value?.let(BatchDetailMapper::notices)
            _state.update { it.copy(notices = notices) }
        }
    }

    /**
     * Send a notice write, keeping the form open until the server answers.
     *
     * @param write The write
     */
    private fun writeNotice(write: suspend () -> AuthResult<Unit>) {
        if (_state.value.noticeWrite == WriteState.Saving) return
        _state.update { it.copy(noticeWrite = WriteState.Saving) }
        viewModelScope.launch {
            val outcome =
                when (val result = write()) {
                    is AuthResult.Ok -> WriteState.Saved
                    is AuthResult.Refused ->
                        WriteState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                    AuthResult.TransportFailure -> WriteState.Failed(OFFLINE_KEY, retryable = true)
                }
            _state.update { it.copy(noticeWrite = outcome) }
            if (outcome == WriteState.Saved) refreshNotices()
        }
    }

    private companion object {
        /** The key shown when the device cannot reach the server at all. */
        const val OFFLINE_KEY: String = "error.network.unreachable"
    }
}
