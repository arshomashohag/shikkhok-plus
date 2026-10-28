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
 * A date as a line of copy says it: `20 Oct`.
 *
 * Month in the phone's language, day in Latin digits per the numeral
 * rule.
 *
 * @param iso `yyyy-MM-dd`
 * @return The short date, or the input if it cannot be read
 */
fun shortDate(iso: String): String =
    isoToUtcMillis(iso)?.let { millis ->
        val day = utcFormat("d").format(millis)
        val month = SimpleDateFormat("MMM", Locale.getDefault()).apply { timeZone = TimeZone.getTimeZone("UTC") }
        "$day ${month.format(millis)}"
    } ?: iso

/**
 * A server timestamp in the phone's time as `17 Oct, 3:22 pm`.
 *
 * @param iso The server's timestamp
 * @return The label, or the input if it cannot be read
 */
fun dateTimeLabel(iso: String): String =
    parseInstant(iso)?.let { millis ->
        val day = SimpleDateFormat("d", Locale.ENGLISH).format(millis)
        val month = SimpleDateFormat("MMM", Locale.getDefault()).format(millis)
        val time = SimpleDateFormat("h:mm a", Locale.ENGLISH).format(millis).lowercase(Locale.ENGLISH)
        "$day $month, $time"
    } ?: iso

/**
 * A `yyyy-MM-dd` date as the picker counts it: UTC midnight.
 *
 * @param iso The date, as the server sends it
 * @return Midnight UTC of that date, or null if it cannot be read
 */
fun isoToUtcMillis(iso: String): Long? = runCatching { utcFormat("yyyy-MM-dd").parse(iso)?.time }.getOrNull()

/**
 * A picked date for display, with Latin digits per the numeral rule.
 *
 * @param utcMillis A date as the picker reports it
 * @return e.g. `4 Nov 2026`
 */
fun displayDate(utcMillis: Long): String = utcFormat("d MMM yyyy").format(utcMillis)

/**
 * Read a timestamp the server wrote, such as `2026-10-28T10:15:02.48Z`.
 *
 * Fractional seconds are dropped and a `Z` read as UTC, because
 * `SimpleDateFormat` on API 24 cannot parse either directly.
 *
 * @param iso The server's ISO-8601 timestamp
 * @return Milliseconds since the epoch, or null if it cannot be read
 */
fun parseInstant(iso: String): Long? {
    val normalised =
        iso
            .replace(Regex("""\.\d+"""), "")
            .replace(Regex("Z$"), "+00:00")
    return runCatching {
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.ENGLISH).parse(normalised)?.time
    }.getOrNull()
}

/**
 * Name the month of a fee period, in the phone's language.
 *
 * Month names carry no digits, so the numeral rule does not apply.
 *
 * @param period `YYYY-MM`
 * @param short `Oct` rather than `October`
 * @return The month's name, or the period unchanged if unreadable
 */
fun monthName(period: String, short: Boolean = true): String =
    runCatching {
        val date = SimpleDateFormat("yyyy-MM", Locale.ENGLISH).parse(period) ?: return period
        SimpleDateFormat(if (short) "MMM" else "MMMM", Locale.getDefault()).format(date)
    }.getOrDefault(period)

/**
 * A day as Today's heading says it: `Saturday, 17 Oct`.
 *
 * Weekday and month in the phone's language, the day number in Latin
 * digits per the numeral rule.
 *
 * @param isoDate `YYYY-MM-DD`
 * @return The heading, or the date unchanged if unreadable
 */
fun dayHeading(isoDate: String): String =
    runCatching {
        val date = SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH).parse(isoDate) ?: return isoDate
        val weekday = SimpleDateFormat("EEEE", Locale.getDefault()).format(date)
        val month = SimpleDateFormat("MMM", Locale.getDefault()).format(date)
        val day = SimpleDateFormat("d", Locale.ENGLISH).format(date)
        "$weekday, $day $month"
    }.getOrDefault(isoDate)

/**
 * A formatter fixed to UTC and English, so digits are always Latin.
 *
 * @param pattern The date pattern
 * @return The formatter
 */
private fun utcFormat(pattern: String): SimpleDateFormat =
    SimpleDateFormat(pattern, Locale.ENGLISH).apply { timeZone = TimeZone.getTimeZone("UTC") }
