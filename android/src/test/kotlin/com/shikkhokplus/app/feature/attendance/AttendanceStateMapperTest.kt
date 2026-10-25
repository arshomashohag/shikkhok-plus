package com.shikkhokplus.app.feature.attendance

import com.shikkhokplus.app.core.network.ConflictDetailDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueueState
import com.shikkhokplus.app.core.queue.QueuedWrite
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The attendance mapping decisions, which is where this screen's
 * behaviour lives.
 *
 * Targeting the mapper rather than "the ViewModel" is what `team.md`
 * asks for: the decisions are here and are reachable without a
 * dispatcher.
 *
 * The three assertions that matter most are the ones where the natural
 * implementation passes a weaker test:
 *
 * * a queued write never maps to confirmed [BR3.1];
 * * a refusal maps to conflicted and never to failed [BR3.6];
 * * the teacher's offline entry survives into the conflict state
 *   [BR3.6].
 */
class AttendanceStateMapperTest {

    private fun session(
        sessionId: String = "s-1",
        status: String = "scheduled",
        version: Int = 7,
    ): SessionDto =
        SessionDto(
            sessionId = sessionId,
            date = "12 May",
            startTime = "16:00",
            origin = "recurrence",
            status = status,
            attendanceVersion = version,
        )

    private fun detail(
        seats: List<RosterSeatDto> =
            listOf(
                RosterSeatDto("e-1", "Rahim"),
                RosterSeatDto("e-2", "Karim"),
            ),
        writable: Boolean = true,
        version: Int = 7,
    ): SessionDetailDto =
        SessionDetailDto(
            session = session(version = version),
            seats = seats,
            writable = writable,
        )

    private fun queued(
        state: QueueState = QueueState.QUEUED,
        entries: List<AttendanceEntry> =
            listOf(AttendanceEntry("e-1", true), AttendanceEntry("e-2", false)),
    ): QueuedWrite =
        QueuedWrite.attendance("s-1", 7, entries).copy(state = state)

    private fun envelope(
        code: String = AttendanceStateMapper.VERSION_CONFLICT_CODE,
        retryable: Boolean = false,
        key: String = "attendance.version_conflict",
    ): ErrorEnvelope =
        ErrorEnvelope(ErrorBody(code = code, retryable = retryable, messageKey = key))

    // ------------------------------------------------------------------
    // The roster defaults [AC3.1.4].
    // ------------------------------------------------------------------

    @Test
    fun `a freshly opened roster has every seat present`() {
        // THE RULE [AC3.1.4]. One of the two structural properties
        // that stand in for the latency target BR7.4 removed: marking
        // a class is mostly confirming attendance, so the roster opens
        // in the state needing the fewest taps.
        val state = AttendanceStateMapper.afterLoad(detail())

        val marking = assertIs<AttendanceUiState.Marking>(state)
        assertEquals(listOf(true, true), marking.seats.map { it.present })
    }

    @Test
    fun `a recorded absence is preserved, not reset to present`() {
        // The default applies to a seat nobody has marked. A recorded
        // `false` is an absence the teacher entered, and resetting it
        // would silently erase their decision.
        val state =
            AttendanceStateMapper.afterLoad(
                detail(
                    seats =
                        listOf(
                            RosterSeatDto("e-1", "Rahim", present = false),
                            RosterSeatDto("e-2", "Karim", present = true),
                        ),
                ),
            )

        val marking = assertIs<AttendanceUiState.Marking>(state)
        assertEquals(listOf(false, true), marking.seats.map { it.present })
    }

    @Test
    fun `writability is read from the server, never derived from status`() {
        // THE RULE [BR1.6, BR5.5]. The server refuses for two reasons
        // -- a cancelled session and an inactive batch -- and a client
        // testing only `status == "cancelled"` would offer a write the
        // server refuses on a scheduled session in a closed batch.
        val state =
            AttendanceStateMapper.afterLoad(detail(writable = false))

        val marking = assertIs<AttendanceUiState.Marking>(state)
        assertEquals(false, marking.writable)
    }

