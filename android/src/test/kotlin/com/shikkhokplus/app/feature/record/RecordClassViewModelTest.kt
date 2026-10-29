package com.shikkhokplus.app.feature.record

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * T2: a topic is stored before it is sent, and a lost connection loses
 * nothing [TC-8, D-9].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class RecordClassViewModelTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val target =
        RecordTarget("s-9", "b-1", "Physics · Batch A", "16:00", topicVersion = 3, subjectName = "1st paper")

    private fun past(id: String, date: String, topic: String?) =
        SessionDto(
            sessionId = id,
            date = date,
            startTime = "16:00:00",
            origin = "recurrence",
            status = "held",
            topic = topic,
            topicLogged = topic != null,
        )

    private class Fake(
        var outcome: SendOutcome = SendOutcome.Applied(4),
        var subjectResult: AuthResult<Unit> = AuthResult.Ok(Unit),
    ) : RecordRepository {
        val sent = mutableListOf<QueuedWrite>()
        val subjectWrites = mutableListOf<String?>()

        override suspend fun subjects(batchId: String) =
            AuthResult.Ok(listOf(SubjectOptionDto("sub-1", "1st paper"), SubjectOptionDto("sub-2", "2nd paper")))

        override suspend fun sessions(batchId: String): AuthResult<List<SessionDto>> = AuthResult.Ok(sessions)

        var sessions: List<SessionDto> = emptyList()

        override suspend fun setSubject(sessionId: String, batchSubjectId: String?): AuthResult<Unit> {
            subjectWrites += batchSubjectId
            return subjectResult
        }

        override suspend fun send(item: QueuedWrite): SendOutcome {
            sent += item
            return outcome
        }
    }

    private fun store() = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    @Test
    fun `the suggestion is the batch's most recent logged topic`() = runTest(dispatcher) {
        val fake = Fake().apply {
            sessions =
                listOf(
                    past("s-1", "2026-10-10", "Heat and temperature"),
                    past("s-2", "2026-10-14", "First law of thermodynamics"),
                    past("s-3", "2026-10-15", null),
                )
        }
        val model = RecordClassViewModel(fake, store())

        model.open(target)
        advanceUntilIdle()

        val sheet = requireNotNull(model.sheet.value)
        assertEquals("First law of thermodynamics", sheet.suggestion)
        assertEquals("sub-1", sheet.subjectId)
        assertEquals(2, sheet.subjects.size)
    }

    @Test
    fun `a sent topic leaves nothing queued and carries its version`() = runTest(dispatcher) {
        val fake = Fake()
        val queue = store()
        val model = RecordClassViewModel(fake, queue)
        model.open(target)
        advanceUntilIdle()

        model.type("  Carnot cycle  ")
        model.save()
        advanceUntilIdle()

        val item = fake.sent.single()
        assertEquals(QueueTarget.TOPIC, item.target)
        assertEquals(3, item.baseVersion)
        assertEquals("Carnot cycle", item.topic)
        assertEquals(emptyList(), queue.read())
        assertEquals(SaveResult.SENT, model.saved.value)
        assertNull(model.sheet.value)
    }

    @Test
    fun `no connection keeps the topic on the phone for the queue`() = runTest(dispatcher) {
        val queue = store()
        val model = RecordClassViewModel(Fake(outcome = SendOutcome.Failed(null)), queue)
        model.open(target)
        advanceUntilIdle()

        model.type("Carnot cycle")
        model.save()
        advanceUntilIdle()

        assertEquals(listOf("Carnot cycle"), queue.read().map { it.topic })
        assertEquals(SaveResult.QUEUED, model.saved.value)
    }

    @Test
    fun `a blank topic is saved as deliberately blank`() = runTest(dispatcher) {
        val fake = Fake()
        val model = RecordClassViewModel(fake, store())
        model.open(target)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals("", fake.sent.single().topic)
    }

    @Test
    fun `a changed subject is written first, and a refusal stops the save`() = runTest(dispatcher) {
        val refused = AuthResult.Refused(ErrorEnvelope(ErrorBody("BATCH_INACTIVE", false, "teaching.batch.inactive")))
        val fake = Fake(subjectResult = refused)
        val model = RecordClassViewModel(fake, store())
        model.open(target)
        advanceUntilIdle()

        model.choose("sub-2")
        model.save()
        advanceUntilIdle()

        assertEquals(listOf<String?>("sub-2"), fake.subjectWrites)
        assertEquals(emptyList(), fake.sent)
        assertEquals("teaching.batch.inactive", model.sheet.value?.errorKey)
    }

    @Test
    fun `the suggestion fills the topic, and closing discards the sheet`() = runTest(dispatcher) {
        val fake = Fake().apply { sessions = listOf(past("s-2", "2026-10-14", "Vectors")) }
        val model = RecordClassViewModel(fake, store())
        model.open(target)
        advanceUntilIdle()

        model.useSuggestion()
        assertEquals("Vectors", model.sheet.value?.typed)

        model.close()
        assertNull(model.sheet.value)
    }

    @Test
    fun `a conflict removes the write and says so`() = runTest(dispatcher) {
        val envelope = ErrorEnvelope(ErrorBody("TOPIC_VERSION_CONFLICT", false, "error.topic_version_conflict"))
        val queue = store()
        val model = RecordClassViewModel(Fake(outcome = SendOutcome.Conflicted(4, envelope)), queue)
        model.open(target)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(emptyList(), queue.read())
        assertEquals(SaveResult.CONFLICTED, model.saved.value)
        model.acknowledge()
        assertNull(model.saved.value)
    }
}
