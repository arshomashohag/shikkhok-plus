package com.shikkhokplus.app.core.session

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.LensEntryDto
import com.shikkhokplus.app.core.network.MeDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The routing decision, which is where a wrong answer sends a person
 * to a screen the server refuses.
 *
 * Written **test-first**: the correct output is knowable from the
 * requirement without the implementation, and a wrong answer is an
 * authorization error — both halves of the predicate `team.md` sets
 * for test-first, so this is not optional here.
 */
class SessionStateMapperTest {

    private fun me(vararg lenses: Pair<String, Int>) =
        MeDto(lenses = lenses.map { LensEntryDto(it.first, it.second) })

    @Test
    fun `one lens skips the picker`() {
        // The server documents a single-entry list as exactly this
        // cue. Asking someone to choose between one thing is a tap
        // that teaches them nothing.
        val state = SessionStateMapper.afterLoad(me("teacher" to 3))

        assertEquals(SessionUiState.Ready(Lens.TEACHER), state)
    }

    @Test
    fun `two lenses offer a choice rather than picking one`() {
        // **The decision the server deliberately does not make**
        // [TC-11, D-2]. Choosing here would be a stored role by
        // another name, and a parent-teacher would always land on
        // whichever side the client happened to prefer.
        val state =
            SessionStateMapper.afterLoad(me("teacher" to 3, "guardian" to 1))

        val choosing = assertIs<SessionUiState.Choosing>(state)
        assertEquals(2, choosing.options.size)
    }

    @Test
    fun `the server's order is preserved, not sorted`() {
        // The server fixes the order so the picker does not reshuffle
        // between sign-ins as counts change. Sorting by count here
        // would reintroduce exactly that, and the guardian entry has
        // the LARGER count precisely so a count sort would show.
        val state =
            SessionStateMapper.afterLoad(me("teacher" to 1, "guardian" to 9))

        val choosing = assertIs<SessionUiState.Choosing>(state)
        assertEquals(
            listOf(Lens.TEACHER, Lens.GUARDIAN),
            choosing.options.map { it.lens },
        )
    }

    @Test
    fun `no lens is its own state, not a failure`() {
        // **A fresh signup legitimately holds no seat** until a
        // teacher adds them. Reporting this as an error would invite
        // them to retry forever against a correct answer.
        assertEquals(SessionUiState.NoLens, SessionStateMapper.afterLoad(me()))
    }

    @Test
    fun `an unknown lens kind is dropped, not fatal`() {
        // A server that adds a fourth lens should leave this app on
        // the three it understands rather than signing the person out.
        val state = SessionStateMapper.afterLoad(me("teacher" to 1, "warden" to 2))

        assertEquals(SessionUiState.Ready(Lens.TEACHER), state)
    }

    @Test
    fun `a list of only unknown kinds reads as no lens`() {
        // The honest answer: this app can open none of what was
        // offered. Routing to a teacher home would be worse.
        assertEquals(
            SessionUiState.NoLens,
            SessionStateMapper.afterLoad(me("warden" to 2)),
        )
    }

    @Test
    fun `the count travels with the lens`() {
        // The counts are what let a parent-teacher tell the two rows
        // apart; dropping them leaves two rows named by role alone.
        val state =
            SessionStateMapper.afterLoad(me("teacher" to 3, "student" to 2))

        val choosing = assertIs<SessionUiState.Choosing>(state)
        assertEquals(
            listOf(LensOption(Lens.TEACHER, 3), LensOption(Lens.STUDENT, 2)),
            choosing.options,
        )
    }

    @Test
    fun `a single lens is not reported as switchable`() {
        // `fromPicker` decides whether "Switch role" appears. A person
        // with one lens offered it would reach a picker that picks for
        // them and returns.
        val state = assertIs<SessionUiState.Ready>(
            SessionStateMapper.afterLoad(me("student" to 1)),
        )

        assertEquals(false, state.fromPicker)
    }

    @Test
    fun `a refusal keeps the server's retryable`() {
        // The client is told whether to retry and never decides [TC-9].
        val state =
            SessionStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "FORBIDDEN",
                        retryable = false,
                        messageKey = "error.forbidden",
                    ),
                ),
            )

        val failed = assertIs<SessionUiState.Failed>(state)
        assertEquals("error.forbidden", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is always retryable`() {
        // Nothing refused it, so there is no server decision to
        // respect -- unlike a refusal, where there is.
        val failed =
            assertIs<SessionUiState.Failed>(
                SessionStateMapper.afterTransportFailure(),
            )

        assertTrue(failed.retryable)
        assertEquals(SessionStateMapper.OFFLINE_KEY, failed.messageKey)
    }

    @Test
    fun `lens parsing accepts the server's casing and rejects nonsense`() {
        assertEquals(Lens.TEACHER, Lens.parse("teacher"))
        assertEquals(Lens.GUARDIAN, Lens.parse("GUARDIAN"))
        assertEquals(null, Lens.parse("admin"))
        assertEquals(null, Lens.parse(""))
    }
}
