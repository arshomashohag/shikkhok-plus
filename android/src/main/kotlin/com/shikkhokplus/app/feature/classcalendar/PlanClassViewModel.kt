package com.shikkhokplus.app.feature.classcalendar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.record.SaveResult
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
 * @property topicVersion The version a write composes against, from the
 *   calendar payload, so a plan saves with no further read
 * @property saving A save is in flight
 * @property errorKey A failure to show, by message key
 * @property conflictItemId The refused plan awaiting a choice, if any
 * @property result How the last save went, until the screen closes
 * @property onClassDay The class is on the server's today, so attendance
 *   opens when it starts rather than on its day
 * @property subjects The batch's subjects, for the chooser
 * @property subjectId The chosen subject, if any
 */
data class PlanClassUiState(
    val clazz: CalendarClassUi,
    val topic: String,
    val notes: String,
    val topicVersion: Int = clazz.topicVersion,
    val saving: Boolean = false,
    val errorKey: String? = null,
    val conflictItemId: String? = null,
    val result: SaveResult? = null,
    val onClassDay: Boolean = false,
    val subjects: List<SubjectOptionDto> = emptyList(),
    val subjectId: String? = null,
)

/**
 * Plans a class's topics before it starts.
 *
 * The plan goes through the device queue like any topic. The server
 * refuses a plan once the class has started; that refusal is kept, and
 * the teacher chooses between saving the words as covered and
 * discarding the plan. Neither is decided here. A refusal no retry can
 * fix is shown as an error with the words left in the field.
 *
 * @property writer How a topic write is queued and sent
 * @property store The device's queue of unsent writes
 * @property subjects The subject chooser's reads and write
 */
class PlanClassViewModel(
    private val writer: TopicWriter,
    private val store: QueueStore,
    private val subjects: ClassSubjects,
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
     * @param batchId The class's batch, to offer its subjects; null offers none
     * @param today The server's date with the month, `YYYY-MM-DD`, or null
     */
    fun open(clazz: CalendarClassUi, batchId: String? = null, today: String? = null) {
        if (_state.value?.clazz?.sessionId == clazz.sessionId) return
        _state.value =
            PlanClassUiState(
                clazz = clazz,
                topic = clazz.topic.orEmpty(),
                notes = clazz.notes.orEmpty(),
                onClassDay = today != null && clazz.date == today,
            )
        batchId ?: return
        viewModelScope.launch {
            val options = subjects.load(batchId)
            _state.value =
                _state.value?.copy(
                    subjects = options,
                    subjectId = options.firstOrNull { it.name == clazz.subjectName }?.id,
                )
        }
    }

    /**
     * The teacher typed topics.
     *
     * @param typed The topics
     */
    fun typeTopic(typed: String) {
        _state.value = _state.value?.copy(topic = capClassText(typed))
    }

    /**
     * The teacher typed notes.
     *
     * @param typed The notes
     */
    fun typeNotes(typed: String) {
        _state.value = _state.value?.copy(notes = capClassText(typed))
    }

    /**
     * Choose the subject.
     *
     * @param subjectId The subject
     */
    fun chooseSubject(subjectId: String) {
        _state.value = _state.value?.copy(subjectId = subjectId)
    }

    /** Set a changed subject, then queue the plan and send it. */
    fun save() {
        val current = _state.value ?: return
        if (current.saving) return
        _state.value = current.copy(saving = true, errorKey = null)
        viewModelScope.launch {
            val subjectKey = afterSubject(current)
            val item =
                QueuedWrite.topic(
                    sessionId = current.clazz.sessionId,
                    baseVersion = current.topicVersion,
                    topic = current.topic.trim().ifEmpty { null },
                    plan = true,
                    notes = current.notes.trim(),
                )
            finish(writer.submit(item), subjectKey)
        }
    }

    private suspend fun afterSubject(current: PlanClassUiState): String? =
        when (
            val saved =
                subjects.saveIfChanged(
                    current.clazz.sessionId,
                    current.subjects,
                    current.subjectId,
                    current.clazz.subjectName,
                )
        ) {
            SubjectSave.Unchanged -> null
            is SubjectSave.Saved -> {
                _state.value = _state.value?.let { it.copy(clazz = it.clazz.copy(subjectName = saved.name)) }
                null
            }
            is SubjectSave.Failed -> saved.messageKey
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

    private fun finish(outcome: TopicOutcome, subjectKey: String? = null) {
        val current = _state.value ?: return
        val settled = current.copy(saving = false, errorKey = subjectKey)
        _state.value =
            when (outcome) {
                is TopicOutcome.Sent -> settled.copy(result = SaveResult.SENT, topicVersion = outcome.version)
                TopicOutcome.Queued -> settled.copy(result = SaveResult.QUEUED)
                is TopicOutcome.ClassStarted -> settled.copy(conflictItemId = outcome.item.id)
                TopicOutcome.VersionConflict -> settled.copy(result = SaveResult.CONFLICTED)
                is TopicOutcome.Refused -> settled.copy(errorKey = outcome.messageKey)
            }
    }

    /** Close the screen. */
    fun close() {
        _state.value = null
    }
}
