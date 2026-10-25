package com.shikkhokplus.app.core.queue

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlinx.coroutines.test.runTest
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The sync loop's behaviour [BR3.1, BR3.6, BR3.7].
 *
 * Written from the acceptance criteria. The two that matter most are
 * negative: a conflicted item is **not** retried automatically, and a
 * re-apply does **not** reuse the mutation id.
 */
class QueueSyncTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    private fun store(): QueueStore = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    private fun roster(sessionId: String = "s-1", baseVersion: Int = 7): QueuedWrite =
        QueuedWrite.attendance(
            sessionId = sessionId,
            baseVersion = baseVersion,
            entries = listOf(AttendanceEntry("e-1", present = true)),
        )

    private fun envelope(code: String): ErrorEnvelope =
        ErrorEnvelope(
            ErrorBody(
                code = code,
                retryable = false,
                messageKey = "attendance.version_conflict",
            ),
        )

    /** Records what the loop tried to send. */
    private class RecordingTransport(
        private val outcomes: MutableList<SendOutcome>,
    ) : QueueTransport {
        val sent: MutableList<QueuedWrite> = mutableListOf()

        override suspend fun send(item: QueuedWrite): SendOutcome {
            sent += item
            return outcomes.removeFirstOrNull() ?: SendOutcome.Applied(item.baseVersion + 1)
        }
    }

    @Test
    fun `an applied item leaves the queue`() = runTest {
        val store = store()
        store.enqueue(roster())
        val transport = RecordingTransport(mutableListOf(SendOutcome.Applied(8)))

        val remaining = QueueSync(store, transport).drain()

        assertEquals(emptyList(), remaining)
        assertEquals(emptyList(), store.read())
    }

    @Test
    fun `a refused item becomes conflicted and not failed`() = runTest {
        // THE RULE [BR3.6]. The two states carry different remedies,
        // and a screen showing one for both leaves a teacher repeating
        // a request that cannot succeed.
        val store = store()
        store.enqueue(roster())
        val transport =
            RecordingTransport(
                mutableListOf(
                    SendOutcome.Conflicted(
                        currentVersion = 8,
                        envelope = envelope("ATTENDANCE_VERSION_CONFLICT"),
                    ),
                ),
            )

        QueueSync(store, transport).drain()

        val item = store.read().single()
        assertEquals(QueueState.CONFLICTED, item.state)
        assertNotEquals(QueueState.FAILED, item.state)
        assertEquals(8, item.conflictCurrentVersion)
    }

    @Test
    fun `a conflicted item is never sent again by the drain`() {
        // **The assertion that distinguishes correct from
        // nearly-correct** [BR3.6]. A loop that marked the state
        // correctly and still retried would pass the test above and
        // fail this one -- and retrying a stale version is guaranteed
        // to be refused again.
        runTest {
            val store = store()
            val conflicted =
                roster().copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 8)
            store.enqueue(conflicted)
            val transport = RecordingTransport(mutableListOf())

            QueueSync(store, transport).drain()

            assertEquals(
                emptyList(),
                transport.sent,
                "a conflicted item must not be sent without the teacher asking",
            )
            assertEquals(QueueState.CONFLICTED, store.read().single().state)
        }
    }

    @Test
    fun `a failed item is retried automatically, because retrying can help`() = runTest {
        // The other side of the same rule: `failed` means the send did
        // not succeed, and sending again is the right remedy. Dropping
        // automatic retry for it as well would leave a roster unsent
        // after a passing connectivity blip.
        val store = store()
        store.enqueue(roster().copy(state = QueueState.FAILED))
        val transport = RecordingTransport(mutableListOf(SendOutcome.Applied(8)))

        QueueSync(store, transport).drain()

        assertEquals(1, transport.sent.size)
        assertEquals(emptyList(), store.read())
    }

    @Test
    fun `a transport failure marks the item failed and keeps it`() = runTest {
        // Losing a roster that could not be sent is the failure the
        // queue exists to prevent.
        val store = store()
        store.enqueue(roster())
        val transport = RecordingTransport(mutableListOf(SendOutcome.Failed(null)))

        QueueSync(store, transport).drain()

        assertEquals(QueueState.FAILED, store.read().single().state)
    }

    @Test
    fun `one dead item does not block the rest of the drain`() = runTest {
        // A failed roster for one session must not stop another
        // session's roster reaching the server.
        val store = store()
        store.enqueue(roster(sessionId = "s-1"))
        store.enqueue(roster(sessionId = "s-2"))
        val transport =
            RecordingTransport(
                mutableListOf(SendOutcome.Failed(null), SendOutcome.Applied(8)),
            )

        QueueSync(store, transport).drain()

        assertEquals(2, transport.sent.size)
        assertEquals(listOf("s-1"), store.read().map { it.sessionId })
    }

    @Test
    fun `items are attempted oldest first`() = runTest {
        // Two rosters for one session must reach the server in the
        // order the teacher recorded them, or the second's
        // base_version describes a state that never existed.
        val store = store()
        val first = roster(sessionId = "s-1", baseVersion = 7)
        val second = roster(sessionId = "s-1", baseVersion = 8)
        store.enqueue(first)
        store.enqueue(second)
        val transport =
            RecordingTransport(
                mutableListOf(SendOutcome.Failed(null), SendOutcome.Failed(null)),
            )

        QueueSync(store, transport).drain()

        assertEquals(listOf(first.id, second.id), transport.sent.map { it.id })
    }

    @Test
    fun `re-apply replaces the conflicted item with a fresh write`() = runTest {
        // THE RULE [BR3.7], at the sync layer. The refused item must
        // not linger beside its own replacement, or the next drain
        // sends both.
        val store = store()
        val conflicted =
            roster(baseVersion = 7)
                .copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 8)
        store.enqueue(conflicted)
        val sync = QueueSync(store, RecordingTransport(mutableListOf()))

        val after = sync.reapply(conflicted.id)

        assertEquals(1, after.size)
        val fresh = store.read().single()
        assertEquals(QueueState.QUEUED, fresh.state)
        assertEquals(8, fresh.baseVersion)
        assertNotEquals(conflicted.clientMutationId, fresh.clientMutationId)
    }

    @Test
    fun `re-apply refuses an item that is not conflicted`() = runTest {
        // Offering re-apply where it has no meaning would be a control
        // the screen should not have drawn.
        val store = store()
        val queued = roster()
        store.enqueue(queued)
        val sync = QueueSync(store, RecordingTransport(mutableListOf()))

        assertFailsWith<IllegalArgumentException> { sync.reapply(queued.id) }
    }

    @Test
    fun `discard removes the conflicted entry and nothing else`() = runTest {
        val store = store()
        val conflicted =
            roster(sessionId = "s-1").copy(state = QueueState.CONFLICTED)
        val other = roster(sessionId = "s-2")
        store.enqueue(conflicted)
        store.enqueue(other)
        val sync = QueueSync(store, RecordingTransport(mutableListOf()))

        sync.discard(conflicted.id)

        assertEquals(listOf(other.id), store.read().map { it.id })
    }

    @Test
    fun `only the two mid-class paths can be queued at all`() {
        // THE RULE [BR3.1] violation_behaviour (b): a third path
        // queueing. NFR5 permits offline writes for the mid-class path
        // only -- attendance and the topic log -- and every other write
        // requires connectivity.
        //
        // Asserted as the closed set, because that is the shape a
        // third path would break.
        assertEquals(
            listOf(QueueTarget.ATTENDANCE, QueueTarget.TOPIC),
            QueueTarget.entries.toList(),
        )
        assertEquals(2, QueueTarget.entries.size)
    }

    @Test
    fun `a topic write queues as its own target`() {
        // BR2.1: the topic log is the second queued path, carrying its
        // own version column. Building the queue for attendance alone
        // leaves half the mid-class path failing in exactly the
        // conditions the queue exists for.
        val item = QueuedWrite.topic(sessionId = "s-1", baseVersion = 3, topic = "Algebra")

        assertEquals(QueueTarget.TOPIC, item.target)
        assertEquals("Algebra", item.topic)
        assertTrue(item.entries.isEmpty())
    }

    @Test
    fun `a topic saved as empty is not a topic that was never written`() {
        // BR2.2. An empty string is a topic deliberately saved blank;
        // null is one never written. The queue must carry the
        // difference, or the distinction dies before it reaches the
        // server.
        val blank = QueuedWrite.topic(sessionId = "s-1", baseVersion = 3, topic = "")

        assertEquals("", blank.topic)
        assertNotEquals(null, blank.topic)
    }
}
