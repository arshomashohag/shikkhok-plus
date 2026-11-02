package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.model.ClaimOutcome
import com.shikkhokplus.app.core.model.HistoryLine

/** The built-in channel the server names `cash`. */
private const val CASH_CHANNEL = "cash"

/**
 * One month's latest payment claim, worded here from structured data.
 *
 * The server sends the amount, channel, date, status and the teacher's
 * note as separate fields, so the sentence is built in the person's
 * language and never arrives as English prose.
 *
 * @param line The claim
 * @param modifier Layout modifier
 */
@Composable
fun HistoryLineText(
    line: HistoryLine,
    modifier: Modifier = Modifier,
) {
    val channel =
        if (line.channel == CASH_CHANNEL) stringResource(R.string.verify_method_cash) else line.channel
    val format =
        when (line.outcome) {
            ClaimOutcome.PENDING -> R.string.history_line_pending
            ClaimOutcome.APPROVED_FULL -> R.string.history_line_approved_full
            ClaimOutcome.APPROVED_PARTIAL -> R.string.history_line_approved_partial
            ClaimOutcome.REJECTED -> R.string.history_line_rejected
        }
    Column(modifier) {
        Text(
            stringResource(format, Numerals.money(line.amount), channel, shortDate(line.paidOn)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        line.decisionNote?.let { note ->
            Text(
                stringResource(R.string.history_note, note),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
