package com.shikkhokplus.app.feature.classcalendar

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
        PlanClassViewModel(FakeSessions(topicVersion = 5), TopicWriter(store, fake), store)

    private val clazz = calendarClass(topic = "Friction", notes = "Bring ramps", plannable = true)

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