    // ------------------------------------------------------------------
    // Queued never renders as confirmed [BR3.1].
    // ------------------------------------------------------------------

    @Test
    fun `an enqueued write maps to Queued and never to Confirmed`() {
        // **THE RULE** [BR3.1] violation_behaviour (a). This is the
        // whole difference between this queue and the one
        // `project.md` forbids: the forbidden queue has one state and
        // renders it as saved.
        val item = queued()

        val state = AttendanceStateMapper.afterEnqueue(item, "12 May")

        // **The absence is asserted FIRST, before any smart cast.**
        // Written the other way round -- `assertIs<Queued>` and then
        // `state !is Confirmed` -- the second check is statically true
        // after the cast and asserts nothing at all, which the Kotlin
        // compiler reports as "check is always true". That is the
        // "test that passes regardless of implementation" shape this
        // project rejects, and it is easy to write by accident here.
        assertFalse(
            state is AttendanceUiState.Confirmed,
            "an unsent write must never render as confirmed",
        )
        val queuedState = assertIs<AttendanceUiState.Queued>(state)
        assertEquals(item.id, queuedState.itemId)
    }

    @Test
    fun `a pending item badges the roster in its own state`() {
        // Each of the four states produces its own label, so the
        // screen can render them distinctly [BR3.2, AC3.1.10].
        val labels =
            QueueState.entries.map { state ->
                val mapped =
                    AttendanceStateMapper.afterLoad(detail(), queued(state = state))
                val marking = assertIs<AttendanceUiState.Marking>(mapped)
                marking.queued?.labelKey
            }

        assertEquals(
            listOf(
                "queue.state.queued",
                "queue.state.confirmed",
                "queue.state.failed",
                "queue.state.conflicted",
            ),
            labels,
        )
        assertEquals(4, labels.distinct().size, "the four states must be distinguishable")
    }

    @Test
    fun `a queued write's own marks are shown, not the server's stale ones`() {
        // BR3.6 requires the offline entry to be preserved, and
        // preservation starts at the open rather than at the conflict.
        // Showing the server's roster over the teacher's would make
        // their marking look lost.
        val state =
            AttendanceStateMapper.afterLoad(
                detail(
                    seats =
                        listOf(
                            RosterSeatDto("e-1", "Rahim", present = true),
                            RosterSeatDto("e-2", "Karim", present = true),
                        ),
                ),
                queued(
                    entries =
                        listOf(
                            AttendanceEntry("e-1", false),
                            AttendanceEntry("e-2", true),
                        ),
                ),
            )

        val marking = assertIs<AttendanceUiState.Marking>(state)
        assertEquals(listOf(false, true), marking.seats.map { it.present })
    }

    @Test
    fun `roster membership stays the server's even with a queued write`() {
        // BR1.5: membership is a four-clause predicate over
        // inactive_from, student_decision and joined_on, run in one
        // indexed query server-side. A queue entry for a seat that has
        // left the batch must not resurrect it.
        val state =
            AttendanceStateMapper.afterLoad(
                detail(seats = listOf(RosterSeatDto("e-1", "Rahim"))),
                queued(
                    entries =
                        listOf(
                            AttendanceEntry("e-1", true),
                            AttendanceEntry("e-gone", true),
                        ),
                ),
            )

        val marking = assertIs<AttendanceUiState.Marking>(state)
        assertEquals(listOf("e-1"), marking.seats.map { it.enrollmentId })
    }

    // ------------------------------------------------------------------
    // Conflicted is not failed [BR3.6].
    // ------------------------------------------------------------------

