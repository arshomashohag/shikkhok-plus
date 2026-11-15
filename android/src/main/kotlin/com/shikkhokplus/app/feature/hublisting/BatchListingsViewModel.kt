package com.shikkhokplus.app.feature.hublisting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The owner's batches with their listing state. */
sealed interface BatchListingsBody {
    /** Waiting for the list. */
    data object Loading : BatchListingsBody

    /**
     * The batches, oldest first as the server ordered them.
     *
     * @property batches The server's rows
     */
    data class Loaded(val batches: List<BatchListingResponse>) : BatchListingsBody

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : BatchListingsBody
}

/**
 * One batch's editor.
 *
 * @property batch What the server holds
 * @property draft What the owner has typed
 * @property busy Whether a write is in flight
 * @property failure The last failed call, or null
 */
data class BatchEditorState(
    val batch: BatchListingResponse,
    val draft: BatchDraft = batchDraftOf(batch),
    val busy: Boolean = false,
    val failure: HubFailure? = null,
) {
    /** Whether the owner has typed something not yet saved. */
    val dirty: Boolean get() = draft != batchDraftOf(batch)

    /** Whether the batch's listing is suspended, and so read-only. */
    val readOnly: Boolean get() = ListingStatus.fromWire(batch.status) == ListingStatus.SUSPENDED

    /** Whether Save is offered. */
    val canSave: Boolean get() = !readOnly && dirty && !busy

    /** Whether Publish is offered: the server's `publishable`, with nothing unsaved. */
    val canPublish: Boolean
        get() = !readOnly && !dirty && !busy && batch.publishable && batch.status != ListingStatus.PUBLISHED.wire

    /** Whether Unpublish is offered. */
    val canUnpublish: Boolean get() = !readOnly && !dirty && !busy && batch.status == ListingStatus.PUBLISHED.wire
}

/**
 * The batch-listings screen.
 *
 * @property body The list
 * @property editor The open editor, or null
 */
data class BatchListingsState(
    val body: BatchListingsBody = BatchListingsBody.Loading,
    val editor: BatchEditorState? = null,
)

/** The write a Retry repeats. */
private enum class BatchWrite { SAVE, PUBLISH, UNPUBLISH }

/**
 * Holds the owner's batch listings and one batch's editor.
 *
 * The fee and teacher names are the server's, shown as sent; nothing here
 * parses or formats them. A failed write keeps the form and offers the same
 * call again [TC-8].
 *
 * @property api The network
 */
class BatchListingsViewModel(
    private val api: HubApi,
) : ViewModel() {

    private val _state = MutableStateFlow(BatchListingsState())

    /** What the screen renders. */
    val state: StateFlow<BatchListingsState> = _state.asStateFlow()

    private var lastWrite: BatchWrite? = null

    /** Read the batches. */
    fun load() {
        viewModelScope.launch {
            val result = api.batchListings()
            _state.update {
                when (result) {
                    is AuthResult.Ok -> it.copy(body = BatchListingsBody.Loaded(result.value))
                    else ->
                        result.hubFailure()
                            ?.let { f -> it.copy(body = BatchListingsBody.Failed(f.messageKey, f.canRetry)) }
                            ?: it
                }
            }
        }
    }

    /** Repeat what last failed: the editor's write, or the read. */
    fun retry() {
        val editor = _state.value.editor
        if (editor?.failure?.canRetry == true) {
            when (lastWrite) {
                BatchWrite.SAVE -> save()
                BatchWrite.PUBLISH -> publish()
                BatchWrite.UNPUBLISH -> unpublish()
                null -> Unit
            }
        } else if (_state.value.body is BatchListingsBody.Failed) {
            _state.update { it.copy(body = BatchListingsBody.Loading) }
            load()
        }
    }

    /**
     * Open one batch's editor.
     *
     * @param batchId The batch
     */
    fun edit(batchId: String) {
        val batch = (_state.value.body as? BatchListingsBody.Loaded)?.batches?.firstOrNull { it.batchId == batchId }
        if (batch != null) _state.update { it.copy(editor = BatchEditorState(batch)) }
    }

    /** Close the editor and read the list as the server now has it. */
    fun close() {
        _state.update { it.copy(editor = null) }
        load()
    }

    /**
     * Change what the owner has typed. Ignored when the listing is suspended.
     *
     * @param change The edit to the draft
     */
    fun change(change: (BatchDraft) -> BatchDraft) =
        _state.update { s ->
            val editor = s.editor
            if (editor == null || editor.readOnly) s else s.copy(editor = editor.copy(draft = change(editor.draft)))
        }

    /** Send the form. */
    fun save() = write(BatchWrite.SAVE, { it.canSave }) { id, editor -> api.saveBatch(id, batchBody(editor.draft)) }

    /** Publish this batch's listing. */
    fun publish() = write(BatchWrite.PUBLISH, { it.canPublish }) { id, _ -> api.publishBatch(id) }

    /** Take this batch's listing down. */
    fun unpublish() = write(BatchWrite.UNPUBLISH, { it.canUnpublish }) { id, _ -> api.unpublishBatch(id) }

    private fun write(
        kind: BatchWrite,
        allowed: (BatchEditorState) -> Boolean,
        call: suspend (String, BatchEditorState) -> AuthResult<BatchListingResponse>,
    ) {
        val editor = _state.value.editor ?: return
        if (!allowed(editor)) return
        lastWrite = kind
        _state.update { it.copy(editor = editor.copy(busy = true, failure = null)) }
        viewModelScope.launch {
            val result = call(editor.batch.batchId, editor)
            _state.update { s ->
                val open = s.editor ?: return@update s
                when (result) {
                    is AuthResult.Ok -> s.copy(editor = BatchEditorState(result.value))
                    else -> s.copy(editor = open.copy(busy = false, failure = result.hubFailure()))
                }
            }
        }
    }
}
