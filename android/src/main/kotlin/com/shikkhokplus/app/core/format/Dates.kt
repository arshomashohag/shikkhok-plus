package com.shikkhokplus.app.core.format

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Today's LOCAL calendar date, in the wire's `yyyy-MM-dd` form.
 *
 * Local, not UTC: "inactive from today" means the teacher's today, and
 * at UTC+6 the UTC date is still yesterday until 6 am. English locale,
 * so the digits are Latin whatever the phone's language [numeral rule].
 *
 * `SimpleDateFormat` rather than `java.time`, which needs API 26 or
 * desugaring and this app supports API 24.
 *
 * @return Today, e.g. `2026-10-28`
 */
fun todayIso(): String = SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH).format(Date())

/**
 * Today's date as the date picker counts it: UTC midnight.
 *
 * The picker speaks UTC midnights. Today must be the LOCAL calendar
 * date expressed that way, or a teacher in Bangladesh (UTC+6) opening
 * the form before 6 am would be offered yesterday.
 *
 * @return Midnight UTC of today's local date
 */
fun todayAsUtcMillis(): Long {
    val local = Calendar.getInstance()
    val utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
    utc.clear()
    utc.set(
        local.get(Calendar.YEAR),
        local.get(Calendar.MONTH),
        local.get(Calendar.DAY_OF_MONTH),
    )
    return utc.timeInMillis
}

/**
 * The wire form of a picked date.
 *
 * **Formatted in UTC**, because the picker's millis are UTC midnight.
 * Formatted in local time they read correctly east of UTC -- so a test
 * run in Dhaka would pass -- and show the previous day anywhere west of
 * it. Formatting in UTC is right in every zone.
 *
 * @param utcMillis A date as the picker reports it
 * @return `yyyy-MM-dd`
 */
fun isoDate(utcMillis: Long): String = utcFormat("yyyy-MM-dd").format(utcMillis)

/**
 * A picked date for display, with Latin digits per the numeral rule.
 *
 * @param utcMillis A date as the picker reports it
 * @return e.g. `4 Nov 2026`
 */
fun displayDate(utcMillis: Long): String = utcFormat("d MMM yyyy").format(utcMillis)

/**
 * A formatter fixed to UTC and English, so digits are always Latin.
 *
 * @param pattern The date pattern
 * @return The formatter
 */
private fun utcFormat(pattern: String): SimpleDateFormat =
    SimpleDateFormat(pattern, Locale.ENGLISH).apply { timeZone = TimeZone.getTimeZone("UTC") }
