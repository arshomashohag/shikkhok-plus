package com.shikkhokplus.app.feature.classcalendar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.SubjectOptionDto
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
 * @property errorKey A refusal to show, by message key; the form stays open
 * @property subjects The batch's subjects, for the chooser
 * @property subjectId The chosen subject, if any
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
    val errorKey: String? = null,
    val subjects: List<SubjectOptionDto> = emptyList(),
    val subjectId: String? = null,
)

/**
 * Records a class: topics, notes and attendance in one Save.
 *
 * The roster, its marks, its conflict screen and its queue badge all
 * stay with [AttendanceViewModel]; the topic goes through [TopicWriter].
 * Both writes are queued before they are sent, so a lost connection
 * loses neither. The topic is composed against the calendar payload's
 * version, so it saves even when the roster could not be read.
 *
 * @property attendance The attendance screen's view model
 * @property writer How a topic write is queued and sent
 * @property store The device's queue of unsent writes
 * @property subjects The subject chooser's reads and write
 */
class ClassDayViewModel(
    val attendance: AttendanceViewModel,
    private val writer: TopicWriter,
    private val store: QueueStore,
    private val subjects: ClassSubjects,
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
     * @param batchId The class's batch, to offer its subjects; null offers none
     */
    fun open(clazz: CalendarClassUi, batchId: String? = null) {
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
     * Choose the subject.
     *
     * @param subjectId The subject
     */
    fun chooseSubject(subjectId: String) {
        _state.value = _state.value?.copy(subjectId = subjectId)
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
     * Queue and send the topic write, and the attendance write when the
     * roster is open for marking. Waits only for the roster's first read
     * to settle: a roster that could not be read does not hold the topic
     * back.
     */
    fun save() {
        val current = _state.value ?: return
        val roster = attendance.state.value
        if (roster is AttendanceUiState.Idle || roster is AttendanceUiState.Loading) return
        if (current.saving) return
        val marking = roster as? AttendanceUiState.Marking
        _state.value = current.copy(saving = true, errorKey = null)
        val topic = current.topic.trim()
        val notes = current.notes.trim()
        val unchanged = current.savedTopic == topic && current.savedNotes == notes
        viewModelScope.launch {
            val subjectKey = afterSubject(current)
            val outcome = if (unchanged) null else sendTopic(current, topic, notes)
            if (marking != null && marking.writable) {
                attendance.submit(marking.sessionId, marking.attendanceVersion, marking.seats)
            }
            _state.value = _state.value?.let { settled(it, current, outcome, subjectKey) }
        }
    }

    private suspend fun sendTopic(current: ClassDayUiState, topic: String, notes: String): TopicOutcome {
        current.pendingItemId?.let { store.remove(it) }
        val item =
            QueuedWrite.topic(
                sessionId = current.clazz.sessionId,
                baseVersion = current.topicVersion ?: current.clazz.topicVersion,
                topic = topic,
                plan = false,
                notes = notes,
            )
        return writer.submit(item)
    }

    private fun settled(
        now: ClassDayUiState,
        before: ClassDayUiState,
        outcome: TopicOutcome?,
        subjectKey: String?,
    ): ClassDayUiState =
        when (outcome) {
            null -> now.copy(saving = false, result = unchangedResult(before), errorKey = subjectKey)
            is TopicOutcome.Refused -> now.copy(saving = false, errorKey = outcome.messageKey)
            else -> now.copy(saving = false, result = outcome.asResult(), errorKey = subjectKey)
        }

    private fun unchangedResult(current: ClassDayUiState): SaveResult {
        current.notice?.let { return it }
        val pending = current.pendingItemId ?: return SaveResult.SENT
        return if (store.read().any { it.id == pending }) SaveResult.QUEUED else SaveResult.SENT
    }

    private suspend fun afterSubject(current: ClassDayUiState): String? =
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
        viewModelScope.launch {
            val outcome = writer.send(covered)
            if (outcome is TopicOutcome.Refused) {
                _state.value =
                    _state.value?.copy(
                        saving = false,
                        topic = covered.topic.orEmpty(),
                        notes = covered.notes.orEmpty(),
                        errorKey = outcome.messageKey,
                    )
                return@launch
            }
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
            is TopicOutcome.ClassStarted, TopicOutcome.VersionConflict, is TopicOutcome.Refused ->
                SaveResult.CONFLICTED
        }
}
