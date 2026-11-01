package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.network.SessionRosterDto
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.attendance.AttendanceRepository
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.AttendanceViewModel
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.record.SaveResult
import com.shikkhokplus.app.feature.sessions.SessionsRepository
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
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import com.shikkhokplus.app.core.queue.QueueState

/** Recording today's class: one Save queues the topic write and the attendance write. */
@OptIn(ExperimentalCoroutinesApi::class)
class ClassDayViewModelTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Sessions : SessionsRepository by FakeSessions() {
        override suspend fun sessionDetail(sessionId: String) =
            AuthResult.Ok(
                SessionDetailDto(
                    SessionDto(
                        sessionId = sessionId,
                        date = "2026-11-11",
                        startTime = "16:00:00",
                        origin = "recurrence",
                        status = "scheduled",
                        topicVersion = 3,
                        attendanceVersion = 7,
                    ),
                    seats = listOf(RosterSeatDto("e-1", "Rahim"), RosterSeatDto("e-2", "Karim")),
                    writable = true,
                ),
            )
    }

    private class Attendance : AttendanceRepository {
        val sent = mutableListOf<QueuedWrite>()

        override suspend fun submit(item: QueuedWrite): SendOutcome {
            sent += item
            return SendOutcome.Applied(item.baseVersion + 1)
        }

        override suspend fun currentRoster(sessionId: String) =
            AuthResult.Ok(SessionRosterDto(emptyList(), 0, writable = true))
    }

    private fun store() = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    private val today = calendarClass(state = CalendarState.TODAY, topic = "Newton", notes = "hw", recordable = true)

    @Test
    fun `Save sends the topic with plan off and notes, and the whole roster`() = runTest(dispatcher) {
        val store = store()
        val topics = FakeTopicSender()
        val attendance = Attendance()
        val roster = AttendanceViewModel(attendance, Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store)

        model.open(today)
        advanceUntilIdle()
        val marking = assertIs<AttendanceUiState.Marking>(roster.state.value)
        roster.toggle(marking.seats[1], false)
        model.typeTopic(" Newton's second law ")
        model.typeNotes("Homework: exercise 4")
        model.save()
        advanceUntilIdle()

        val topic = topics.sent.single()
        assertEquals(QueueTarget.TOPIC, topic.target)
        assertEquals(false, topic.plan)
        assertEquals(3, topic.baseVersion)
        assertEquals("Newton's second law", topic.topic)
        assertEquals("Homework: exercise 4", topic.notes)
        val roll = attendance.sent.single()
        assertEquals(QueueTarget.ATTENDANCE, roll.target)
        assertEquals(7, roll.baseVersion)
        assertEquals(listOf(true, false), roll.entries.map { it.present })
        assertEquals(SaveResult.SENT, model.state.value?.result)
    }

    @Test
    fun `Save does nothing before the roster has loaded`() = runTest(dispatcher) {
        val store = store()
        val topics = FakeTopicSender()
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store)

        model.open(today)
        model.save()
        advanceUntilIdle()

        assertEquals(0, topics.sent.size)
        assertNull(model.state.value?.result)
    }

    @Test
    fun `a lost connection leaves both writes queued on the phone`() = runTest(dispatcher) {
        val store = store()
        val topics = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
        val offline =
            object : AttendanceRepository {
                override suspend fun submit(item: QueuedWrite): SendOutcome = SendOutcome.Failed(null)

                override suspend fun currentRoster(sessionId: String) = AuthResult.TransportFailure
            }
        val roster = AttendanceViewModel(offline, Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store)
        model.open(today)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(
            setOf(QueueTarget.TOPIC, QueueTarget.ATTENDANCE),
            store.read().map { it.target }.toSet(),
        )
        assertEquals(SaveResult.QUEUED, model.state.value?.result)
    }

    private fun refusedPlan(store: QueueStore): QueuedWrite {
        val refused =
            QueuedWrite.topic("s-1", 3, "Newton's third law", plan = true, notes = "Bring ramps")
                .copy(state = QueueState.CONFLICTED, conflictKey = TopicWriter.CLASS_STARTED_KEY)
        store.enqueue(refused)
        return refused
    }

    private val started = calendarClass(state = CalendarState.TODAY, recordable = true, plannable = false)

    @Test
    fun `a started class offers the plan the sync refused, with the plan's words`() = runTest(dispatcher) {
        val store = store()
        val refused = refusedPlan(store)
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, FakeTopicSender()), store)

        model.open(started)
        advanceUntilIdle()

        assertEquals(refused.id, model.state.value?.conflictItemId)
        assertEquals("Newton's third law", model.state.value?.topic)
    }

    @Test
    fun `Save as covered replaces the refused plan with a covered write under a fresh id`() =
        runTest(dispatcher) {
            val store = store()
            val refused = refusedPlan(store)
            val topics = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
            val roster = AttendanceViewModel(Attendance(), Sessions(), store)
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store)
            model.open(started)
            advanceUntilIdle()

            model.saveAsCovered()
            advanceUntilIdle()

            val sent = topics.sent.single()
            assertEquals(false, sent.plan)
            assertEquals("Newton's third law", sent.topic)
            assertEquals("Bring ramps", sent.notes)
            assertNotEquals(refused.clientMutationId, sent.clientMutationId)
            val queue = store.read().filter { it.target == QueueTarget.TOPIC }
            assertEquals(1, queue.size)
            assertNotEquals(refused.id, queue.single().id)
            assertEquals(false, queue.single().plan)
            assertNull(model.state.value?.conflictItemId)
        }

    @Test
    fun `Discard plan removes the refused plan and sends nothing`() = runTest(dispatcher) {
        val store = store()
        refusedPlan(store)
        val topics = FakeTopicSender()
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store)
        model.open(started)
        advanceUntilIdle()

        model.discardPlan()

        assertTrue(store.read().none { it.target == QueueTarget.TOPIC })
        assertEquals(0, topics.sent.size)
        assertNull(model.state.value?.conflictItemId)
    }

    @Test
    fun `opening the class that is already open keeps typed input and the saved result`() =
        runTest(dispatcher) {
            val store = store()
            val roster = AttendanceViewModel(Attendance(), Sessions(), store)
            val model = ClassDayViewModel(roster, TopicWriter(store, FakeTopicSender()), store)
            model.open(today)
            advanceUntilIdle()
            model.typeTopic("Typed")
            model.save()
            advanceUntilIdle()

            model.open(today)
            advanceUntilIdle()

            assertEquals("Typed", model.state.value?.topic)
            assertEquals(SaveResult.SENT, model.state.value?.result)
        }
}
