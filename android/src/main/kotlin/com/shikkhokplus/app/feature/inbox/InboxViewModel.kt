package com.shikkhokplus.app.feature.inbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.InboxDto
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
     * Mark every message read.
     *
     * @return Done, a refusal, or a transport failure
     */
    suspend fun markRead(): AuthResult<Unit>
}

/**
 * Holds the inbox: for the bell's badge on a home screen, and for the
 * inbox screen itself, which marks what it showed as read.
 *
 * @property repository The inbox
 */
class InboxViewModel(
    private val repository: InboxRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<InboxUiState>(InboxUiState.Loading)

    /** What the bell or the screen renders. */
    val state: StateFlow<InboxUiState> = _state.asStateFlow()

    /** Read the inbox, for the badge. */
    fun load() {
        viewModelScope.launch { _state.value = read() }
    }

    /**
     * Read the inbox and, once shown, mark it read on the server.
     *
     * The messages keep their unread look for this visit, so the reader
     * can see which are new; the next read shows them as seen.
     */
    fun open() {
        _state.value = InboxUiState.Loading
        viewModelScope.launch {
            val shown = read()
            _state.value = shown
            if (shown is InboxUiState.Loaded && shown.unread > 0) repository.markRead()
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
