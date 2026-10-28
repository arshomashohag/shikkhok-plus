package com.shikkhokplus.app.core.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.parseInstant

/** Minutes in an hour. */
private const val MINUTES_PER_HOUR = 60L

/** Minutes in a day. */
private const val MINUTES_PER_DAY = 1_440L

/** Milliseconds in a minute. */
private const val MILLIS_PER_MINUTE = 60_000L

/**
 * How long ago something happened, as the cards say it: `2 h ago`.
 *
 * Display only: nothing is decided from it. Latin digits per the
 * numeral rule.
 *
 * @param iso The server's timestamp
 * @param now The present, in milliseconds
 * @return The phrase, or the timestamp's date if it cannot be read
 */
@Composable
fun ago(iso: String, now: Long = System.currentTimeMillis()): String {
    val then = parseInstant(iso) ?: return iso.take(DATE_LENGTH)
    val minutes = ((now - then) / MILLIS_PER_MINUTE).coerceAtLeast(0)
    return when {
        minutes < 1 -> stringResource(R.string.time_just_now)
        minutes < MINUTES_PER_HOUR -> stringResource(R.string.time_minutes_ago, Numerals.count(minutes.toInt()))
        minutes < MINUTES_PER_DAY ->
            stringResource(R.string.time_hours_ago, Numerals.count((minutes / MINUTES_PER_HOUR).toInt()))
        else -> stringResource(R.string.time_days_ago, Numerals.count((minutes / MINUTES_PER_DAY).toInt()))
    }
}

/** `yyyy-MM-dd` out of a timestamp. */
private const val DATE_LENGTH = 10
