package com.shikkhokplus.app.feature.myclasses

import com.shikkhokplus.app.core.network.ClassAttendanceBodyDto
import com.shikkhokplus.app.core.network.ClassAttendanceResultDto
import com.shikkhokplus.app.core.network.ClassRosterDto
import com.shikkhokplus.app.core.network.ClassSeatMarkDto
import com.shikkhokplus.app.core.network.ClassTopicBodyDto
import com.shikkhokplus.app.core.network.ClassTopicResultDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MyClassDto
import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** A centre teacher's classes: the week, and one class's attendance and topic. */
@OptIn(ExperimentalCoroutinesApi::class)
class MyClassesViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : MyClassesRepository {
        var classes: AuthResult<List<MyClassDto>> =
            AuthResult.Ok(
                listOf(
                    klass("c-1", "2026-11-06", "16:00"),
                    klass("c-2", "2026-11-06", "17:00"),
                    klass("c-3", "2026-11-09", "16:00"),
                ),
            )
        var roster: AuthResult<ClassRosterDto> =
            AuthResult.Ok(
                ClassRosterDto(
                    seats =
                        listOf(
                            RosterSeatDto("e-1", "Rafi", present = true),
                            RosterSeatDto("e-2", "Mitu", present = false),
                            RosterSeatDto("e-3", "Nila"),
                        ),
                    attendanceVersion = 3,
                    writable = true,
                    topic = "Vectors",
                    topicVersion = 2,
                ),
            )
        var attendanceResult: AuthResult<ClassAttendanceResultDto> = AuthResult.Ok(ClassAttendanceResultDto(4))
        var topicResult: AuthResult<ClassTopicResultDto> = AuthResult.Ok(ClassTopicResultDto(3))
        val ranges = mutableListOf<Pair<String, String>>()
        val attendance = mutableListOf<ClassAttendanceBodyDto>()
        val topics = mutableListOf<ClassTopicBodyDto>()

        override suspend fun classes(from: String, to: String): AuthResult<List<MyClassDto>> {
            ranges += from to to
            return classes
        }

        override suspend fun roster(sessionId: String): AuthResult<ClassRosterDto> = roster

        override suspend fun submitAttendance(
            sessionId: String,
            body: ClassAttendanceBodyDto,
        ): AuthResult<ClassAttendanceResultDto> {
            attendance += body
            return attendanceResult
        }

        override suspend fun writeTopic(sessionId: String, body: ClassTopicBodyDto): AuthResult<ClassTopicResultDto> {
            topics += body
            return topicResult
        }

