package com.shikkhokplus.app.core.format

import java.util.Locale
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Reading the server's timestamps and naming days and months.
 *
 * The digits are Latin whatever the phone's language, per the numeral
 * rule: under Bangla, the weekday and month are Bangla words and the day
 * number stays `17`.
 */
class DatesTest {

    private val original = Locale.getDefault()

    @BeforeTest
    fun english() = Locale.setDefault(Locale.ENGLISH)

    @AfterTest
    fun restore() = Locale.setDefault(original)

    @Test
    fun `a server timestamp reads with or without fractions and a Z`() {
        val plain = parseInstant("2026-10-28T10:00:00Z")
        val fractional = parseInstant("2026-10-28T10:00:00.123456Z")
        val offset = parseInstant("2026-10-28T16:00:00+06:00")

        assertEquals(1_793_181_600_000L, plain)
        assertEquals(plain, fractional)
        assertEquals(plain, offset)
    }

    @Test
    fun `an unreadable timestamp is null, not a crash`() {
        assertNull(parseInstant("yesterday"))
    }

    @Test
    fun `a period names its month, short or long`() {
        assertEquals("Oct", monthName("2026-10"))
        assertEquals("October", monthName("2026-10", short = false))
        assertEquals("soon", monthName("soon"))
    }

    @Test
    fun `today's heading names the weekday, day and month`() {
        assertEquals("Saturday, 17 Oct", dayHeading("2026-10-17"))
        assertEquals("not a date", dayHeading("not a date"))
    }

    @Test
    fun `under Bangla the day number stays in Latin digits`() {
        Locale.setDefault(Locale.forLanguageTag("bn-BD"))

        val heading = dayHeading("2026-10-17")

        assertEquals(true, heading.contains(" 17 "), heading)
    }

    @Test
    fun `a server date round-trips through the picker's UTC midnight`() {
        val millis = isoToUtcMillis("2026-11-04")

        assertEquals("2026-11-04", millis?.let(::isoDate))
        assertEquals(null, isoToUtcMillis("not a date"))
    }
}
