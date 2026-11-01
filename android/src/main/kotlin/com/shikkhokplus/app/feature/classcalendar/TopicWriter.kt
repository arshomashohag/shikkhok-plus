package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.record.RecordRepository

/** How a topic write ended. */
sealed interface TopicOutcome {
    /**
     * The server has it.
     *
     * @property version The topic version the server now holds
     */
    data class Sent(val version: Int) : TopicOutcome

    /** Kept on the phone; the queue sends it when the connection returns. */
    data object Queued : TopicOutcome

    /**
     * The class had already started, so a plan was refused. The write
     * stays in the queue until the teacher chooses.
     *
     * @property item The refused write, now conflicted
     */
    data class ClassStarted(val item: QueuedWrite) : TopicOutcome

    /** Someone saved a different topic first; nothing was overwritten. */
    data object VersionConflict : TopicOutcome

    /**
     * The server refused the write and a retry as-is cannot help: the
     * class was cancelled, the batch closed, or the words were refused.
     * The write is taken off the phone; the teacher's words stay in the
     * field, so they can change them and save again.
     *
     * @property messageKey The refusal's key, from the server's envelope
     */
    data class Refused(val messageKey: String) : TopicOutcome
}

/**
 * Stores a topic write before sending it, so a lost connection loses
 * nothing [TC-8, D-9], then maps what the server said.
 *
 * @property store The device's queue of unsent writes
 * @property repository How a queued topic reaches the server
 */
class TopicWriter(
    private val store: QueueStore,
    private val repository: RecordRepository,
) {

    /**
     * Queue a write and send it.
     *
     * @param item The write
     * @return How it ended
     */
    suspend fun submit(item: QueuedWrite): TopicOutcome {
        store.enqueue(item)
        return send(item)
    }

    /**
     * Send a write that is already in the queue.
     *
     * @param item The write
     * @return How it ended
     */
    suspend fun send(item: QueuedWrite): TopicOutcome =
        when (val outcome = repository.send(item)) {
            is SendOutcome.Applied -> {
                store.remove(item.id)
                TopicOutcome.Sent(outcome.resultingVersion)
            }
            is SendOutcome.Conflicted -> afterConflict(item, outcome)
            is SendOutcome.Failed -> afterFailure(item, outcome)
        }

    private fun afterFailure(item: QueuedWrite, outcome: SendOutcome.Failed): TopicOutcome {
        val envelope = outcome.envelope ?: return TopicOutcome.Queued
        if (envelope.error.retryable) {
            store.replace(item.failed(envelope))
            return TopicOutcome.Queued
        }
        store.remove(item.id)
        return TopicOutcome.Refused(envelope.error.messageKey)
    }

    private fun afterConflict(item: QueuedWrite, outcome: SendOutcome.Conflicted): TopicOutcome {
        val key = outcome.envelope.error.messageKey
        if (key == VERSION_CONFLICT_KEY) {
            store.remove(item.id)
            return TopicOutcome.VersionConflict
        }
        if (key != CLASS_STARTED_KEY) {
            store.remove(item.id)
            return TopicOutcome.Refused(key)
        }
        val conflicted =
            item.copy(
                state = QueueState.CONFLICTED,
                conflictCurrentVersion = outcome.currentVersion,
                conflictKey = key,
            )
        store.replace(conflicted)
        return TopicOutcome.ClassStarted(conflicted)
    }

    companion object {
        /** The server's key for a plan sent after the class started. */
        const val CLASS_STARTED_KEY: String = "teaching.topic.class_started"

        /** The server's key for a topic composed against a stale version. */
        const val VERSION_CONFLICT_KEY: String = "error.topic_version_conflict"
    }
}
