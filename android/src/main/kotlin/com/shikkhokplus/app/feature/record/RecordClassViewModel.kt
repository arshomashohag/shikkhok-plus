package com.shikkhokplus.app.feature.record

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds the "Record class" sheet (T2).
 *
 * **The topic goes through the device queue**, the one write besides
 * attendance that may wait for a connection [TC-8, D-9]: it is stored
 * before it is sent, so closing the app or losing signal mid-class loses
 * nothing. A blank topic is saved as a deliberately blank one [BR2.2].
 *
 * @property repository Subjects, past classes, the subject write, the sender
 * @property store The device's queue of unsent writes
 */
class RecordClassViewModel(
    private val repository: RecordRepository,
    private val store: QueueStore,
) : ViewModel() {

    private val _sheet = MutableStateFlow<RecordSheet?>(null)

    /** The open sheet, or null. */
    val sheet: StateFlow<RecordSheet?> = _sheet.asStateFlow()

    private val _saved = MutableStateFlow<SaveResult?>(null)

    /** How the last save went, until acknowledged. */
    val saved: StateFlow<SaveResult?> = _saved.asStateFlow()

    /**
     * Open the sheet for a class, then fill in its subjects and suggestion.
     *
     * @param target The class
     */
    fun open(target: RecordTarget) {
        _sheet.value = RecordSheet(target)
        viewModelScope.launch {
            val subjects = (repository.subjects(target.batchId) as? AuthResult.Ok)?.value.orEmpty()
            val suggestion =
                (repository.sessions(target.batchId) as? AuthResult.Ok)
                    ?.value
                    ?.filter { it.sessionId != target.sessionId && it.topicLogged && !it.topic.isNullOrBlank() }
                    ?.maxByOrNull { "${it.date}T${it.startTime}" }
                    ?.topic
            _sheet.value =
                _sheet.value?.copy(
                    subjects = subjects,
                    subjectId = subjects.firstOrNull { it.name == target.subjectName }?.id,
                    suggestion = suggestion,
                )
        }
    }

    /** Close the sheet without saving. */
    fun close() {
        _sheet.value = null
    }

    /**
     * The teacher typed.
     *
     * @param typed The topic as typed
     */
    fun type(typed: String) {
        _sheet.value = _sheet.value?.copy(typed = typed)
    }

    /** Fill the topic from the suggestion. */
    fun useSuggestion() {
        val current = _sheet.value ?: return
        _sheet.value = current.copy(typed = current.suggestion ?: return)
    }

    /**
     * Choose the subject.
     *
     * @param subjectId The subject
     */
    fun choose(subjectId: String) {
        _sheet.value = _sheet.value?.copy(subjectId = subjectId)
    }

    /** Acknowledge the save result, once the screen has shown it. */
    fun acknowledge() {
        _saved.value = null
    }

    /** Save the subject, if changed, then queue and send the topic. */
    fun save() {
        val sheet = _sheet.value ?: return
        if (sheet.saving) return
        _sheet.value = sheet.copy(saving = true, errorKey = null)
        viewModelScope.launch {
            val chosen = sheet.subjects.firstOrNull { it.id == sheet.subjectId }
            if (chosen != null && chosen.name != sheet.target.subjectName) {
                val result = repository.setSubject(sheet.target.sessionId, chosen.id)
                if (result is AuthResult.Refused) {
                    _sheet.value = sheet.copy(saving = false, errorKey = result.envelope.error.messageKey)
                    return@launch
                }
            }
            val item = QueuedWrite.topic(sheet.target.sessionId, sheet.target.topicVersion, sheet.typed.trim())
            store.enqueue(item)
            _saved.value =
                when (val outcome = repository.send(item)) {
                    is SendOutcome.Applied -> {
                        store.remove(item.id)
                        SaveResult.SENT
                    }
                    is SendOutcome.Conflicted -> {
                        store.remove(item.id)
                        SaveResult.CONFLICTED
                    }
                    is SendOutcome.Failed -> {
                        // No response: it stays queued and the queue
                        // sends it when the connection returns. A refusal
                        // with an envelope is recorded on the item so the
                        // queue does not resend it blindly.
                        outcome.envelope?.let { store.replace(item.failed(it)) }
                        SaveResult.QUEUED
                    }
                }
            _sheet.value = null
        }
    }
}
