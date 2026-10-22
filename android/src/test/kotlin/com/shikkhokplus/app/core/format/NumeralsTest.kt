package com.shikkhokplus.app.core.format

import com.shikkhokplus.app.core.model.Money
import java.math.BigDecimal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The numeral rule, from the design system's stated contract.
 *
 * Written before the implementation: the expected values come from the
 * design, not from the code, and money output is exactly the case the
 * team's ordering predicate puts test-first.
 */
class NumeralsTest {

    // Lakh grouping ---------------------------------------------------

    @Test
    fun `an amount groups by lakh, not by thousand`() {
        // 1,25,400 is how a Bangladeshi reader parses this, including
        // in English. Western grouping would render 125,400.
        assertEquals("৳1,25,400", Numerals.money(money("125400")))
    }

    @Test
    fun `four digits take one group`() {
        assertEquals("৳1,200", Numerals.money(money("1200")))
    }

    @Test
    fun `five digits break at two from the left`() {
        assertEquals("৳48,600", Numerals.money(money("48600")))
    }

    @Test
    fun `seven digits take two lakh groups`() {
        assertEquals("৳12,34,567", Numerals.money(money("1234567")))
    }

    @Test
    fun `three digits are left alone`() {
        assertEquals("৳400", Numerals.money(money("400")))
    }

    @Test
    fun `zero renders as zero, not blank`() {
        assertEquals("৳0", Numerals.money(money("0")))
    }

    @Test
    fun `amounts never show decimals`() {
        // The design states this flatly. 2dp is stored; it is not shown.
        assertEquals("৳1,200", Numerals.money(money("1200.00")))
        assertEquals("৳1,201", Numerals.money(money("1200.50")))
    }

    // Bengali digit input ---------------------------------------------

    @Test
    fun `Bengali digits are accepted as a number`() {
        // A teacher typing names in Bangla stays on the Bangla
        // keyboard, which types these. Switching keyboards per field
        // is the thing this avoids.
        assertEquals(BigDecimal("125400"), Numerals.parseAmount("১২৫৪০০"))
    }

    @Test
    fun `Latin digits are accepted`() {
        assertEquals(BigDecimal("125400"), Numerals.parseAmount("125400"))
    }

    @Test
    fun `grouping separators in input are ignored`() {
        assertEquals(BigDecimal("125400"), Numerals.parseAmount("1,25,400"))
    }

    @Test
    fun `mixed digit sets in one field are accepted`() {
        // Not a contrived case: a predictive keyboard can emit either.
        assertEquals(BigDecimal("1200"), Numerals.parseAmount("১2০0"))
    }

    @Test
    fun `a Bengali decimal is accepted`() {
        assertEquals(BigDecimal("47.5"), Numerals.parseAmount("৪৭.৫"))
    }

    @Test
    fun `text that is not a number is refused rather than coerced`() {
        assertNull(Numerals.parseAmount(""))
        assertNull(Numerals.parseAmount("   "))
        assertNull(Numerals.parseAmount("abc"))
        assertNull(Numerals.parseAmount("৳"))
    }

    // Marks -----------------------------------------------------------

    @Test
    fun `marks keep a half mark but drop a trailing zero`() {
        assertEquals("47.5 / 50", Numerals.marks(BigDecimal("47.5"), 50))
        assertEquals("47 / 50", Numerals.marks(BigDecimal("47.0"), 50))
    }

    // Phone -----------------------------------------------------------

    @Test
    fun `a phone number is grouped after the operator prefix`() {
        assertEquals("01711-234567", Numerals.phone("+8801711234567"))
        assertEquals("01711-234567", Numerals.phone("01711234567"))
    }

    @Test
    fun `a phone number typed in Bengali digits is grouped too`() {
        assertEquals("01711-234567", Numerals.phone("০১৭১১২৩৪৫৬৭"))
    }

    @Test
    fun `an unexpected phone length is shown as given rather than mangled`() {
        // Better a number that looks odd than one silently reshaped
        // into something that is not what the owner typed.
        assertEquals("12345", Numerals.phone("12345"))
    }

    // Transaction id --------------------------------------------------

    @Test
    fun `a transaction id is upper-cased with spaces removed`() {
        assertEquals("BJK40OQ1IL", Numerals.transactionId(" bjk40oq1il "))
        assertEquals("BJK40OQ1IL", Numerals.transactionId("BJK4 0OQ1 IL"))
    }

    // Free text -------------------------------------------------------

    @Test
    fun `free text is never converted`() {
        // The rule the design is most explicit about: digits inside
        // text a person wrote stay exactly as written.
        val typed = "অধ্যায় ৩ — Chapter 3 recap"
        assertEquals(typed, Numerals.freeText(typed))
    }

    /**
     * Build a [Money] from a plain amount.
     *
     * [Money] requires exactly two decimal places, so a bare "1200"
     * is rejected by its constructor. Scaling here rather than writing
     * "1200.00" at every call site keeps the test reading in the units
     * the design states.
     */
    private fun money(amount: String) =
        Money(BigDecimal(amount).setScale(2))
}
