package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.TestQueueCipher
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import kotlinx.coroutines.test.runTest
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/** How each server answer to a topic write is reported, and what stays on the phone. */
class TopicWriterTest {

    @get:Rule
    val folder = TemporaryFolder()

    private fun store() = QueueStore(File(folder.root, QueueStore.FILE_NAME), TestQueueCipher)

    private fun item() = QueuedWrite.topic("s-1", 2, "Optics")

    private suspend fun submit(outcome: SendOutcome, store: QueueStore): TopicOutcome =
        TopicWriter(store, FakeTopicSender(mutableListOf(outcome))).submit(item())

    @Test
    fun `no response keeps the write queued`() = runTest {
        val store = store()

        assertEquals(TopicOutcome.Queued, submit(SendOutcome.Failed(null), store))
        assertEquals(1, store.read().size)
    }

    @Test
    fun `a retryable refusal keeps the write queued and marked failed`() = runTest {
        val store = store()
        val retryable = ErrorEnvelope(ErrorBody(code = "BUSY", retryable = true, messageKey = "error.busy"))

        assertEquals(TopicOutcome.Queued, submit(SendOutcome.Failed(retryable), store))
        assertEquals(QueueState.FAILED, store.read().single().state)
    }

    @Test
    fun `a refusal no retry can fix is reported with its key and taken off the phone`() = runTest {
        val store = store()

        val outcome = submit(SendOutcome.Failed(envelope("error.validation.too_long")), store)

        assertEquals(TopicOutcome.Refused("error.validation.too_long"), outcome)
        assertTrue(store.read().isEmpty())
    }

    @Test
    fun `a cancelled class is its own refusal, not a version conflict`() = runTest {
        val store = store()

        val outcome = submit(SendOutcome.Conflicted(2, envelope("teaching.session.cancelled")), store)

        assertEquals(TopicOutcome.Refused("teaching.session.cancelled"), outcome)
        assertTrue(store.read().isEmpty())
    }

    @Test
    fun `a stale version is a version conflict`() = runTest {
        val store = store()

        val outcome = submit(SendOutcome.Conflicted(3, envelope(TopicWriter.VERSION_CONFLICT_KEY)), store)

        assertEquals(TopicOutcome.VersionConflict, outcome)
        assertTrue(store.read().isEmpty())
    }

    @Test
    fun `a plan after the start stays queued as conflicted for the teacher to choose`() = runTest {
        val store = store()

        val outcome = submit(SendOutcome.Conflicted(2, envelope(TopicWriter.CLASS_STARTED_KEY)), store)

        assertIs<TopicOutcome.ClassStarted>(outcome)
        assertEquals(QueueState.CONFLICTED, store.read().single().state)
    }
}
