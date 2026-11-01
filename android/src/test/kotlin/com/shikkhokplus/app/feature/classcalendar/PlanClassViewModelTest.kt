package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.record.SaveResult
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
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Planning a class: the plan goes through the queue, and a started class is the teacher's call. */
@OptIn(ExperimentalCoroutinesApi::class)
class PlanClassViewModelTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val started = SendOutcome.Conflicted(5, envelope(TopicWriter.CLASS_STARTED_KEY, "TOPIC_CLASS_STARTED"))

    private fun store() = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    private fun model(fake: FakeTopicSender, store: QueueStore) =
        PlanClassViewModel(TopicWriter(store, fake), store, ClassSubjects(fake))

    private val clazz = calendarClass(topic = "Friction", notes = "Bring ramps", plannable = true, topicVersion = 5)

    @Test
    fun `saving enqueues a plan write against the session's topic version`() = runTest(dispatcher) {
        val fake = FakeTopicSender()
        val model = model(fake, store())
        model.open(clazz)
        advanceUntilIdle()
        model.typeTopic("  Newton's third law  ")
        model.typeNotes("Read ch 4")

        model.save()
        advanceUntilIdle()

        val sent = fake.sent.single()
        assertTrue(sent.plan)
        assertEquals(QueueTarget.TOPIC, sent.target)
        assertEquals(5, sent.baseVersion)
        assertEquals("Newton's third law", sent.topic)
        assertEquals("Read ch 4", sent.notes)
        assertEquals(SaveResult.SENT, model.state.value?.result)
    }

    @Test
    fun `clearing the plan sends a null topic, and cleared notes an empty string`() = runTest(dispatcher) {
        val fake = FakeTopicSender()
        val model = model(fake, store())
        model.open(clazz)
        advanceUntilIdle()
        model.typeTopic("   ")
        model.typeNotes("")

        model.save()
        advanceUntilIdle()

        assertNull(fake.sent.single().topic)
        assertEquals("", fake.sent.single().notes)
    }

    @Test
    fun `with no connection the plan stays queued and the teacher is told so`() = runTest(dispatcher) {
        val fake = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
        val store = store()
        val model = model(fake, store)
        model.open(clazz)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(SaveResult.QUEUED, model.state.value?.result)
        assertEquals(1, store.read().size)
    }

    @Test
    fun `a plan refused because the class started offers both choices and keeps the write`() =
        runTest(dispatcher) {
            val fake = FakeTopicSender(mutableListOf(started))
            val store = store()
            val model = model(fake, store)
            model.open(clazz)
            advanceUntilIdle()

            model.save()
            advanceUntilIdle()

            val state = assertNotNull(model.state.value)
            assertNotNull(state.conflictItemId)
            assertNull(state.result)
            val kept = store.read().single()
            assertEquals(QueueState.CONFLICTED, kept.state)
            assertEquals(TopicWriter.CLASS_STARTED_KEY, kept.conflictKey)
        }

    @Test
    fun `Save as covered re-enqueues the same words as a covered topic with a fresh id`() =
        runTest(dispatcher) {
            val fake = FakeTopicSender(mutableListOf(started))
            val store = store()
            val model = model(fake, store)
            model.open(clazz)
            advanceUntilIdle()
            model.typeTopic("Newton's third law")
            model.save()
            advanceUntilIdle()
            val refused = fake.sent.single()

            model.saveAsCovered()
            advanceUntilIdle()

            val covered = fake.sent.last()
            assertEquals(false, covered.plan)
            assertEquals("Newton's third law", covered.topic)
            assertNotEquals(refused.clientMutationId, covered.clientMutationId)
            assertEquals(SaveResult.SENT, model.state.value?.result)
            assertNull(model.state.value?.conflictItemId)
            assertTrue(store.read().isEmpty())
        }

    @Test
    fun `Discard plan removes the refused write and sends nothing`() = runTest(dispatcher) {
        val fake = FakeTopicSender(mutableListOf(started))
        val store = store()
        val model = model(fake, store)
        model.open(clazz)
        advanceUntilIdle()
        model.save()
        advanceUntilIdle()

        model.discardPlan()
        advanceUntilIdle()

        assertTrue(store.read().isEmpty())
        assertEquals(1, fake.sent.size)
        assertNull(model.state.value)
    }

    @Test
    fun `opening the class that is already open keeps what was typed`() = runTest(dispatcher) {
        val model = model(FakeTopicSender(), store())
        model.open(clazz)
        advanceUntilIdle()
        model.typeTopic("Typed by the teacher")

        model.open(clazz)
        advanceUntilIdle()

        assertEquals("Typed by the teacher", model.state.value?.topic)
        assertEquals(5, model.state.value?.topicVersion)
    }

    @Test
    fun `the plan saves offline from the calendar payload alone`() = runTest(dispatcher) {
        val fake = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
        val store = store()
        val model = model(fake, store)
        model.open(calendarClass(topic = "Friction", plannable = true, topicVersion = 7))
        advanceUntilIdle()
        model.typeTopic("Newton's third law")

        model.save()
        advanceUntilIdle()

        assertEquals(7, fake.sent.single().baseVersion)
        assertEquals(7, store.read().single().baseVersion)
        assertEquals(SaveResult.QUEUED, model.state.value?.result)
    }

    @Test
    fun `a refused write is an error with the words kept, never queued`() = runTest(dispatcher) {
        val refused = SendOutcome.Failed(envelope("error.validation.too_long", "VALIDATION"))
        val fake = FakeTopicSender(mutableListOf(refused))
        val store = store()
        val model = model(fake, store)
        model.open(clazz)
        advanceUntilIdle()
        model.typeTopic("Too long")

        model.save()
        advanceUntilIdle()

        val state = model.state.value
        assertNull(state?.result)
        assertEquals("error.validation.too_long", state?.errorKey)
        assertEquals("Too long", state?.topic)
        assertTrue(store.read().isEmpty())

        model.typeTopic("Short")
        model.save()
        advanceUntilIdle()

        assertEquals(listOf("Too long", "Short"), fake.sent.map { it.topic })
        assertEquals(SaveResult.SENT, model.state.value?.result)
    }

    @Test
    fun `a cancelled class shows its own message, not the version conflict`() = runTest(dispatcher) {
        val cancelled = SendOutcome.Conflicted(5, envelope("teaching.session.cancelled", "SESSION_CANCELLED"))
        val store = store()
        val model = model(FakeTopicSender(mutableListOf(cancelled)), store)
        model.open(clazz)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertNull(model.state.value?.result)
        assertEquals("teaching.session.cancelled", model.state.value?.errorKey)
        assertTrue(store.read().isEmpty())
    }

    @Test
    fun `a changed subject is set through the subject write before the plan is sent`() = runTest(dispatcher) {
        val subjects = listOf(SubjectOptionDto("sub-1", "Physics"), SubjectOptionDto("sub-2", "Maths"))
        val fake = FakeTopicSender(options = subjects)
        val model = model(fake, store())
        model.open(clazz, batchId = "b-1")
        advanceUntilIdle()
        assertEquals("sub-1", model.state.value?.subjectId)

        model.chooseSubject("sub-2")
        model.save()
        advanceUntilIdle()

        assertEquals<List<Pair<String, String?>>>(listOf("s-1" to "sub-2"), fake.subjectWrites)
        assertEquals("Maths", model.state.value?.clazz?.subjectName)
        assertEquals(1, fake.sent.size)
    }

    @Test
    fun `an unchanged subject is not written`() = runTest(dispatcher) {
        val fake = FakeTopicSender(options = listOf(SubjectOptionDto("sub-1", "Physics")))
        val model = model(fake, store())
        model.open(clazz, batchId = "b-1")
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertTrue(fake.subjectWrites.isEmpty())
    }

    @Test
    fun `the class's own day is the server's today, not the phone's`() = runTest(dispatcher) {
        val model = model(FakeTopicSender(), store())

        model.open(calendarClass(date = "2026-11-16", plannable = true), today = "2026-11-16")

        assertEquals(true, model.state.value?.onClassDay)
        model.close()
        model.open(calendarClass(date = "2026-11-17", plannable = true), today = "2026-11-16")
        assertEquals(false, model.state.value?.onClassDay)
    }

    @Test
    fun `topics and notes are cut at 2000 characters`() = runTest(dispatcher) {
        val model = model(FakeTopicSender(), store())
        model.open(clazz)

        model.typeTopic("t".repeat(2001))
        model.typeNotes("n".repeat(2500))

        assertEquals(2000, model.state.value?.topic?.length)
        assertEquals(2000, model.state.value?.notes?.length)
    }

    @Test
    fun `a topic version conflict is reported and not kept`() = runTest(dispatcher) {
        val other = SendOutcome.Conflicted(6, envelope("error.topic_version_conflict"))
        val store = store()
        val model = model(FakeTopicSender(mutableListOf(other)), store)
        model.open(clazz)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(SaveResult.CONFLICTED, model.state.value?.result)
        assertTrue(store.read().isEmpty())
    }
}
