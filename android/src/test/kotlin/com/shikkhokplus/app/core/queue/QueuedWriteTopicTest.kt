package com.shikkhokplus.app.core.queue

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlinx.coroutines.test.runTest
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull

/** What a queued topic write carries: the plan flag, the notes, and why it was refused. */
class QueuedWriteTopicTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    private val json = ApiClient.json

    @Test
    fun `plan, notes and the conflict key survive the queue file`() {
        val item =
            QueuedWrite.topic("s-1", 4, "Friction", plan = true, notes = "")
                .copy(conflictKey = "teaching.topic.class_started")

        val back = json.decodeFromString(QueuedWrite.serializer(), json.encodeToString(QueuedWrite.serializer(), item))

        assertEquals(item, back)
        assertEquals("", back.notes)
        assertEquals(true, back.plan)
    }

    @Test
    fun `a queue file written before these fields existed still reads`() {
        val old =
            """{"id":"i","target":"topic","session_id":"s","base_version":1,""" +
                """"client_mutation_id":"m","topic":"x"}"""

        val item = json.decodeFromString(QueuedWrite.serializer(), old)

        assertFalse(item.plan)
        assertNull(item.notes)
        assertNull(item.conflictKey)
    }

    @Test
    fun `saving as covered is a new write, not a replay`() {
        val refused =
            QueuedWrite.topic("s-1", 4, "Friction", plan = true, notes = "n")
                .copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 6, conflictKey = "k")

        val covered = refused.coveredInstead()

        assertFalse(covered.plan)
        assertEquals("Friction", covered.topic)
        assertEquals("n", covered.notes)
        assertEquals(6, covered.baseVersion)
        assertEquals(QueueState.QUEUED, covered.state)
        assertNotEquals(refused.clientMutationId, covered.clientMutationId)
        assertNotEquals(refused.id, covered.id)
        assertNull(covered.conflictKey)
    }

    @Test
    fun `the sync records why a topic was refused`() = runTest {
        val store = QueueStore(File(folder.root, QueueStore.FILE_NAME))
        store.enqueue(QueuedWrite.topic("s-1", 4, "Friction", plan = true))
        val refusal =
            SendOutcome.Conflicted(
                4,
                ErrorEnvelope(ErrorBody("TOPIC_CLASS_STARTED", false, "teaching.topic.class_started")),
            )

        val queue = QueueSync(store) { refusal }.drain()

        assertEquals(QueueState.CONFLICTED, queue.single().state)
        assertEquals("teaching.topic.class_started", queue.single().conflictKey)
    }
}
