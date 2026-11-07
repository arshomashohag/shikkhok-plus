package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.network.SessionRosterDto
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.TestQueueCipher
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

    private fun store() = QueueStore(File(folder.root, QueueStore.FILE_NAME), TestQueueCipher)

    private fun dayModel(roster: AttendanceViewModel, store: QueueStore) =
        ClassDayViewModel(roster, TopicWriter(store, FakeTopicSender()), store, ClassSubjects(FakeTopicSender()))

    private val today =
        calendarClass(state = CalendarState.TODAY, topic = "Newton", notes = "hw", recordable = true, topicVersion = 3)

    @Test
    fun `Save sends the topic with plan off and notes, and the whole roster`() = runTest(dispatcher) {
        val store = store()
        val topics = FakeTopicSender()
        val attendance = Attendance()
        val roster = AttendanceViewModel(attendance, Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))

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
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))

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
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
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
        val model = dayModel(roster, store)

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
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
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
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
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
            val model = dayModel(roster, store)
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

    @Test
    fun `after Save as covered the form stays editable with the plan's words and one topic item`() =
        runTest(dispatcher) {
            val store = store()
            refusedPlan(store)
            val topics = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
            val attendance = Attendance()
            val roster = AttendanceViewModel(attendance, Sessions(), store)
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
            model.open(started)
            advanceUntilIdle()

            model.saveAsCovered()
            advanceUntilIdle()

            val state = model.state.value
            assertNull(state?.result)
            assertEquals(SaveResult.QUEUED, state?.notice)
            assertEquals("Newton's third law", state?.topic)
            assertEquals("Bring ramps", state?.notes)
            assertTrue(assertIs<AttendanceUiState.Marking>(roster.state.value).writable)
            assertEquals(1, store.read().count { it.target == QueueTarget.TOPIC })

            model.save()
            advanceUntilIdle()

            assertEquals(1, topics.sent.size)
            assertEquals(1, attendance.sent.size)
            assertEquals(1, store.read().count { it.target == QueueTarget.TOPIC })
            assertEquals(SaveResult.QUEUED, model.state.value?.result)
        }

    @Test
    fun `after a sent covered topic Save sends attendance only`() = runTest(dispatcher) {
        val store = store()
        refusedPlan(store)
        val topics = FakeTopicSender()
        val attendance = Attendance()
        val roster = AttendanceViewModel(attendance, Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
        model.open(started)
        advanceUntilIdle()
        model.saveAsCovered()
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(1, topics.sent.size)
        assertEquals(1, attendance.sent.size)
        assertTrue(store.read().none { it.target == QueueTarget.TOPIC })
    }

    @Test
    fun `editing after a queued covered topic replaces it rather than adding another`() =
        runTest(dispatcher) {
            val store = store()
            refusedPlan(store)
            val topics = FakeTopicSender(mutableListOf(SendOutcome.Failed(null), SendOutcome.Failed(null)))
            val roster = AttendanceViewModel(Attendance(), Sessions(), store)
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
            model.open(started)
            advanceUntilIdle()
            model.saveAsCovered()
            advanceUntilIdle()

            model.typeTopic("Friction")
            model.save()
            advanceUntilIdle()

            val queued = store.read().filter { it.target == QueueTarget.TOPIC }
            assertEquals(listOf("Friction"), queued.map { it.topic })
        }

    @Test
    fun `the topic saves offline from the calendar payload when the roster cannot load`() =
        runTest(dispatcher) {
            val store = store()
            val topics = FakeTopicSender(mutableListOf(SendOutcome.Failed(null)))
            val offline =
                object : SessionsRepository by FakeSessions() {
                    override suspend fun sessionDetail(sessionId: String) = AuthResult.TransportFailure
                }
            val roster = AttendanceViewModel(Attendance(), offline, store)
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
            model.open(calendarClass(state = CalendarState.TODAY, recordable = true, topicVersion = 4))
            advanceUntilIdle()
            model.typeTopic("Newton")

            model.save()
            advanceUntilIdle()

            assertEquals(4, topics.sent.single().baseVersion)
            assertEquals(listOf(QueueTarget.TOPIC), store.read().map { it.target })
            assertEquals(SaveResult.QUEUED, model.state.value?.result)
        }

    @Test
    fun `Save of unchanged queued words reports queued, not sent`() = runTest(dispatcher) {
        val store = store()
        store.enqueue(QueuedWrite.topic("s-1", 3, "Queued words", notes = "Queued notes"))
        val topics = FakeTopicSender()
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(FakeTopicSender()))
        model.open(today)
        advanceUntilIdle()

        model.save()
        advanceUntilIdle()

        assertEquals(0, topics.sent.size)
        assertEquals(SaveResult.QUEUED, model.state.value?.result)
    }

    @Test
    fun `a refused topic is an error with the words kept, and Save works again after editing`() =
        runTest(dispatcher) {
            val store = store()
            val cancelled = SendOutcome.Conflicted(3, envelope("teaching.session.cancelled", "SESSION_CANCELLED"))
            val topics = FakeTopicSender(mutableListOf(cancelled))
            val roster = AttendanceViewModel(Attendance(), Sessions(), store)
            val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(topics))
            model.open(today)
            advanceUntilIdle()
            model.typeTopic("Gravity")

            model.save()
            advanceUntilIdle()

            assertNull(model.state.value?.result)
            assertEquals("teaching.session.cancelled", model.state.value?.errorKey)
            assertEquals("Gravity", model.state.value?.topic)
            assertTrue(store.read().none { it.target == QueueTarget.TOPIC })

            model.typeTopic("Gravity, again")
            model.save()
            advanceUntilIdle()

            assertEquals(listOf("Gravity", "Gravity, again"), topics.sent.map { it.topic })
            assertEquals(SaveResult.SENT, model.state.value?.result)
            assertNull(model.state.value?.errorKey)
        }

    @Test
    fun `a changed subject is written before the topic`() = runTest(dispatcher) {
        val store = store()
        val subjects = listOf(SubjectOptionDto("sub-1", "Physics"), SubjectOptionDto("sub-2", "Maths"))
        val topics = FakeTopicSender(options = subjects)
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(topics))
        model.open(today, batchId = "b-1")
        advanceUntilIdle()
        assertEquals("sub-1", model.state.value?.subjectId)

        model.chooseSubject("sub-2")
        model.save()
        advanceUntilIdle()

        assertEquals<List<Pair<String, String?>>>(listOf("s-1" to "sub-2"), topics.subjectWrites)
        assertEquals("Maths", model.state.value?.clazz?.subjectName)
        assertEquals(SaveResult.SENT, model.state.value?.result)
    }

    @Test
    fun `a subject the server refuses is shown, and the topic still saves`() = runTest(dispatcher) {
        val store = store()
        val subjects = listOf(SubjectOptionDto("sub-1", "Physics"), SubjectOptionDto("sub-2", "Maths"))
        val topics =
            FakeTopicSender(
                options = subjects,
                subjectAnswer = AuthResult.Refused(envelope("teaching.subject.not_in_batch")),
            )
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = ClassDayViewModel(roster, TopicWriter(store, topics), store, ClassSubjects(topics))
        model.open(today, batchId = "b-1")
        advanceUntilIdle()

        model.chooseSubject("sub-2")
        model.save()
        advanceUntilIdle()

        assertEquals("teaching.subject.not_in_batch", model.state.value?.errorKey)
        assertEquals("Physics", model.state.value?.clazz?.subjectName)
        assertEquals(1, topics.sent.size)
    }

    @Test
    fun `topics and notes are cut at 2000 characters`() = runTest(dispatcher) {
        val store = store()
        val roster = AttendanceViewModel(Attendance(), Sessions(), store)
        val model = dayModel(roster, store)
        model.open(today)

        model.typeTopic("t".repeat(2001))
        model.typeNotes("n".repeat(2500))

        assertEquals(2000, model.state.value?.topic?.length)
        assertEquals(2000, model.state.value?.notes?.length)
    }

    @Test
    fun `reopening a class with a queued topic shows the queued words, not the server's`() =
        runTest(dispatcher) {
            val store = store()
            store.enqueue(QueuedWrite.topic("s-1", 3, "Queued words", notes = "Queued notes"))
            val roster = AttendanceViewModel(Attendance(), Sessions(), store)
            val model = dayModel(roster, store)

            model.open(calendarClass(state = CalendarState.TODAY, topic = "Stale", recordable = true))
            advanceUntilIdle()

            assertEquals("Queued words", model.state.value?.topic)
            assertEquals("Queued notes", model.state.value?.notes)
        }
}
