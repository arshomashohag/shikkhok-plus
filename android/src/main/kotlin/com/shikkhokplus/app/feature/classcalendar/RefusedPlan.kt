package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite

/**
 * Finds a plan the server refused because its class had started.
 *
 * The background sync keeps such a plan in the queue as CONFLICTED. Once
 * the class has started the server calls it recordable, not plannable,
 * so it is the class screen that must offer the choice.
 *
 * @param items The queue
 * @param sessionId The class
 * @return The refused plan, or null
 */
fun refusedPlanFor(items: List<QueuedWrite>, sessionId: String): QueuedWrite? =
    items.firstOrNull {
        it.target == QueueTarget.TOPIC &&
            it.sessionId == sessionId &&
            it.state == QueueState.CONFLICTED &&
            it.plan &&
            it.conflictKey == TopicWriter.CLASS_STARTED_KEY
    }