        companion object {
            fun klass(id: String, date: String, start: String) =
                MyClassDto(
                    sessionId = id,
                    centreName = "Alo Coaching",
                    batchName = "Physics",
                    date = date,
                    startTime = start,
                    status = "scheduled",
                )
        }
    }

    private val reassigned =
        AuthResult.Refused(ErrorEnvelope(ErrorBody("CLASS_REASSIGNED", false, "class.reassigned")))

    private fun keys(): () -> String {
        var n = 0
        return { "k-${++n}" }
    }

    @Test
    fun `the week lists only days with my classes, in order`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyClassesViewModel(fake, today = "2026-11-06")
        model.load()
        advanceUntilIdle()

        assertEquals(listOf("2026-11-06" to "2026-11-12"), fake.ranges)
        val days = assertIs<MyClassesBody.Loaded>(model.state.value.body).days
        assertEquals(listOf("2026-11-06", "2026-11-09"), days.map { it.first })
        assertEquals(listOf("c-1", "c-2"), days.first().second.map { it.sessionId })
    }

    @Test
    fun `stepping back a week reads the seven days before`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyClassesViewModel(fake, today = "2026-11-06")
        model.shift(-1)
        advanceUntilIdle()

        assertEquals("2026-10-30", model.state.value.weekStart)
        assertEquals("2026-10-30" to "2026-11-05", fake.ranges.last())
    }

    @Test
    fun `an offline read offers a retry`() = runTest(dispatcher) {
        val fake = Fake().apply { classes = AuthResult.TransportFailure }
        val model = MyClassesViewModel(fake, today = "2026-11-06")
        model.load()
        advanceUntilIdle()

        val failed = assertIs<MyClassesBody.Failed>(model.state.value.body)
        assertTrue(failed.retryable)
    }

    @Test
    fun `a roster opens with its recorded absences and topic`() = runTest(dispatcher) {
        val model = MyClassViewModel(Fake(), "c-1", keys())
        model.load()
        advanceUntilIdle()

        assertEquals(setOf("e-2"), model.state.value.absent)
        assertEquals("Vectors", model.state.value.topic)
        assertTrue(model.state.value.writable)
    }

    @Test
    fun `attendance sends every seat, absent ones false, against the version read`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyClassViewModel(fake, "c-1", keys())
        model.load()
        advanceUntilIdle()

        model.toggle("e-1")
        model.toggle("e-2")
        model.saveAttendance()
        advanceUntilIdle()

        val sent = fake.attendance.single()
        assertEquals(3, sent.baseAttendanceVersion)
        assertEquals("k-1", sent.clientMutationId)
        assertEquals(
            listOf(ClassSeatMarkDto("e-1", false), ClassSeatMarkDto("e-2", true), ClassSeatMarkDto("e-3", true)),
            sent.seats,
        )
        val roster = assertIs<MyClassBody.Loaded>(model.state.value.body).roster
        assertEquals(4, roster.attendanceVersion, "the next write is based on the new version")
        assertTrue(model.state.value.saved)
    }

    @Test
    fun `a failed send keeps its replay key, and a saved one gets a fresh key`() = runTest(dispatcher) {
        val fake = Fake().apply { attendanceResult = AuthResult.TransportFailure }
        val model = MyClassViewModel(fake, "c-1", keys())
        model.load()
        advanceUntilIdle()

        model.saveAttendance()
        advanceUntilIdle()
        fake.attendanceResult = AuthResult.Ok(ClassAttendanceResultDto(4))
        model.saveAttendance()
        advanceUntilIdle()
        model.saveAttendance()
        advanceUntilIdle()

        assertEquals(listOf("k-1", "k-1", "k-2"), fake.attendance.map { it.clientMutationId })
        assertEquals(listOf(3, 3, 4), fake.attendance.map { it.baseAttendanceVersion })
    }

    @Test
    fun `a class moved to another teacher is refused with the server's message, nothing kept`() =
        runTest(dispatcher) {
            val fake = Fake().apply { attendanceResult = reassigned }
            val model = MyClassViewModel(fake, "c-1", keys())
            model.load()
            advanceUntilIdle()

            model.saveAttendance()
            advanceUntilIdle()

            assertEquals("class.reassigned", model.state.value.failureKey)
            assertFalse(model.state.value.saved)
            assertEquals(3, assertIs<MyClassBody.Loaded>(model.state.value.body).roster.attendanceVersion)
        }

    @Test
    fun `a closed class cannot be marked or sent`() = runTest(dispatcher) {
        val fake = Fake()
        fake.roster = AuthResult.Ok((fake.roster as AuthResult.Ok).value.copy(writable = false))
        val model = MyClassViewModel(fake, "c-1", keys())
        model.load()
        advanceUntilIdle()

        model.toggle("e-1")
        model.saveAttendance()
        advanceUntilIdle()

        assertEquals(setOf("e-2"), model.state.value.absent)
        assertTrue(fake.attendance.isEmpty())
    }

    @Test
    fun `the topic is sent trimmed as taught, not a plan, and a blank one is not sent`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyClassViewModel(fake, "c-1", keys())
        model.load()
        advanceUntilIdle()

        model.topic("   ")
        model.saveTopic()
        model.topic("  Newton's laws ")
        model.saveTopic()
        advanceUntilIdle()

        val sent = fake.topics.single()
        assertEquals(ClassTopicBodyDto(2, "k-2", "Newton's laws", plan = false), sent)
        val roster = assertIs<MyClassBody.Loaded>(model.state.value.body).roster
        assertEquals(3, roster.topicVersion)
        assertNull(model.state.value.failureKey)
    }

    @Test
    fun `a roster the lens cannot reach lands on the refusal`() = runTest(dispatcher) {
        val fake = Fake().apply { roster = reassigned }
        val model = MyClassViewModel(fake, "c-1", keys())
        model.load()
        advanceUntilIdle()

        val failed = assertIs<MyClassBody.Failed>(model.state.value.body)
        assertEquals("class.reassigned", failed.messageKey)
        assertFalse(failed.retryable)
    }
}
