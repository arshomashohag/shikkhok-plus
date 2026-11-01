package com.shikkhokplus.app.feature.classcalendar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.AttendanceViewModel
import com.shikkhokplus.app.feature.record.SaveResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The "today's class" screen's own fields.
 *
 * @property clazz The class being recorded
 * @property topic The topics as typed
 * @property notes The notes as typed
 * @property saving A save is in flight
 * @property result How the topic write went, until the screen closes
 * @property conflictItemId A refused plan awaiting the teacher's choice
 * @property notice How a topic write made before Save went, shown without
 *   locking the form
 * @property savedTopic The covered words already sent or queued, if any
 * @property savedNotes The covered notes already sent or queued
 * @property pendingItemId The queued covered-topic item still on the phone
 * @property topicVersion The topic version after a covered write was sent
 */
data class ClassDayUiState(
    val clazz: CalendarClassUi,
    val topic: String,
    val notes: String,
    val saving: Boolean = false,
    val result: SaveResult? = null,
    val conflictItemId: String? = null,
    val notice: SaveResult? = null,
    val savedTopic: String? = null,
    val savedNotes: String = "",
    val pendingItemId: String? = null,
    val topicVersion: Int? = null,
)

/**
 * Records a class: topics, notes and attendance in one Save.
 *
 * The roster, its marks, its conflict screen and its queue badge all
 * stay with [AttendanceViewModel]; the topic goes through [TopicWriter].
 * Both writes are queued before they are sent, so a lost connection
 * loses neither.
 *
 * @property attendance The attendance screen's view model
 * @property writer How a topic write is queued and sent
 * @property store The device's queue of unsent writes
 */
class ClassDayViewModel(
    val attendance: AttendanceViewModel,
    private val writer: TopicWriter,
    private val store: QueueStore,
) : ViewModel() {

    private val _state = MutableStateFlow<ClassDayUiState?>(null)

    /** The open screen's fields, or null. */
    val state: StateFlow<ClassDayUiState?> = _state.asStateFlow()

    /**
     * Open the screen for a class. A plan the sync refused while the
     * teacher was away is offered first. Opening the class that is
     * already open changes nothing, so a recreated screen keeps what was
     * typed.
     *
     * @param clazz The class
     */
    fun open(clazz: CalendarClassUi) {
        if (_state.value?.clazz?.sessionId == clazz.sessionId) return
        val queue = store.read()
        val refused = refusedPlanFor(queue, clazz.sessionId)
        val pending =
            queue.firstOrNull {
                it.target == QueueTarget.TOPIC &&
                    it.sessionId == clazz.sessionId &&
                    it.state != QueueState.CONFLICTED &&
                    !it.plan
            }
        val source = refused ?: pending
        _state.value =
            ClassDayUiState(
                clazz = clazz,
                topic = source?.topic ?: clazz.topic.orEmpty(),
                notes = source?.notes ?: clazz.notes.orEmpty(),
                conflictItemId = refused?.id,
                savedTopic = pending?.topic?.trim(),
                savedNotes = pending?.notes.orEmpty().trim(),
                pendingItemId = pending?.id,
            )
        attendance.load(clazz.sessionId)
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

    /** Queue and send the topic write and the attendance write. */
    fun save() {
        val current = _state.value ?: return
        val marking = attendance.state.value as? AttendanceUiState.Marking ?: return
        if (current.saving) return
        _state.value = current.copy(saving = true)
        val topic = current.topic.trim()
        val notes = current.notes.trim()
        val unchanged = current.savedTopic == topic && current.savedNotes == notes
        viewModelScope.launch {
            val result =
                if (unchanged) {
                    current.notice ?: SaveResult.SENT
                } else {
                    current.pendingItemId?.let { store.remove(it) }
                    val item =
                        QueuedWrite.topic(
                            sessionId = marking.sessionId,
                            baseVersion = current.topicVersion ?: marking.topicVersion,
                            topic = topic,
                            plan = false,
                            notes = notes,
                        )
                    writer.submit(item).asResult()
                }
            if (marking.writable) {
                attendance.submit(marking.sessionId, marking.attendanceVersion, marking.seats)
            }
            _state.value = _state.value?.copy(saving = false, result = result)
        }
    }

    /** Keep the refused plan's words as a record of what the class covered. */
    fun saveAsCovered() {
        val itemId = _state.value?.conflictItemId ?: return
        val refused = store.read().firstOrNull { it.id == itemId } ?: return
        if (refused.state != QueueState.CONFLICTED) return
        val covered = refused.coveredInstead()
        store.write(store.read().map { if (it.id == itemId) covered else it })
        _state.value = _state.value?.copy(saving = true, conflictItemId = null)
        viewModelScope.launch {
            val outcome = writer.send(covered)
            _state.value =
                _state.value?.copy(
                    saving = false,
                    topic = covered.topic.orEmpty(),
                    notes = covered.notes.orEmpty(),
                    notice = outcome.asResult(),
                    savedTopic = covered.topic.orEmpty().trim(),
                    savedNotes = covered.notes.orEmpty().trim(),
                    pendingItemId = covered.id.takeIf { outcome !is TopicOutcome.Sent },
                    topicVersion = (outcome as? TopicOutcome.Sent)?.version,
                )
        }
    }

    /** Drop the refused plan and go on with the class as the server has it. */
    fun discardPlan() {
        val current = _state.value ?: return
        val itemId = current.conflictItemId ?: return
        store.remove(itemId)
        _state.value =
            current.copy(
                conflictItemId = null,
                topic = current.clazz.topic.orEmpty(),
                notes = current.clazz.notes.orEmpty(),
            )
    }

    /** Close the screen. */
    fun close() {
        _state.value = null
    }

    private fun TopicOutcome.asResult(): SaveResult =
        when (this) {
            is TopicOutcome.Sent -> SaveResult.SENT
            TopicOutcome.Queued -> SaveResult.QUEUED
            is TopicOutcome.ClassStarted, TopicOutcome.VersionConflict -> SaveResult.CONFLICTED
        }
}
