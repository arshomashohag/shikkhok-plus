package com.shikkhokplus.app.feature.sessions

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SessionDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotEquals

/**
 * The session-list mapping decisions.
 *
 * The one that matters most is BR2.2: `topicLogged` is read from the
 * server and never derived from `topic == null`, because the
 * derivation collapses exactly the two cases the rule exists to keep
 * apart.
 */
class SessionsStateMapperTest {

    private fun session(
        sessionId: String = "s-1",
        status: String = "scheduled",
        origin: String = "recurrence",
        topic: String? = null,
        topicLogged: Boolean = false,
    ): SessionDto =
        SessionDto(
            sessionId = sessionId,
            date = "12 May",
            startTime = "16:00",
            origin = origin,
            status = status,
            topic = topic,
            topicLogged = topicLogged,
        )

    @Test
    fun `each server status maps to its own key`() {
        val labels =
            listOf("scheduled", "held", "cancelled").map { status ->
                val loaded =
                    assertIs<SessionsUiState.Loaded>(
                        SessionsStateMapper.afterLoad("Physics", listOf(session(status = status))),
                    )
                loaded.rows.single().statusLabel
            }

        assertEquals(
            listOf(
                "session.status.scheduled",
                "session.status.held",
                "session.status.cancelled",
            ),
            labels,
        )
    }

    @Test
    fun `an unknown status fails loudly rather than defaulting`() {
        // A fallback here could render a cancelled class as one going
        // ahead, and a teacher would find out at the refusal.
        val state = SessionsStateMapper.afterLoad("Physics", listOf(session(status = "moved")))

        val failed = assertIs<SessionsUiState.Failed>(state)
        assertEquals(SessionsStateMapper.UNEXPECTED_KEY, failed.messageKey)
    }

    @Test
    fun `an unlogged topic is distinguishable from one logged as empty`() {
        // **THE RULE** [BR2.2]. Collapsing the two makes it impossible
        // to tell a class nobody logged from one logged as nothing,
        // which is the whole content of AC3.4.2's "topics covered in
        // each". A client `topic == null` check IS that collapse.
        val never =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session(topic = null, topicLogged = false)),
                ),
            ).rows.single()

        val blank =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session(topic = "", topicLogged = true)),
                ),
            ).rows.single()

        assertEquals(false, never.topicLogged)
        assertEquals(true, blank.topicLogged)
        assertNotEquals(never.topicLogged, blank.topicLogged)
    }

    @Test
    fun `topicLogged is read from the server, not derived from the text`() {
        // The sharper form of the rule: a server that says a topic was
        // logged is believed even when the text is empty, and one that
        // says it was not is believed even if a stale `topic` arrived.
        val row =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session(topic = "", topicLogged = true)),
                ),
            ).rows.single()

        assertEquals(true, row.topicLogged)
        assertEquals("", row.topic)
    }

    @Test
    fun `a cancelled session is marked, decided by the mapper`() {
        // So no composable writes `status == "cancelled"` to choose a
        // control [TC-9, D-31].
        val row =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session(status = "cancelled")),
                ),
            ).rows.single()

        assertEquals(true, row.isCancelled)
    }

    @Test
    fun `an ad-hoc session is marked as the teacher's own`() {
        // BR1.4: generation never creates, modifies or deletes one, so
        // the teacher who created it is the only one who will.
        val row =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session(origin = "ad_hoc")),
                ),
            ).rows.single()

        assertEquals(true, row.isAdHoc)
    }

    @Test
    fun `an empty list is Empty, not Loaded with no rows`() {
        // An empty list and "no classes scheduled" need different
        // screens, and a blank list explains neither.
        assertEquals(
            SessionsUiState.Empty("Physics"),
            SessionsStateMapper.afterLoad("Physics", emptyList()),
        )
    }

    @Test
    fun `sessions are kept in the server's order, never re-sorted`() {
        // Ordering is part of the query [TC-9]. A client sort would
        // differ from the server's tiebreak the moment two sessions
        // share a date.
        val loaded =
            assertIs<SessionsUiState.Loaded>(
                SessionsStateMapper.afterLoad(
                    "Physics",
                    listOf(session("s-3"), session("s-1"), session("s-2")),
                ),
            )

        assertEquals(listOf("s-3", "s-1", "s-2"), loaded.rows.map { it.sessionId })
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val failed =
            assertIs<SessionsUiState.Failed>(
                SessionsStateMapper.afterError(
                    ErrorEnvelope(
                        ErrorBody(
                            code = "SESSION_CANCELLED",
                            retryable = false,
                            messageKey = "fees.not_available",
                        ),
                    ),
                ),
            )

        assertEquals(false, failed.retryable)
        assertEquals("fees.not_available", failed.messageKey)
    }

    @Test
    fun `a transport failure is retryable`() {
        val failed =
            assertIs<SessionsUiState.Failed>(SessionsStateMapper.afterTransportFailure())

        assertEquals(SessionsStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }
}
