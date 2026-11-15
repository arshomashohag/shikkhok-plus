package com.shikkhokplus.app.core.model

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The client's email shape is the server's, never stricter [Q5,
 * NFR3.10, FR11.3].
 *
 * The server matches `[^@\s]+@[^@\s]+\.[^@\s]+` against the whole
 * trimmed value, capped at 254 characters (`app/accounts/identifier.py`).
 * Before U3 the client refused `a@b.c.` and `a@.b.c`, which the server
 * takes, so a person could be refused on the phone for an address the
 * server would have accepted. These pin the two corners and the cap.
 *
 * **Limit, stated plainly:** this pins known corners; nothing compares
 * the client function with the server's regular expression mechanically.
 */
class EmailShapeTest {

    @Test
    fun `a trailing dot in the domain is accepted, as the server accepts it`() {
        assertTrue(emailIsWellFormed("a@b.c."))
    }

    @Test
    fun `a leading dot in the domain is accepted, as the server accepts it`() {
        assertTrue(emailIsWellFormed("a@.b.c"))
    }

    @Test
    fun `an ordinary address with surrounding spaces is accepted`() {
        assertTrue(emailIsWellFormed("  rina@example.com "))
    }

    @Test
    fun `no dot after the at sign is refused`() {
        assertFalse(emailIsWellFormed("a@b"))
    }

    @Test
    fun `nothing before the at sign is refused`() {
        assertFalse(emailIsWellFormed("@b.c"))
    }

    @Test
    fun `whitespace inside is refused`() {
        assertFalse(emailIsWellFormed("a b@c.d"))
        assertFalse(emailIsWellFormed("a@b .c"))
    }

    @Test
    fun `two at signs are refused`() {
        assertFalse(emailIsWellFormed("a@b@c.d"))
    }

    @Test
    fun `254 characters are accepted and 255 refused`() {
        val local = "a".repeat(64)
        val at254 = local + "@" + "b".repeat(254 - 64 - 1 - 4) + ".com"
        val at255 = local + "@" + "b".repeat(255 - 64 - 1 - 4) + ".com"

        assertTrue(at254.length == 254 && emailIsWellFormed(at254))
        assertTrue(at255.length == 255 && !emailIsWellFormed(at255))
    }

    @Test
    fun `blank is refused`() {
        assertFalse(emailIsWellFormed("   "))
    }
}
