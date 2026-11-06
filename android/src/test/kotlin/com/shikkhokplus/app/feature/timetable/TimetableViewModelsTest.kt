package com.shikkhokplus.app.feature.timetable

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.RoomDto
import com.shikkhokplus.app.core.network.TimetableClassDto
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
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The centre timetable: a week, changing one class, swapping teachers, and rooms. */
@OptIn(ExperimentalCoroutinesApi::class)
class TimetableViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : TimetableRepository {
        var classes: List<TimetableClassDto> =
            listOf(
                klass("c-1", "2026-11-06", "16:00"),
                klass("c-2", "2026-11-06", "17:00"),
                klass("c-3", "2026-11-07", "16:00"),
            )
        var writeResult: AuthResult<TimetableClassDto> = AuthResult.Ok(klass("c-1", "2026-11-06", "16:00"))
        var swapResult: AuthResult<List<TimetableClassDto>> = AuthResult.Ok(emptyList())
        var roomsResult: AuthResult<List<RoomDto>> =
            AuthResult.Ok(listOf(RoomDto("r-1", "Room A"), RoomDto("r-2", "Old room", archived = true)))
        var roomWrite: AuthResult<RoomDto> = AuthResult.Ok(RoomDto("r-3", "Room B"))
        val ranges = mutableListOf<Pair<String, String>>()
        val assigned = mutableListOf<Triple<String, String?, String?>>()
        val swapped = mutableListOf<Pair<String, String>>()
        val added = mutableListOf<String>()
        val archived = mutableListOf<Pair<String, Boolean>>()

        override suspend fun timetable(from: String, to: String): AuthResult<List<TimetableClassDto>> {
            ranges += from to to
            return AuthResult.Ok(classes)
        }

        override suspend fun members(): AuthResult<List<MemberDto>> =
            AuthResult.Ok(
                listOf(
                    MemberDto("m-1", "Karim", "+880", "teacher", "accepted"),
                    MemberDto("m-2", "Salma", "+880", "teacher", "pending"),
                    MemberDto("m-3", "Gone", "+880", "teacher", "accepted", revoked = true),
                    MemberDto("m-4", "No", "+880", "teacher", "declined"),
                ),
            )

        override suspend fun rooms(): AuthResult<List<RoomDto>> = roomsResult

        override suspend fun assign(
            sessionId: String,
            teacherMemberId: String?,
            roomId: String?,
        ): AuthResult<TimetableClassDto> {
            assigned += Triple(sessionId, teacherMemberId, roomId)
            return writeResult
        }

        override suspend fun swap(first: String, second: String): AuthResult<List<TimetableClassDto>> {
            swapped += first to second
            return swapResult
        }

        override suspend fun addRoom(name: String): AuthResult<RoomDto> {
            added += name
            return roomWrite
        }

        override suspend fun archiveRoom(roomId: String, archived: Boolean): AuthResult<RoomDto> {
            this.archived += roomId to archived
            return roomWrite
        }