    @Test
    fun `a version conflict maps to Conflicted and never to Failed`() {
        // **THE RULE** [BR3.6]. `failed` means "try again" and would
        // invite a retry guaranteed to be refused again -- or a retry
        // wrapper that strips the version and overwrites.
        val item = queued()
        val detail =
            ConflictDetailDto(
                expectedVersion = 7,
                currentVersion = 8,
                currentState = listOf(RosterSeatDto("e-1", "Rahim", present = true)),
            )

        val state =
            AttendanceStateMapper.afterConflict(item, "12 May", detail, envelope())

        // Asserted BEFORE the smart cast, for the reason given above:
        // after `assertIs<Conflicted>` the compiler knows `state` is
        // not `Failed`, so the check would be a tautology.
        assertFalse(
            state is AttendanceUiState.Failed,
            "a conflict must not render as a failure, because the remedies differ",
        )
        val conflicted = assertIs<AttendanceUiState.Conflicted>(state)
        assertEquals(8, conflicted.currentVersion)
    }

    @Test
    fun `the teacher's own entry survives into the conflict state`() {
        // THE RULE [BR3.6]: the offline entry is retained until the
        // teacher explicitly re-applies or discards. A conflict screen
        // showing only the server's roster would have discarded it
        // silently.
        val item =
            queued(
                entries =
                    listOf(
                        AttendanceEntry("e-1", false),
                        AttendanceEntry("e-2", false),
                    ),
            )
        val detail =
            ConflictDetailDto(
                expectedVersion = 7,
                currentVersion = 8,
                currentState =
                    listOf(
                        RosterSeatDto("e-1", "Rahim", present = true),
                        RosterSeatDto("e-2", "Karim", present = true),
                    ),
            )

        val conflicted =
            assertIs<AttendanceUiState.Conflicted>(
                AttendanceStateMapper.afterConflict(item, "12 May", detail, envelope()),
            )

        assertEquals(listOf(false, false), conflicted.mine.map { it.present })
        assertEquals(listOf(true, true), conflicted.theirs.map { it.present })
        // Nothing is merged: the two rosters stay two rosters.
        assertNotEquals(conflicted.mine, conflicted.theirs)
    }

    @Test
    fun `the conflict screen names seats from the server's roster`() {
        // The queue holds no names [security-design § 7.1], so the
        // names come from the refusal's current_state. A blank name
        // would leave the row unreadable.
        val item = queued(entries = listOf(AttendanceEntry("e-1", false)))
        val detail =
            ConflictDetailDto(
                expectedVersion = 7,
                currentVersion = 8,
                currentState = listOf(RosterSeatDto("e-1", "Rahim", present = true)),
            )

        val conflicted =
            assertIs<AttendanceUiState.Conflicted>(
                AttendanceStateMapper.afterConflict(item, "12 May", detail, envelope()),
            )

        assertEquals("Rahim", conflicted.mine.single().displayName)
    }

    @Test
    fun `a refusal with another code is a failure, not a conflict`() {
        // Showing the conflict screen for an inactive-batch refusal
        // would offer a re-apply that cannot work.
        val state =
            AttendanceStateMapper.afterConflict(
                queued(),
                "12 May",
                ConflictDetailDto(7, 8),
                envelope(code = "BATCH_INACTIVE", retryable = false, key = "fees.not_available"),
            )

        assertIs<AttendanceUiState.Failed>(state)
    }

    // ------------------------------------------------------------------
    // The error paths.
    // ------------------------------------------------------------------

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val failed =
            assertIs<AttendanceUiState.Failed>(
                AttendanceStateMapper.afterError(
                    envelope(code = "X", retryable = true, key = "error.unexpected"),
                    itemId = "q-1",
                ),
            )

        assertEquals(true, failed.retryable)
        assertEquals("error.unexpected", failed.messageKey)
        assertEquals("q-1", failed.itemId)
    }

    @Test
    fun `a transport failure on a read is retryable and is not queued`() {
        // Reads do not queue [BR3.1]: only the two mid-class write
        // paths do, and a queued read would be a cache this unit does
        // not build.
        val failed =
            assertIs<AttendanceUiState.Failed>(
                AttendanceStateMapper.afterTransportFailure(),
            )

        assertEquals(AttendanceStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }

    @Test
    fun `the applied state carries the server's new version`() {
        assertEquals(
            AttendanceUiState.Confirmed(8),
            AttendanceStateMapper.afterApplied(8),
        )
    }
}
