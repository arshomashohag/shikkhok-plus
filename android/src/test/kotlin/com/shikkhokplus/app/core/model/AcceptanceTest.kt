package com.shikkhokplus.app.core.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The wire vocabulary for roles and acceptance states.
 *
 * These enums carry the exact tokens the API uses, spelled rather than
 * derived from `name.lowercase()`. The tests below are what makes that
 * spelling a contract instead of a coincidence: a rename that silently
 * changed a token would otherwise show up as a 422 on a real device.
 */
class AcceptanceTest {

    @Test
    fun `every role spells the token the api expects`() {
        assertEquals("teacher", SignupRole.TEACHER.wire)
        assertEquals("student", SignupRole.STUDENT.wire)
        assertEquals("guardian", SignupRole.GUARDIAN.wire)
    }

    @Test
    fun `every acceptance state spells the token the api expects`() {
        assertEquals("pending", AcceptanceState.PENDING.wire)
        assertEquals("accepted", AcceptanceState.ACCEPTED.wire)
        assertEquals("declined", AcceptanceState.DECLINED.wire)
    }

    @Test
    fun `an unknown role token reads as null, never as a default`() {
        // The already-added path LOCKS the form to this value [BR4.5],
        // so a default would lock somebody to a role contradicting the
        // seat they actually hold.
        assertNull(SignupRole.fromWire("headmaster"))
        assertNull(SignupRole.fromWire(null))
    }

    @Test
    fun `an unknown state token reads as null, never as pending`() {
        // Defaulting to PENDING would render a seat the person already
        // declined as if they had not been asked.
        assertNull(AcceptanceState.fromWire("archived"))
        assertNull(AcceptanceState.fromWire(null))
    }

    @Test
    fun `every token round-trips through fromWire`() {
        // Guards the two maps above against drifting apart: the
        // spelling test asserts the tokens, and this asserts that each
        // is actually reachable by the parser the app uses.
        SignupRole.entries.forEach { role ->
            assertEquals(role, SignupRole.fromWire(role.wire))
        }
        AcceptanceState.entries.forEach { state ->
            assertEquals(state, AcceptanceState.fromWire(state.wire))
        }
    }
}
