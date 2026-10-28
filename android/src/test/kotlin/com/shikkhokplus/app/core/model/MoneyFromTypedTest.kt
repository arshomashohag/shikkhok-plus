package com.shikkhokplus.app.core.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Turning what a teacher TYPES into the canonical wire form.
 *
 * **Written before the function existed**, because both halves of the
 * test-first predicate hold: every expected value below is knowable
 * from the server's `Money` pattern without any implementation, and a
 * wrong answer is a money error.
 *
 * **The defect this closes.** Both create forms sent the fee exactly as
 * typed. The server accepts only `^[0-9]+\.[0-9]{2}$`, so a teacher who
 * typed `1500` -- which is every teacher -- was refused with a 422, and
 * the refusal was then hidden by a list reload racing it. The class was
 * never created and nothing said so.
 *
 * Kept apart from [Money.of] on purpose. That function parses the WIRE
 * and must stay strict: its own documentation names a lenient wire
 * parse as the actual failure mode. Typed input is a different job,
 * and folding the two together would loosen the one that must not be.
 */
class MoneyFromTypedTest {

    private fun typed(raw: String): String? = Money.fromTyped(raw)?.toString()

    @Test
    fun `a whole number gains its two decimals`() {
        assertEquals("1500.00", typed("1500"))
    }

    @Test
    fun `one decimal place is padded, not rejected`() {
        assertEquals("1500.50", typed("1500.5"))
    }

    @Test
    fun `the canonical form passes through unchanged`() {
        assertEquals("1500.00", typed("1500.00"))
    }

    @Test
    fun `surrounding whitespace is ignored`() {
        assertEquals("800.00", typed("  800 "))
    }

    @Test
    fun `thousands separators are removed`() {
        // A teacher reading "১,৫০০" off a receipt types it that way.
        assertEquals("1500.00", typed("1,500"))
        assertEquals("150000.00", typed("1,50,000"))
    }

    @Test
    fun `Bangla digits are read as digits`() {
        // **The case that matters most in a Bangla-first app.** A
        // Bangla keyboard emits U+09E6..U+09EF, and the server's
        // pattern admits only Latin digits.
        assertEquals("1500.00", typed("১৫০০"))
        assertEquals("1500.50", typed("১৫০০.৫"))
        assertEquals("1500.00", typed("১,৫০০"))
    }

    @Test
    fun `a leading taka sign is allowed`() {
        assertEquals("1500.00", typed("৳1500"))
        assertEquals("1500.00", typed("৳ 1500"))
    }

    @Test
    fun `zero is a value, not an absence`() {
        // Zero is a WAIVER [AC2.2.5]. It must survive as 0.00 so the
        // caller can tell it apart from a blank field, which inherits.
        assertEquals("0.00", typed("0"))
    }

    @Test
    fun `three decimal places are refused, never rounded`() {
        // **No rounding on the client.** The rounding mode is declared
        // once, server-side [D-20]; rounding here would be a second
        // declaration that could disagree with it.
        assertNull(typed("1500.555"))
    }

    @Test
    fun `a negative amount is refused`() {
        assertNull(typed("-1500"))
    }

    @Test
    fun `text that is not a number is refused`() {
        assertNull(typed("fifteen hundred"))
        assertNull(typed("1500tk"))
        assertNull(typed("15.00.00"))
        assertNull(typed("."))
    }

    @Test
    fun `blank input is refused, because blank means inherit`() {
        // The caller decides what blank means; this function only ever
        // answers "which amount did they type". Returning ZERO here
        // would silently waive every inherited fee.
        assertNull(typed(""))
        assertNull(typed("   "))
    }

    @Test
    fun `a separator in the wrong place is refused`() {
        assertNull(typed(",1500"))
        assertNull(typed("1500,"))
    }
}
