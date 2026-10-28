package com.shikkhokplus.app.core.format

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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
