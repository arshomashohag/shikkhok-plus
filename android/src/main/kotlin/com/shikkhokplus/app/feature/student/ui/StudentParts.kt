package com.shikkhokplus.app.feature.student.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.student.FeeLine
import com.shikkhokplus.app.feature.student.LastResult
import com.shikkhokplus.app.feature.student.NextClass

/** The blue "Next class" card. */
const val TAG_STUDENT_HERO: String = "student_hero"

/** A fee status chip. */
const val TAG_STUDENT_FEE_CHIP: String = "student_fee_chip"

/** Minutes in an hour. */
private const val MINUTES_PER_HOUR = 60

/** The hero card's soft caption colour, #D8E3F7 on the board. */
private val HeroCaption = Color(0xFFD8E3F7)

/**
 * The blue card naming the next class: how soon, when, and where.
 *
 * @param next The class
 * @param caption What it is: batch and teacher, or the subject
 * @param withEnd Whether to show the end time as well
 * @param modifier The layout modifier
 */
@Composable
fun NextClassHero(next: NextClass, caption: String?, withEnd: Boolean, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.primary, MaterialTheme.shapes.medium)
            .padding(horizontal = 16.dp, vertical = 14.dp)
            .testTag(TAG_STUDENT_HERO),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            howSoon(next),
            style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
            color = HeroCaption,
        )
        Text(
            whenLabel(next, withEnd),
            style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onPrimary,
        )
        caption?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimary)
        }
    }
}

/**
 * "Next class · in 35 min", or plain "Next class" when it is not today.
 *
 * @param next The class
 * @return The caption
 */
@Composable
private fun howSoon(next: NextClass): String {
    val minutes = next.startsInMinutes ?: return stringResource(R.string.student_next_class)
    return if (minutes < MINUTES_PER_HOUR) {
        stringResource(R.string.student_next_in_min, Numerals.count(minutes))
    } else {
        stringResource(
            R.string.student_next_in_hours,
            Numerals.count(minutes / MINUTES_PER_HOUR),
            Numerals.count(minutes % MINUTES_PER_HOUR),
        )
    }
}

/**
 * "Today, 4:00 pm" or "Mon 19 Oct, 4:00–5:30 pm".
 *
 * "Today" is said only where the server sent a countdown, which it does
 * only for a class today; the phone compares no dates.
 *
 * @param next The class
 * @param withEnd Whether to show the end time as well
 * @return The label
 */
@Composable
fun whenLabel(next: NextClass, withEnd: Boolean): String {
    val today = next.startsInMinutes != null
    val start = displayTime(next.startTime)
    val end = next.endTime?.takeIf { withEnd }?.let(::displayTime)
    return when {
        today && end != null -> stringResource(R.string.student_today_range, rangeStart(start, end), end)
        today -> stringResource(R.string.student_today_at, start)
        end != null -> stringResource(R.string.student_day_range, dayLabel(next.date), rangeStart(start, end), end)
        else -> stringResource(R.string.student_day_at, dayLabel(next.date), start)
    }
}

/**
 * A range's first time, without its am/pm when the end shares it:
 * "4:00–5:30 pm", but "11:00 am–12:30 pm".
 *
 * @param start The start, as displayed
 * @param end The end, as displayed
 * @return The start to print
 */
private fun rangeStart(start: String, end: String): String =
    if (start.takeLast(HALF_LENGTH) == end.takeLast(HALF_LENGTH)) start.dropLast(HALF_LENGTH + 1) else start

/** The length of "am" or "pm". */
private const val HALF_LENGTH = 2

/**
 * "44/50 · rank 5", the mark in bold, or "None yet".
 *
 * @param result The latest result, or null
 */
@Composable
fun LastResultText(result: LastResult?) {
    if (result == null) {
        Text(
            stringResource(R.string.student_none_yet),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return
    }
    val outOf = stringResource(R.string.student_out_of, Numerals.count(result.totalMarks))
    val rank = result.rank?.let { " " + stringResource(R.string.student_rank, Numerals.count(it)) }.orEmpty()
    Text(
        buildAnnotatedString {
            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Numerals.count(result.marks)) }
            append(outOf)
            append(rank)
        },
        style = MaterialTheme.typography.bodyMedium,
    )
}

/**
 * The fee's status as the board's chips draw it.
 *
 * Keyed on the server's status and its "verifying" flag; the amounts are
 * never compared here.
 *
 * @param fee The period
 * @param modifier The layout modifier
 */
@Composable
fun FeeChip(fee: FeeLine, modifier: Modifier = Modifier) {
    val (state, label) =
        when {
            fee.verifying -> PaymentState.VERIFYING to stringResource(R.string.student_chip_verifying)
            fee.statusKey == PAID_KEY -> PaymentState.PAID to stringResource(R.string.student_chip_paid)
            fee.statusKey == WAIVED_KEY -> PaymentState.PAID to stringResource(R.string.student_chip_waived)
            fee.statusKey == PARTLY_PAID_KEY ->
                PaymentState.PARTIAL to stringResource(R.string.student_chip_partly_paid)
            else -> PaymentState.DUE to stringResource(R.string.student_chip_due, shortDate(fee.dueDate))
        }
    PaymentStateChip(state, label, modifier = modifier.testTag(TAG_STUDENT_FEE_CHIP), compact = true)
}

/** The server statuses' message keys, as the fee mapper names them. */
private const val PAID_KEY = "fees.status.paid"
private const val WAIVED_KEY = "fees.status.waived"
private const val PARTLY_PAID_KEY = "fees.status.partly_paid"
