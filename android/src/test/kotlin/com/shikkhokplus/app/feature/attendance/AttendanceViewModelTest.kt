package com.shikkhokplus.app.feature.attendance

import com.shikkhokplus.app.core.network.ConflictDetailDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.sessions.SessionsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The attendance state machine, including the explicit retry path for
 * a failed write [TC-8, D-9].
 *
 * `team.md` requires every ViewModel to ship tests for loading,
 * success, error and that retry path. The queue adds two more that
 * matter at least as much: a conflicted item is not retried, and
 * re-applying one sends a fresh mutation id.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AttendanceViewModelTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun store(): QueueStore = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    private fun detail(version: Int = 7): SessionDetailDto =
        SessionDetailDto(
            session =
                SessionDto(
                    sessionId = "s-1",
                    date = "12 May",
                    startTime = "16:00",
                    origin = "recurrence",
                    status = "scheduled",
                    attendanceVersion = version,
                ),
            seats = listOf(RosterSeatDto("e-1", "Rahim"), RosterSeatDto("e-2", "Karim")),
            writable = true,
        )

    private class FakeSessions(
        private val result: AuthResult<SessionDetailDto>,
    ) : SessionsRepository {
        override suspend fun sessions(batchId: String) = AuthResult.Ok(emptyList<SessionDto>())

        override suspend fun sessionDetail(sessionId: String) = result

        override suspend fun createAdHoc(
            batchId: String,
            date: String,
            startTime: String,
            batchSubjectId: String?,
        ) = AuthResult.Ok(Unit)

        override suspend fun reschedule(sessionId: String, date: String, startTime: String) =
            AuthResult.Ok(Unit)

        override suspend fun cancel(sessionId: String) = AuthResult.Ok(Unit)
    }

    private class FakeAttendance(
        private val outcomes: MutableList<SendOutcome>,
        private val detail: ConflictDetailDto? = null,
    ) : AttendanceRepository {
        val sent: MutableList<QueuedWrite> = mutableListOf()

        override suspend fun submit(item: QueuedWrite): SendOutcome {
            sent += item
            return outcomes.removeFirstOrNull() ?: SendOutcome.Applied(item.baseVersion + 1)
        }

        override suspend fun conflictDetail(sessionId: String) =
            detail?.let { AuthResult.Ok(it) } ?: AuthResult.TransportFailure
    }

    private fun conflictEnvelope(): ErrorEnvelope =
        ErrorEnvelope(
            ErrorBody(
                code = AttendanceStateMapper.VERSION_CONFLICT_CODE,
                retryable = false,
                messageKey = "attendance.version_conflict",
            ),
        )

    @Test
    fun `a toggle changes one seat and sends nothing`() = runTest(dispatcher) {
        // **Nothing leaves the device on a tap** [BR3.5]. A teacher
        // marks a whole roster and commits it once; a send per toggle
        // would be the per-seat queue the rule forbids, and mid-class
        // it would be a request per tap on a phone that may have no
        // signal.
        val transport = FakeAttendance(mutableListOf())
        val model =
            AttendanceViewModel(transport, FakeSessions(AuthResult.Ok(detail())), store())
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        val before = assertIs<AttendanceUiState.Marking>(model.state.value)
        val seat = before.seats.first()
        model.toggle(seat, !seat.present)

        val after = assertIs<AttendanceUiState.Marking>(model.state.value)
        assertEquals(!seat.present, after.seats.first().present)
        // Every other seat is untouched.
        assertEquals(before.seats.drop(1), after.seats.drop(1))
        assertEquals(emptyList(), transport.sent)
    }

    @Test
    fun `a toggle is ignored outside marking`() = runTest(dispatcher) {
        val model =
            AttendanceViewModel(
                FakeAttendance(mutableListOf()),
                FakeSessions(AuthResult.TransportFailure),
                store(),
            )
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        val failed = model.state.value
        model.toggle(AttendanceSeat("e-1", "Rafi", present = true), present = false)

        assertEquals(failed, model.state.value)
    }

    @Test
    fun `loading then success`() = runTest(dispatcher) {
        val model =
            AttendanceViewModel(
                FakeAttendance(mutableListOf()),
                FakeSessions(AuthResult.Ok(detail())),
                store(),
            )

        model.load("s-1")
        assertEquals(AttendanceUiState.Loading, model.state.value)

        dispatcher.scheduler.advanceUntilIdle()

        val marking = assertIs<AttendanceUiState.Marking>(model.state.value)
        assertEquals(2, marking.seats.size)
        assertEquals(7, marking.attendanceVersion)
    }

    @Test
    fun `a read failure surfaces an error`() = runTest(dispatcher) {
        val model =
            AttendanceViewModel(
                FakeAttendance(mutableListOf()),
                FakeSessions(AuthResult.TransportFailure),
                store(),
            )

        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        val failed = assertIs<AttendanceUiState.Failed>(model.state.value)
        assertEquals(true, failed.retryable)
    }

    @Test
    fun `a submitted roster is queued before it is sent`() = runTest(dispatcher) {
        // **The order is the guarantee** [BR3.1, BR3.2]: a process
        // death between queueing and sending leaves the roster on the
        // device rather than losing it.
        val store = store()
        val model =
            AttendanceViewModel(
                FakeAttendance(mutableListOf(SendOutcome.Applied(8))),
                FakeSessions(AuthResult.Ok(detail())),
                store,
            )
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        model.submit(
            "s-1",
            7,
            listOf(AttendanceSeat("e-1", "Rahim", true), AttendanceSeat("e-2", "Karim", false)),
        )

        // Before the send runs: on the phone, and NOT confirmed.
        assertIs<AttendanceUiState.Queued>(model.state.value)
        assertEquals(1, store.read().size)
        assertEquals(QueueState.QUEUED, store.read().single().state)

        dispatcher.scheduler.advanceUntilIdle()

        assertIs<AttendanceUiState.Confirmed>(model.state.value)
        assertEquals(emptyList(), store.read())
    }

    @Test
    fun `the whole roster goes as one write, never one per seat`() = runTest(dispatcher) {
        // THE RULE [BR3.5]. A per-seat write leaves attendance
        // half-saved after a mid-roster drop, and a retry cannot
        // reconcile that on screen.
        val repository = FakeAttendance(mutableListOf(SendOutcome.Applied(8)))
        val model =
            AttendanceViewModel(repository, FakeSessions(AuthResult.Ok(detail())), store())
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        model.submit(
            "s-1",
            7,
            listOf(AttendanceSeat("e-1", "Rahim", true), AttendanceSeat("e-2", "Karim", false)),
        )
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, repository.sent.size, "the roster commits as one write")
        assertEquals(2, repository.sent.single().entries.size)
    }

    @Test
    fun `a refused write becomes conflicted and stays in the queue`() = runTest(dispatcher) {
        // THE RULE [BR3.6]: the teacher's offline entry is preserved
        // until they explicitly re-apply or discard.
        val store = store()
        val model =
            AttendanceViewModel(
                FakeAttendance(
                    mutableListOf(SendOutcome.Conflicted(8, conflictEnvelope())),
                    detail =
                        ConflictDetailDto(
                            expectedVersion = 7,
                            currentVersion = 8,
                            currentState =
                                listOf(RosterSeatDto("e-1", "Rahim", present = true)),
                        ),
                ),
                FakeSessions(AuthResult.Ok(detail())),
                store,
            )
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        model.submit("s-1", 7, listOf(AttendanceSeat("e-1", "Rahim", false)))
        dispatcher.scheduler.advanceUntilIdle()

        val conflicted = assertIs<AttendanceUiState.Conflicted>(model.state.value)
        assertEquals(8, conflicted.currentVersion)
        assertEquals(listOf(false), conflicted.mine.map { it.present })
        assertEquals(listOf(true), conflicted.theirs.map { it.present })
        assertEquals(QueueState.CONFLICTED, store.read().single().state)
    }

    @Test
    fun `retry does nothing for a conflicted item`() = runTest(dispatcher) {
        // **The assertion that separates correct from
        // nearly-correct** [BR3.6]. Retrying a stale version is
        // guaranteed to be refused again, and the retry control is
        // where a version-stripping wrapper gets added.
        val store = store()
        val conflicted =
            QueuedWrite.attendance("s-1", 7, emptyList())
                .copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 8)
        store.enqueue(conflicted)
        val repository = FakeAttendance(mutableListOf())
        val model =
            AttendanceViewModel(repository, FakeSessions(AuthResult.Ok(detail())), store)

        model.retry(conflicted.id)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(emptyList(), repository.sent, "a conflict must not be retried as-is")
        assertEquals(QueueState.CONFLICTED, store.read().single().state)
    }

    @Test
    fun `the explicit retry path resends a failed write`() = runTest(dispatcher) {
        // The path `team.md` names for every ViewModel [TC-8, D-9]:
        // a failed write surfaces an explicit retry rather than
        // succeeding locally and reconciling later.
        val store = store()
        val repository =
            FakeAttendance(
                mutableListOf(SendOutcome.Failed(null), SendOutcome.Applied(8)),
            )
        val model =
            AttendanceViewModel(repository, FakeSessions(AuthResult.Ok(detail())), store)
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        model.submit("s-1", 7, listOf(AttendanceSeat("e-1", "Rahim", true)))
        dispatcher.scheduler.advanceUntilIdle()

        val failed = assertIs<AttendanceUiState.Failed>(model.state.value)
        val itemId = requireNotNull(failed.itemId)
        assertEquals(QueueState.FAILED, store.read().single().state)

        model.retry(itemId)
        dispatcher.scheduler.advanceUntilIdle()

        assertIs<AttendanceUiState.Confirmed>(model.state.value)
        assertEquals(2, repository.sent.size)
    }

    @Test
    fun `re-apply sends a NEW write with a fresh client_mutation_id`() = runTest(dispatcher) {
        // **THE RULE this unit gets wrong by default** [BR3.7],
        // asserted end to end rather than only on the value object.
        // Reusing the id would take the server's replay path, return
        // the ORIGINAL stored result with 200, and change nothing --
        // reporting success for the opposite of what the teacher
        // asked.
        val store = store()
        val repository =
            FakeAttendance(
                mutableListOf(
                    SendOutcome.Conflicted(8, conflictEnvelope()),
                    SendOutcome.Applied(9),
                ),
                detail = ConflictDetailDto(7, 8, listOf(RosterSeatDto("e-1", "Rahim", true))),
            )
        val model =
            AttendanceViewModel(repository, FakeSessions(AuthResult.Ok(detail())), store)
        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        model.submit("s-1", 7, listOf(AttendanceSeat("e-1", "Rahim", false)))
        dispatcher.scheduler.advanceUntilIdle()

        val conflicted = assertIs<AttendanceUiState.Conflicted>(model.state.value)
        val refused = repository.sent.single()

        model.reapply(conflicted.itemId)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, repository.sent.size)
        val reapplied = repository.sent[1]
        assertNotEquals(
            refused.clientMutationId,
            reapplied.clientMutationId,
            "reusing the mutation id replays and changes nothing",
        )
        assertEquals(8, reapplied.baseVersion, "re-apply carries the CURRENT version")
        // The teacher's marks are what gets re-applied.
        assertEquals(listOf(false), reapplied.entries.map { it.present })
        assertIs<AttendanceUiState.Confirmed>(model.state.value)
    }

    @Test
    fun `discard drops the offline entry and keeps what the server holds`() =
        runTest(dispatcher) {
            val store = store()
            val repository =
                FakeAttendance(
                    mutableListOf(SendOutcome.Conflicted(8, conflictEnvelope())),
                    detail = ConflictDetailDto(7, 8, listOf(RosterSeatDto("e-1", "Rahim", true))),
                )
            val model =
                AttendanceViewModel(repository, FakeSessions(AuthResult.Ok(detail())), store)
            model.load("s-1")
            dispatcher.scheduler.advanceUntilIdle()

            model.submit("s-1", 7, listOf(AttendanceSeat("e-1", "Rahim", false)))
            dispatcher.scheduler.advanceUntilIdle()
            val conflicted = assertIs<AttendanceUiState.Conflicted>(model.state.value)

            model.discard(conflicted.itemId)
            dispatcher.scheduler.advanceUntilIdle()

            assertEquals(emptyList(), store.read())
            // Only one send: discard does not re-send anything.
            assertEquals(1, repository.sent.size)
        }

    @Test
    fun `a queued write is restored on reopening the session`() = runTest(dispatcher) {
        // BR3.2 at the ViewModel: after a restart the teacher's own
        // marks come back, badged as not-yet-sent rather than as
        // confirmed.
        val store = store()
        store.enqueue(
            QueuedWrite.attendance(
                "s-1",
                7,
                listOf(com.shikkhokplus.app.core.queue.AttendanceEntry("e-1", false)),
            ),
        )
        val model =
            AttendanceViewModel(
                FakeAttendance(mutableListOf()),
                FakeSessions(AuthResult.Ok(detail())),
                store,
            )

        model.load("s-1")
        dispatcher.scheduler.advanceUntilIdle()

        val marking = assertIs<AttendanceUiState.Marking>(model.state.value)
        assertEquals("queue.state.queued", marking.queued?.labelKey)
        assertEquals(false, marking.seats.first { it.enrollmentId == "e-1" }.present)
        assertTrue(
            marking.queued != null,
            "a pending write must be visible, never rendered as confirmed",
        )
    }
}
