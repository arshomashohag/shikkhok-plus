package com.shikkhokplus.app.feature.classcalendar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.record.SaveResult
import com.shikkhokplus.app.feature.sessions.SessionsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The "plan a class" screen's state.
 *
 * @property clazz The class being planned
 * @property topic The topics as typed
 * @property notes The notes as typed
 * @property topicVersion The version a write composes against, once read
 * @property saving A save is in flight
 * @property errorKey A failure to show, by message key
 * @property conflictItemId The refused plan awaiting a choice, if any
 * @property result How the last save went, until the screen closes
 */
data class PlanClassUiState(
    val clazz: CalendarClassUi,
    val topic: String,
    val notes: String,
    val topicVersion: Int? = null,
    val saving: Boolean = false,
    val errorKey: String? = null,
    val conflictItemId: String? = null,
    val result: SaveResult? = null,
)

/**
 * Plans a class's topics before it starts.
 *
 * The plan goes through the device queue like any topic. The server
 * refuses a plan once the class has started; that refusal is kept, and
 * the teacher chooses between saving the words as covered and
 * discarding the plan. Neither is decided here.
 *
 * @property sessions Where the session's topic version is read
 * @property writer How a topic write is queued and sent
 * @property store The device's queue of unsent writes
 */
class PlanClassViewModel(
    private val sessions: SessionsRepository,
    private val writer: TopicWriter,
    private val store: QueueStore,
) : ViewModel() {

    private val _state = MutableStateFlow<PlanClassUiState?>(null)

    /** The open screen, or null. */
    val state: StateFlow<PlanClassUiState?> = _state.asStateFlow()

    /**
     * Open the screen for a class.
     *
     * Opening the class that is already open changes nothing, so a
     * screen recreated by a configuration change keeps what was typed.
     *
     * @param clazz The class
     */
    fun open(clazz: CalendarClassUi) {
        if (_state.value?.clazz?.sessionId == clazz.sessionId) return
        _state.value = PlanClassUiState(clazz, clazz.topic.orEmpty(), clazz.notes.orEmpty())
        viewModelScope.launch {
            val version =
                when (val detail = sessions.sessionDetail(clazz.sessionId)) {
                    is AuthResult.Ok -> detail.value.session.topicVersion
                    is AuthResult.Refused -> return@launch fail(detail.envelope.error.messageKey)
                    AuthResult.TransportFailure -> return@launch fail(ClassCalendarViewModel.OFFLINE_KEY)
                }
            _state.value = _state.value?.copy(topicVersion = version)
        }
    }

    /**
     * The teacher typed topics.
     *
     * @param typed The topics
     */
    fun typeTopic(typed: String) {
        _state.value = _state.value?.copy(topic = typed)
    }

    /**
     * The teacher typed notes.
     *
     * @param typed The notes
     */
    fun typeNotes(typed: String) {
        _state.value = _state.value?.copy(notes = typed)
    }

    /** Queue the plan and send it. */
    fun save() {
        val current = _state.value ?: return
        val version = current.topicVersion ?: return
        if (current.saving) return
        _state.value = current.copy(saving = true, errorKey = null)
        val item =
            QueuedWrite.topic(
                sessionId = current.clazz.sessionId,
                baseVersion = version,
                topic = current.topic.trim().ifEmpty { null },
                plan = true,
                notes = current.notes.trim(),
            )
        viewModelScope.launch { finish(writer.submit(item)) }
    }

    /** Keep the refused plan's words as a record of what the class covered. */
    fun saveAsCovered() {
        val itemId = _state.value?.conflictItemId ?: return
        val refused = store.read().firstOrNull { it.id == itemId } ?: return
        if (refused.state != QueueState.CONFLICTED) return
        val covered = refused.coveredInstead()
        store.write(store.read().map { if (it.id == itemId) covered else it })
        _state.value = _state.value?.copy(saving = true, conflictItemId = null)
        viewModelScope.launch { finish(writer.send(covered)) }
    }

    /** Drop the refused plan, keeping what the server holds. */
    fun discardPlan() {
        val itemId = _state.value?.conflictItemId ?: return
        store.remove(itemId)
        close()
    }

    private fun finish(outcome: TopicOutcome) {
        _state.value =
            when (outcome) {
                TopicOutcome.Sent -> _state.value?.copy(saving = false, result = SaveResult.SENT)
                TopicOutcome.Queued -> _state.value?.copy(saving = false, result = SaveResult.QUEUED)
                is TopicOutcome.ClassStarted ->
                    _state.value?.copy(saving = false, conflictItemId = outcome.item.id)
                TopicOutcome.VersionConflict -> _state.value?.copy(saving = false, result = SaveResult.CONFLICTED)
            }
    }

    private fun fail(messageKey: String) {
        _state.value = _state.value?.copy(errorKey = messageKey)
    }

    /** Close the screen. */
    fun close() {
        _state.value = null
    }
}
