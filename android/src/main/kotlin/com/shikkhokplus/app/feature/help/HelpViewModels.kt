package com.shikkhokplus.app.feature.help

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.ui.RefreshGate
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Holds the reader's My questions list.
 *
 * Read when the screen opens and again on every return to it, so a
 * question just asked or answered is listed; re-read otherwise only when
 * the person pulls or taps retry [TC-8, D-9]. Nothing polls.
 *
 * @property repository The help centre
 */
class HelpListViewModel(
    private val repository: HelpRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<HelpListUiState>(HelpListUiState.Loading)

    /** What the list renders. */
    val state: StateFlow<HelpListUiState> = _state.asStateFlow()

    private val gate = RefreshGate()

    /** Whether a pull-to-refresh is in flight. */
    val refreshing: StateFlow<Boolean> = gate.refreshing

    /** Read the list, keeping what is on screen until the answer arrives. */
    fun load() {
        viewModelScope.launch { _state.value = HelpMapper.list(repository.tickets()) }
    }

    /** Re-read on a pull. */
    fun refresh() {
        gate.run(viewModelScope) { _state.value = HelpMapper.list(repository.tickets()) }
    }

    /** Read again after a failure, showing the loader meanwhile. */
    fun retry() {
        _state.value = HelpListUiState.Loading
        load()
    }
}

/**
 * Holds the Ask a question form.
 *
 * Validation here is format only -- trimmed, not empty, within the
 * server's length -- and typing past the length stops at it. Whether the
 * reader may ask another question today is the server's to say, and it
 * says so with `help.ticket.too_many`.
 *
 * @property repository The help centre
 */
class AskQuestionViewModel(
    private val repository: HelpRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AskUiState())

    /** What the form renders. */
    val state: StateFlow<AskUiState> = _state.asStateFlow()

    /**
     * Type the subject.
     *
     * @param text The subject as typed
     */
    fun subject(text: String) = _state.update { it.copy(subject = text.take(HELP_SUBJECT_MAX), write = idle(it)) }

    /**
     * Type the question.
     *
     * @param text The question as typed
     */
    fun body(text: String) = _state.update { it.copy(body = text.take(HELP_BODY_MAX), write = idle(it)) }

    /**
     * Send the question, when it can be sent. Also the explicit retry
     * after a failure: the fields still hold what was typed.
     */
    fun send() {
        val form = _state.value
        if (!form.canSend) return
        _state.update { it.copy(write = WriteState.Saving) }
        viewModelScope.launch {
            when (val result = repository.ask(form.subject.trim(), form.body.trim())) {
                is AuthResult.Ok ->
                    _state.update { it.copy(write = WriteState.Saved, ticketId = result.value.ticket.ticketId) }
                is AuthResult.Refused -> _state.update { it.copy(write = HelpMapper.writeFailed(result.envelope)) }
                AuthResult.TransportFailure -> _state.update { it.copy(write = HelpMapper.writeUnanswered()) }
            }
        }
    }
}

/**
 * Holds one question's thread and its reply box.
 *
 * @property repository The help centre
 */
class HelpThreadViewModel(
    private val repository: HelpRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<HelpThreadUiState>(HelpThreadUiState.Loading)

    /** What the thread renders. */
    val state: StateFlow<HelpThreadUiState> = _state.asStateFlow()

    private val _reply = MutableStateFlow(ReplyUiState())

    /** What the reply box renders. */
    val reply: StateFlow<ReplyUiState> = _reply.asStateFlow()

    private var ticketId: String? = null

    /**
     * Read one question.
     *
     * @param id The question
     */
    fun load(id: String) {
        ticketId = id
        _state.value = HelpThreadUiState.Loading
        viewModelScope.launch { _state.value = HelpMapper.thread(repository.ticket(id)) }
    }

    /** Read the question again after a failure. */
    fun retry() {
        ticketId?.let(::load)
    }

    /**
     * Type the reply.
     *
     * @param text The reply as typed
     */
    fun type(text: String) = _reply.update { it.copy(text = text.take(HELP_BODY_MAX), write = idle(it.write)) }

    /**
     * Send the reply, when it can be sent. Also the explicit retry after
     * a failure: the box still holds what was typed.
     *
     * On success the thread is replaced by the server's answer -- which
     * carries the reply and, for a closed question, the reopened status
     * -- and the box empties.
     */
    fun send() {
        val id = ticketId ?: return
        val box = _reply.value
        if (!box.canSend) return
        _reply.update { it.copy(write = WriteState.Saving) }
        viewModelScope.launch {
            when (val result = repository.reply(id, box.text.trim())) {
                is AuthResult.Ok -> {
                    _state.value = HelpThreadUiState.Loaded(HelpMapper.threadOf(result.value))
                    _reply.value = ReplyUiState()
                }
                is AuthResult.Refused -> _reply.update { it.copy(write = HelpMapper.writeFailed(result.envelope)) }
                AuthResult.TransportFailure -> _reply.update { it.copy(write = HelpMapper.writeUnanswered()) }
            }
        }
    }
}

/**
 * The write state once the person edits after a failure: the stale error
 * clears, anything in flight stays as it is.
 *
 * @param form The form being edited
 * @return The write state to keep
 */
private fun idle(form: AskUiState): WriteState = idle(form.write)

/**
 * The write state once the person edits after a failure.
 *
 * @param write The current write state
 * @return Idle in place of a failure, else unchanged
 */
private fun idle(write: WriteState): WriteState = if (write is WriteState.Failed) WriteState.Idle else write