        companion object {
            fun klass(id: String, date: String, start: String, status: String = "scheduled") =
                TimetableClassDto(
                    sessionId = id,
                    batchId = "b-1",
                    batchName = "Physics",
                    date = date,
                    startTime = start,
                    status = status,
                    teacherMemberId = "m-1",
                    teacherName = "Karim",
                )
        }
    }

    private fun model(fake: Fake) = TimetableViewModel(fake, today = "2026-11-06")

    @Test
    fun `a week is seven days from today, every day present, with live teachers and rooms`() = runTest(dispatcher) {
        val fake = Fake()
        val model = model(fake)
        model.load()
        advanceUntilIdle()

        assertEquals(listOf("2026-11-06" to "2026-11-12"), fake.ranges)
        val days = assertIs<TimetableBody.Loaded>(model.state.value.body).days
        assertEquals(7, days.size)
        assertEquals(listOf("c-1", "c-2"), days.first().second.map { it.sessionId })
        assertEquals(listOf("m-1", "m-2"), model.state.value.teachers.map { it.memberId })
        assertEquals(listOf("r-1"), model.state.value.rooms.map { it.roomId })
    }

    @Test
    fun `stepping a week reads the next seven days, across a month`() = runTest(dispatcher) {
        val fake = Fake()
        val model = TimetableViewModel(fake, today = "2026-11-28")
        model.shift(1)
        advanceUntilIdle()

        assertEquals("2026-12-05", model.state.value.weekStart)
        assertEquals("2026-12-05" to "2026-12-11", fake.ranges.last())
    }

    @Test
    fun `changing one class sends its teacher and room`() = runTest(dispatcher) {
        val fake = Fake()
        val model = model(fake)
        model.load()
        advanceUntilIdle()

        model.open("c-1")
        model.teacher("m-2")
        model.room("r-1")
        model.save()
        advanceUntilIdle()

        assertEquals(listOf<Triple<String, String?, String?>>(Triple("c-1", "m-2", "r-1")), fake.assigned)
        assertNull(model.state.value.change)
        assertEquals(2, fake.ranges.size, "the week is read again")
    }

    @Test
    fun `a teacher or room the pickers do not offer is ignored, and nobody can be chosen`() = runTest(dispatcher) {
        val fake = Fake()
        val model = model(fake)
        model.load()
        advanceUntilIdle()
        model.open("c-1")

        model.teacher("m-3")
        model.room("r-2")
        assertEquals("m-1", model.state.value.change?.teacherMemberId)
        assertNull(model.state.value.change?.roomId)

        model.teacher(null)
        assertNull(model.state.value.change?.teacherMemberId)
    }

    @Test
    fun `a swap is offered with the same day's other classes and sent instead`() = runTest(dispatcher) {
        val fake = Fake()
        fake.classes = fake.classes + Fake.klass("c-4", "2026-11-06", "18:00", status = "cancelled")
        val model = model(fake)
        model.load()
        advanceUntilIdle()

        model.open("c-1")
        assertEquals(listOf("c-2"), model.state.value.swapCandidates.map { it.sessionId })
        model.swapWith("c-3")
        assertNull(model.state.value.change?.swapWith, "another day's class cannot be swapped")
        model.swapWith("c-2")
        model.save()
        advanceUntilIdle()

        assertEquals(listOf("c-1" to "c-2"), fake.swapped)
        assertTrue(fake.assigned.isEmpty())
    }

    @Test
    fun `a clash is refused with the other class named and the sheet stays open`() = runTest(dispatcher) {
        val fake = Fake()
        fake.writeResult =
            AuthResult.Refused(
                ErrorEnvelope(
                    ErrorBody(
                        "CLASS_CLASH",
                        false,
                        "schedule.clash",
                        details = mapOf("batch" to "Chemistry", "start_time" to "16:30"),
                    ),
                ),
            )
        val model = model(fake)
        model.load()
        advanceUntilIdle()
        model.open("c-1")
        model.save()
        advanceUntilIdle()

        assertEquals(TimetableFailure("schedule.clash", "Chemistry", "16:30"), model.state.value.failure)
        assertEquals("c-1", model.state.value.change?.target?.sessionId)
    }

    @Test
    fun `a cancelled class cannot be changed`() = runTest(dispatcher) {
        val fake = Fake()
        fake.classes = listOf(Fake.klass("c-9", "2026-11-06", "16:00", status = "cancelled"))
        val model = model(fake)
        model.load()
        advanceUntilIdle()

        model.open("c-9")

        assertNull(model.state.value.change)
    }

    @Test
    fun `rooms are added and stopped, and the list is read again`() = runTest(dispatcher) {
        val fake = Fake()
        val model = RoomsViewModel(fake)
        model.load()
        advanceUntilIdle()
        assertEquals(2, model.state.value.rooms.size)

        model.name("  Room B ")
        model.add()
        advanceUntilIdle()
        model.archive("r-1", archived = true)
        advanceUntilIdle()

        assertEquals(listOf("Room B"), fake.added)
        assertEquals(listOf("r-1" to true), fake.archived)
        assertEquals("", model.state.value.typedName)
    }

    @Test
    fun `a refused room says why`() = runTest(dispatcher) {
        val fake = Fake()
        fake.roomWrite = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "room.name_taken")))
        val model = RoomsViewModel(fake)
        model.load()
        advanceUntilIdle()
        model.name("Room A")
        model.add()
        advanceUntilIdle()

        assertEquals("room.name_taken", model.state.value.failureKey)
        assertEquals("Room A", model.state.value.typedName)
    }
}
