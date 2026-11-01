package com.shikkhokplus.app.core.format

import java.util.Calendar
import java.util.GregorianCalendar
import java.util.Locale

/**
 * A calendar month, without `java.time`.
 *
 * `java.time.YearMonth` needs API 26 or core-library desugaring, and
 * this app supports API 24 with neither, so the calendar carries its
 * own. Same shape as the platform class where it is used: comparable,
 * with month arithmetic and a `YYYY-MM` wire form.
 *
 * @property year The year, e.g. 2026
 * @property month The month, 1 to 12
 */
data class YearMonth(val year: Int, val month: Int) : Comparable<YearMonth> {

    init {
        require(month in 1..MONTHS_IN_YEAR) { "month must be 1..12, was $month" }
    }

    /**
     * Order by year, then month.
     *
     * @param other The month to compare with
     * @return Negative, zero or positive
     */
    override fun compareTo(other: YearMonth): Int = index().compareTo(other.index())

    /**
     * Step by whole months, across year ends.
     *
     * @param months How many months, negative to go back
     * @return The month that far away
     */
    fun plusMonths(months: Long): YearMonth {
        val total = index() + months
        val y = Math.floorDiv(total, MONTHS_IN_YEAR.toLong()).toInt()
        val m = Math.floorMod(total, MONTHS_IN_YEAR.toLong()).toInt() + 1
        return YearMonth(y, m)
    }

    /**
     * Number of days in this month, leap years included.
     *
     * @return 28 to 31
     */
    fun lengthOfMonth(): Int =
        GregorianCalendar(year, month - 1, 1).getActualMaximum(Calendar.DAY_OF_MONTH)

    /**
     * How many blanks precede day 1 in a Sunday-first grid.
     *
     * @return 0 for a month starting on Sunday, up to 6 for Saturday
     */
    fun leadingBlanks(): Int = GregorianCalendar(year, month - 1, 1).get(Calendar.DAY_OF_WEEK) - 1

    /**
     * The date of a day in this month, in the wire form.
     *
     * @param day 1 to [lengthOfMonth]
     * @return `YYYY-MM-DD`
     */
    fun isoDay(day: Int): String = String.format(Locale.ENGLISH, "%04d-%02d-%02d", year, month, day)

    /**
     * The wire form.
     *
     * @return `YYYY-MM`
     */
    override fun toString(): String = String.format(Locale.ENGLISH, "%04d-%02d", year, month)

    private fun index(): Long = year.toLong() * MONTHS_IN_YEAR + (month - 1)

    companion object {
        private const val MONTHS_IN_YEAR = 12

        /**
         * Read a `YYYY-MM` string.
         *
         * @param text The wire form
         * @return The month, or null if it cannot be read
         */
        fun parseOrNull(text: String?): YearMonth? {
            val parts = text?.split("-") ?: return null
            if (parts.size != 2) return null
            val y = parts[0].toIntOrNull() ?: return null
            val m = parts[1].toIntOrNull() ?: return null
            return if (m in 1..MONTHS_IN_YEAR) YearMonth(y, m) else null
        }
    }
}
