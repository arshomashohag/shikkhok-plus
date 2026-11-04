package com.shikkhokplus.app.feature.inbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NotificationDetailDto
import com.shikkhokplus.app.core.ui.RefreshGate
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the inbox needs from the network. */
interface InboxRepository {
    /**
     * Read the reader's own inbox.
     *
     * @return The inbox, a refusal, or a transport failure
     */
    suspend fun inbox(): AuthResult<InboxDto>

    /**
     * Read one message and what it opens to.
     *
     * @param id The message
     * @return The detail, a refusal, or a transport failure
     */
    suspend fun detail(id: String): AuthResult<NotificationDetailDto>

    /**
     * Mark every message read.
     *
     * @return Done, a refusal, or a transport failure
     */
    suspend fun markAllRead(): AuthResult<Unit>

    /**
     * Mark one message read.
     *
     * @param id The message
     * @return Done, a refusal, or a transport failure
     */
    suspend fun markRead(id: String): AuthResult<Unit>
}

/**
 * Holds the inbox: for the bell's badge on a home screen, and for the
 * inbox screen itself, where opening an item marks that item read.
 *
 * @property repository The inbox
 */
class InboxViewModel(
    private val repository: InboxRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<InboxUiState>(InboxUiState.Loading)

    /** What the bell or the screen renders. */
    val state: StateFlow<InboxUiState> = _state.asStateFlow()

    private val gate = RefreshGate()

    /** Whether a pull-to-refresh is in flight. */
    val refreshing: StateFlow<Boolean> = gate.refreshing

    /** Read the inbox, for the badge. */
    fun load() {
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Re-read on a pull, keeping what is on screen until the answer
     * arrives. Started only by the person pulling [TC-8, D-9].
     */
    fun refresh() {
        gate.run(viewModelScope) { _state.value = read() }
    }

    /**
     * Read the inbox for the screen.
     *
     * Nothing is marked read here: only an item the reader opens is.
     */
    fun open() {
        _state.value = InboxUiState.Loading
        load()
    }

    /** Mark every message read, then read the inbox again. */
    fun markAllRead() {
        viewModelScope.launch {
            repository.markAllRead()
            _state.value = read()
        }
    }

    /**
     * Open one item: mark it read, then say where it leads.
     *
     * @param message The item tapped
     * @param navigate Called with where the item leads
     */
    fun select(message: InboxMessage, navigate: (InboxTarget) -> Unit) {
        viewModelScope.launch {
            repository.markRead(message.id)
            navigate(InboxMapper.targetOf(message))
        }
    }

    /**
     * Read the inbox.
     *
     * @return The state to show
     */
    private suspend fun read(): InboxUiState =
        when (val result = repository.inbox()) {
            is AuthResult.Ok -> InboxMapper.afterLoad(result.value)
            is AuthResult.Refused -> InboxMapper.afterError(result.envelope)
            AuthResult.TransportFailure -> InboxMapper.afterTransportFailure()
        }
}
