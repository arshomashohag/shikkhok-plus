package com.shikkhokplus.app.feature.profile

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The typed-number confirmation before deleting an account.
 *
 * A confirmation gesture, not an authorization check: the token is the
 * server's proof. What matters is that it is hard to pass by accident
 * and easy to pass on purpose.
 */
class NumberMatchesTest {

    private val phone = "+8801611477203"

    @Test
    fun `the local number matches, with or without punctuation`() {
        assertTrue(numberMatches("01611477203", phone))
        assertTrue(numberMatches("01611-477203", phone))
        assertTrue(numberMatches(" 01611 477 203 ", phone))
    }

    @Test
    fun `the number with its country code matches`() {
        assertTrue(numberMatches("+8801611477203", phone))
        assertTrue(numberMatches("8801611477203", phone))
    }

    @Test
    fun `Bangla digits match`() {
        assertTrue(numberMatches("০১৬১১৪৭৭২০৩", phone))
    }

    @Test
    fun `a short tail does not match`() {
        // The last few digits are visible to anyone who has seen the
        // number on screen; they must not be enough.
        assertFalse(numberMatches("477203", phone))
        assertFalse(numberMatches("1611477203", phone))
    }

    @Test
    fun `a different number does not match`() {
        assertFalse(numberMatches("01711477203", phone))
    }

    @Test
    fun `nothing matches when the account's number is unknown`() {
        // Failing closed: an action that cannot be undone needs a known
        // number to confirm against.
        assertFalse(numberMatches("01611477203", null))
    }

    @Test
    fun `blank does not match`() {
        assertFalse(numberMatches("", phone))
    }
}
